"""Document review, human decisions, and controlled change management routes."""

from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from app.agents.document_change_agent import RegulatoryDocumentChangeAgent
from app.models.content import RegulatoryContentItem
from app.models.document_change import (
    ApprovedChangeReport,
    ChangeImpact,
    ConfirmOccurrencesRequest,
    ProposedChange,
    RelatedOccurrence,
    ReviewDecisionType,
    ReviewerDecision,
)
from app.models.audit import AuditEventType
from app.services.candidate_store import get_candidate_store
from app.services.change_manager import ChangeManagerService
from app.services.content_extraction import ContentExtractionService
from app.services.corrected_document_generator import (
    CorrectedDocumentGenerator,
    CorrectedDocumentResult,
    TargetResolutionError,
    UnapprovedReportError,
    UnresolvedOccurrencesError,
    UnsupportedFormatError,
)
from app.services.pdf_generator import PDFReportGenerator

router = APIRouter(tags=["Document Review & Change Management"])

extractor = ContentExtractionService()
change_manager = ChangeManagerService()
change_agent = RegulatoryDocumentChangeAgent()
pdf_generator = PDFReportGenerator()
corrected_doc_generator = CorrectedDocumentGenerator()


class DocumentUploadRequest(BaseModel):
    document_name: str = Field(..., min_length=1, description="File or document name")
    content: str = Field(..., min_length=10, description="Raw text of regulatory document")


class ChangeAnalyzeRequest(BaseModel):
    decision_id: str = Field(..., description="Linked human decision ID")
    section: str = Field(..., description="Target regulatory section")
    original_text: str = Field(..., description="Original text prior to change")
    candidate_text: Optional[str] = Field(default=None, description="Candidate reference text")
    document_name: Optional[str] = Field(default=None, description="Subject document name")
    document_version: Optional[str] = Field(default=None, description="Subject document version")
    document_sections: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional list of all document sections for related occurrence detection",
    )
    document_id: Optional[str] = Field(
        default=None,
        description="Authoritative source regulatory document identifier",
    )


class DetectOccurrencesRequest(BaseModel):
    target_phrase: str = Field(..., min_length=3, description="Search phrase or excerpt")
    document_sections: List[Dict[str, Any]] = Field(..., description="List of document sections to search")
    target_text: Optional[str] = Field(default=None, description="Full context text for false-match checks")


class ApproveReportRequest(BaseModel):
    approver_name: str = Field(..., min_length=1, description="Authorized regulatory approver identity")
    approval_confirmation: bool = Field(
        default=False,
        description="Explicit human approval confirmation. MUST NEVER DEFAULT TO TRUE.",
    )
    document_name: Optional[str] = Field(default=None, description="Subject regulatory document")
    document_version: Optional[str] = Field(default=None, description="Document revision")
    audit_notes: Optional[str] = Field(default=None, description="Compliance audit notes")
    proposal_ids: Optional[List[str]] = Field(default=None, description="Specific proposal IDs to approve")
    document_id: Optional[str] = Field(
        default=None,
        description="Authoritative source regulatory document identifier",
    )


@router.post(
    "/documents/upload",
    response_model=List[RegulatoryContentItem],
    summary="Extract regulatory sections from uploaded document text",
)
async def upload_document(payload: DocumentUploadRequest) -> List[RegulatoryContentItem]:
    """Parse raw regulatory document into structured section components."""
    try:
        sections = extractor.extract_sections_from_text(
            text=payload.content,
            document_name=payload.document_name,
        )
        store = get_candidate_store()
        doc_id = f"doc_{uuid4().hex[:8]}"
        fn = payload.document_name
        if not fn.endswith((".txt", ".md", ".json", ".xml", ".html", ".pdf", ".docx", ".doc")):
            fn = f"{fn}.txt"
        store.store_source_document(
            document_id=doc_id,
            source_bytes=payload.content.encode("utf-8"),
            filename=fn,
            file_format="txt",
        )
        for s in sections:
            s.document_id = doc_id
            store._content_items[s.content_id] = s
        return sections
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document parsing failed: {exc}",
        )


