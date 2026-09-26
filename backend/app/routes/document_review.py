"""Document review, human decisions, and controlled change management routes."""

from typing import Any, Dict, List, Optional
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
from app.services.change_manager import ChangeManagerService
from app.services.content_extraction import ContentExtractionService
from app.services.pdf_generator import PDFReportGenerator

router = APIRouter(tags=["Document Review & Change Management"])

extractor = ContentExtractionService()
change_manager = ChangeManagerService()
change_agent = RegulatoryDocumentChangeAgent()
pdf_generator = PDFReportGenerator()


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


@router.post(
    "/documents/upload",
    response_model=List[RegulatoryContentItem],
    summary="Extract regulatory sections from uploaded document text",
)
async def upload_document(payload: DocumentUploadRequest) -> List[RegulatoryContentItem]:
    """Parse raw regulatory document into structured section components."""
    try:
        return extractor.extract_sections_from_text(
            text=payload.content,
            document_name=payload.document_name,
        )
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
        )
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


@router.get(
    "/history",
    response_model=List[ReviewerDecision],
    summary="Retrieve session decision history",
)
async def list_history() -> List[ReviewerDecision]:
    return change_manager.list_decisions()