@router.post(
    "/review/decision",
    response_model=ReviewerDecision,
    summary="Record human regulatory professional decision (Reuse, Adapt, Reject)",
)
async def record_review_decision(decision: ReviewerDecision) -> ReviewerDecision:
    """Store the human reviewer's authoritative decision.

    Auditable for all decision states (REUSE, ADAPT, REJECT).
    """
    if not decision.reviewer_name or not decision.reviewer_name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reviewer name/identity is required.",
        )

    if decision.decision == ReviewDecisionType.ADAPT and not (decision.adaptation_instructions or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Adaptation instructions are required when selecting ADAPT.",
        )

    try:
        if not decision.document_id and decision.target_content_id:
            store = get_candidate_store()
            chunk = store.get_chunk(decision.target_content_id)
            if chunk and chunk.document_id:
                decision.document_id = chunk.document_id
            else:
                item = store.get_content_item(decision.target_content_id)
                if item and item.document_id:
                    decision.document_id = item.document_id
                else:
                    raw_id = decision.target_content_id
                    base_id = raw_id.rsplit("_item", 1)[0] if raw_id.endswith("_item") else raw_id
                    if store.has_source_document(base_id) or store.get_document(base_id):
                        decision.document_id = base_id
                    elif store.has_source_document(raw_id) or store.get_document(raw_id):
                        decision.document_id = raw_id
        return change_manager.record_decision(decision)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record decision: {exc}",
        )


@router.post(
    "/changes/analyze",
    response_model=ProposedChange,
    summary="Formulate controlled change proposal via Agent 2",
)
async def analyze_change_proposal(payload: ChangeAnalyzeRequest) -> ProposedChange:
    """Invoke Agent 2 foundation to formulate a change proposal for a recorded decision.

    MANDATORY GOVERNANCE:
    If human decision was REJECT, no change proposal is created.
    """
    decision = change_manager.get_decision(payload.decision_id)
    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision ID '{payload.decision_id}' not found.",
        )

    if decision.decision == ReviewDecisionType.REJECT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot formulate a change proposal for a REJECT decision. "
                "The regulatory candidate was rejected, and original document content is strictly preserved."
            ),
        )

    proposal = change_agent.formulate_change_proposal(
        decision=decision,
        section=payload.section,
        original_text=payload.original_text,
        candidate_text=payload.candidate_text,
        document_name=payload.document_name,
        document_version=payload.document_version,
        document_sections=payload.document_sections,
    )

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to formulate proposed change from decision.",
        )

    # Attach authoritative document_id to proposal
    resolved_doc_id = payload.document_id
    if not resolved_doc_id and decision:
        if getattr(decision, "document_id", None):
            resolved_doc_id = decision.document_id
        elif decision.target_content_id:
            store = get_candidate_store()
            chunk = store.get_chunk(decision.target_content_id)
            if chunk and chunk.document_id:
                resolved_doc_id = chunk.document_id
            else:
                item = store.get_content_item(decision.target_content_id)
                if item and item.document_id:
                    resolved_doc_id = item.document_id
                else:
                    raw_id = decision.target_content_id
                    base_id = raw_id.rsplit("_item", 1)[0] if raw_id.endswith("_item") else raw_id
                    if store.has_source_document(base_id) or store.get_document(base_id):
                        resolved_doc_id = base_id
                    elif store.has_source_document(raw_id) or store.get_document(raw_id):
                        resolved_doc_id = raw_id

    if resolved_doc_id:
        proposal.document_id = resolved_doc_id

    change_manager.save_proposal(proposal)
    return proposal


@router.post(
    "/changes/occurrences",
    response_model=List[RelatedOccurrence],
    summary="Detect related occurrences across document sections with false-match protection",
)
async def detect_occurrences(payload: DetectOccurrencesRequest) -> List[RelatedOccurrence]:
    """Identify occurrences across 4 layers (exact, normalized, structured, semantic)."""
    try:
        return change_agent.detect_related_occurrences(
            target_phrase=payload.target_phrase,
            document_sections=payload.document_sections,
            target_text=payload.target_text,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Occurrence detection failed: {exc}",
        )


@router.post(
    "/changes/occurrences/confirm",
    response_model=ProposedChange,
    summary="Confirm or exclude detected occurrences for coordinated change",
)
async def confirm_occurrences(payload: ConfirmOccurrencesRequest) -> ProposedChange:
    """Confirm or exclude detected occurrences for a proposed change.

    Recalculates change impact and validation findings based on confirmed occurrences.
    Excluded occurrences remain preserved with status EXCLUDED for audit traceability.
    """
    try:
        return change_manager.confirm_occurrences(
            change_id=payload.change_id,
            confirmed_occurrence_ids=payload.confirmed_occurrence_ids,
            excluded_occurrence_ids=payload.excluded_occurrence_ids,
            reviewer_notes=payload.reviewer_notes,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc.args[0]),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Occurrence confirmation failed: {exc}",
        )



@router.post(
    "/changes/validate",
    response_model=ChangeImpact,
    summary="Validate proposed change against regulatory rules",
)
async def validate_change(proposal: ProposedChange) -> ChangeImpact:
    """Run validation engine and assess impact."""
    impact = change_agent.assess_impact_and_validate(proposal)
    change_manager.record_validation(proposal, impact)
    return impact


@router.post(
    "/changes/approve",
    response_model=ApprovedChangeReport,
    summary="Finalize human approval and compile change report",
)
async def approve_and_generate_report(payload: ApproveReportRequest) -> ApprovedChangeReport:
    """Assemble all active proposals into an authorized audit report.

    MANDATORY APPROVAL GATE:
    - approval_confirmation MUST be explicitly True (NEVER defaults to True).
    - approver_name must be a non-empty human regulatory authority.
    """
    if not payload.approval_confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit human approval confirmation (approval_confirmation=true) is mandatory before generating an Approved Change Report.",
        )

    if not payload.approver_name or not payload.approver_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid human regulatory approver identity is required.",
        )

    all_proposals = change_manager.list_proposals()
    if payload.proposal_ids:
        proposals = [p for p in all_proposals if p.change_id in payload.proposal_ids]
    else:
        proposals = all_proposals

    # Filter out rejected or invalid proposals
    eligible_proposals = [
        p for p in proposals
        if getattr(p, "decision_type", None) != ReviewDecisionType.REJECT
        and getattr(p, "status", None) != "REJECTED"
    ]

    if not eligible_proposals:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No eligible change proposals available to approve. Rejected candidates cannot be approved.",
        )

    try:
        report = change_agent.generate_approved_change_report(
            document_name=payload.document_name,
            document_version=payload.document_version,
            approver_name=payload.approver_name,
            approval_confirmation=payload.approval_confirmation,
            approved_changes=eligible_proposals,
            audit_notes=payload.audit_notes,
            document_id=payload.document_id,
        )

        # Authoritative document_id assignment
        if payload.document_id:
            report.document_id = payload.document_id
        elif not report.document_id:
            for p in eligible_proposals:
                if getattr(p, "document_id", None):
                    report.document_id = p.document_id
                    break
            if not report.document_id:
                store = get_candidate_store()
                for p in eligible_proposals:
                    if p.decision_id:
                        dec = change_manager.get_decision(p.decision_id)
                        if dec:
                            if getattr(dec, "document_id", None):
                                report.document_id = dec.document_id
                                break
                            if dec.target_content_id:
                                chunk = store.get_chunk(dec.target_content_id)
                                if chunk and chunk.document_id:
                                    report.document_id = chunk.document_id
                                    break
                                item = store.get_content_item(dec.target_content_id)
                                if item and item.document_id:
                                    report.document_id = item.document_id
                                    break
                                raw_id = dec.target_content_id
                                base_id = raw_id.rsplit("_item", 1)[0] if raw_id.endswith("_item") else raw_id
                                if store.has_source_document(base_id) or store.get_document(base_id):
                                    report.document_id = base_id
                                    break
                                elif store.has_source_document(raw_id) or store.get_document(raw_id):
                                    report.document_id = raw_id
                                    break

        # Mark proposals as approved and record audit transitions
        for p in eligible_proposals:
            p.status = "APPROVED"
            change_manager.update_proposal_status(
                p.change_id,
                "APPROVED",
                reviewer_name=payload.approver_name,
                notes=payload.audit_notes,
            )
        change_manager.record_approved_report(report)
        return report
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report assembly failed: {exc}",
        )


@router.get(
    "/changes/report",
    response_model=List[ProposedChange],
    summary="List currently pending or formulated change proposals",
)
async def list_proposals() -> List[ProposedChange]:
    return change_manager.list_proposals()


@router.get(
    "/changes/report/{report_id}/pdf",
    summary="Export audit-ready PDF representation of an approved change report",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Deterministic PDF representation of the approved report and audit trail.",
        },
        400: {"description": "Report has not received explicit human regulatory approval."},
        404: {"description": "Approved change report not found."},
    },
)
async def export_approved_report_pdf(report_id: str) -> Response:
    """Generate and return an audit-ready PDF for an already approved change report.

    READ-ONLY: Does not mutate workflow state, create approvals, or emit audit events.
    Enforces that the report exists and has explicit human approval confirmation.
    """
    report = change_manager.get_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approved change report '{report_id}' not found.",
        )

    if not report.approval_confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report '{report_id}' has not received explicit human regulatory approval confirmation.",
        )

    audit_events = change_manager.list_audit_events_for_report(report)
    pdf_bytes = pdf_generator.generate(report=report, audit_events=audit_events)

    filename = f"Approved_Change_Report_{report_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post(
    "/changes/report/{report_id}/corrected-document",
    summary="Generate and download a corrected regulatory document from retained original source bytes",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {},
                "text/plain": {},
            },
            "description": "Deterministic corrected regulatory document byte stream attachment.",
        },
        400: {"description": "Invalid report configuration, missing document_id, or unsupported format."},
        404: {"description": "Approved change report or source document not found."},
        409: {"description": "Workflow conflict: unapproved report, pending occurrences, or ambiguous target."},
    },
)
async def generate_corrected_document(report_id: str) -> Response:
    """Generate and return a corrected regulatory document from retained source bytes.

    Strictly enforces:
    1. Report exists and has explicit human approval confirmation.
    2. Valid human regulatory approver identity is present.
    3. All related occurrences are resolved (no PENDING occurrences).
    4. Only CONFIRMED occurrences are applied; EXCLUDED occurrences remain unchanged.
    5. Resolves original source document via report.document_id.
    6. Rejects input-only formats (PDF, legacy .doc) cleanly.
    7. Appends a tamper-evident CORRECTED_DOCUMENT_GENERATED audit event with SHA-256 hash.
    8. Returns the corrected document as a downloadable file attachment.
    """
    report = change_manager.get_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approved change report '{report_id}' not found.",
        )

    # 1. Approval guard
    if not report.approval_confirmation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Document correction rejected: Report '{report_id}' has not received explicit "
                "human regulatory approval confirmation (approval_confirmation=true)."
            ),
        )

    if not report.author_approver or not report.author_approver.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document correction rejected: Report '{report_id}' lacks a valid authorized approver identity.",
        )

    # 2. Occurrence guard: reject any unresolved PENDING occurrences
    for prop in (report.changes or []):
        for occ in (prop.related_occurrences or []):
            if occ.status == "PENDING":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Document correction rejected: Unresolved PENDING occurrence '{occ.occurrence_id}' "
                        f"detected in proposal '{prop.change_id}'. All occurrences must be explicitly reviewed "
                        "(CONFIRMED or EXCLUDED) before corrected document generation."
                    ),
                )

    # 3. Source document resolution
    if not report.document_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Approved change report '{report_id}' is missing an associated source document_id.",
        )

    store = get_candidate_store()
    source_doc = store.get_source_document(report.document_id)
    if source_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retained source document for document_id '{report.document_id}' not found in candidate store.",
        )

    # 4. Input-only format guards (PDF / legacy DOC)
    eff_fmt = (source_doc.file_format or "").strip().lower().lstrip(".")
    if not eff_fmt and "." in source_doc.filename:
        from pathlib import Path
        eff_fmt = Path(source_doc.filename).suffix.strip().lower().lstrip(".")

    if eff_fmt == "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF format is input-only; in-place PDF document correction is not supported.",
        )
    if eff_fmt == "doc":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Legacy DOC (.doc) format is input-only; direct binary .doc modification is not supported.",
        )

    # 5. Call generator
    try:
        result: CorrectedDocumentResult = corrected_doc_generator.generate_corrected_document(report=report)
    except UnapprovedReportError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except UnresolvedOccurrencesError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except TargetResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Corrected document generation failed: {exc}",
        )

    # 6. Record audit event (idempotent: avoid duplicate audit entries for identical artifact)
    existing_audits = [
        e for e in change_manager.list_audit_events_for_report(report)
        if e.event_type == AuditEventType.CORRECTED_DOCUMENT_GENERATED.value
        and (e.details or {}).get("sha256_hash") == result.sha256_hash
    ]
    if not existing_audits:
        change_manager.record_corrected_document_generated(report=report, result=result)

    # 7. Media type determination
    media_type = "application/octet-stream"
    out_fmt = (result.output_format or "").strip().lower().lstrip(".")
    if out_fmt == "docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif out_fmt in ("txt", "text"):
        media_type = "text/plain; charset=utf-8"
    elif out_fmt == "md":
        media_type = "text/markdown; charset=utf-8"

    return Response(
        content=result.corrected_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.output_filename}"',
        },
    )


@router.get(
    "/history",
    response_model=List[ReviewerDecision],
    summary="Retrieve session decision history",
)
async def list_history() -> List[ReviewerDecision]:
    return change_manager.list_decisions()
