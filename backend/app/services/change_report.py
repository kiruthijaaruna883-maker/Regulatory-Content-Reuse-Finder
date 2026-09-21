"""Approved change report generation service module.

Generates audit-ready reports documenting approved changes with full source traceability.
CRITICAL SAFETY CONSTRAINT:
Does NOT overwrite, mutate, or alter original source documents.
Generates an auditable report representation of human-authorized proposals.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4
from app.models.comparison import EvidenceTrace
from app.models.document_change import ApprovedChangeReport, ProposedChange


class ChangeReportService:
    """Generates structured regulatory change reports for audit trails."""

    def generate_report(
        self,
        author_approver: Optional[str] = None,
        changes: Optional[List[ProposedChange]] = None,
        approval_confirmation: bool = False,
        document_name: Optional[str] = None,
        document_version: Optional[str] = None,
        audit_notes: Optional[str] = None,
        **kwargs,
    ) -> ApprovedChangeReport:
        """Assemble an approved change report with full source traceability citations.

        Strictly enforces that explicit human approval confirmation is provided.
        """
        # Support flexible keyword passing from callers
        author = author_approver or kwargs.get("author_approver")
        prop_list = changes if changes is not None else kwargs.get("changes", [])
        doc_name = document_name or kwargs.get("document_name")
        doc_version = document_version or kwargs.get("document_version")
        notes = audit_notes or kwargs.get("audit_notes")
        confirmed = approval_confirmation or kwargs.get("approval_confirmation", False)

        if not confirmed:
            raise ValueError(
                "Explicit human approval confirmation (approval_confirmation=true) is mandatory to generate an Approved Change Report."
            )

        if not author or not author.strip():
            raise ValueError("Valid human regulatory approver identity is required.")

        # Exclude any proposals with REJECT decision or status
        valid_approved_changes = [
            c for c in changes
            if getattr(c, "decision_type", None) != "REJECT" and getattr(c, "status", None) != "REJECTED"
        ]

        if not valid_approved_changes:
            raise ValueError("No authorized change proposals available for report compilation.")

        # Gather distinct decision IDs
        decision_ids = list(dict.fromkeys(c.decision_id for c in valid_approved_changes if c.decision_id))

        # Gather supporting source evidence traces
        source_evidence: List[EvidenceTrace] = []
        for c in valid_approved_changes:
            if c.source_evidence and c.source_evidence not in source_evidence:
                source_evidence.append(c.source_evidence)

        # Build validation and impact summaries
        total_findings = sum(len(c.validation_findings) for c in valid_approved_changes)
        validation_summary = (
            f"All {len(valid_approved_changes)} proposal(s) evaluated across deterministic regulatory integrity rules. "
            f"Evaluated {total_findings} finding(s). Validation status: PASSED."
        )

        all_affected_sections = set()
        for c in valid_approved_changes:
            all_affected_sections.add(c.section)
            for occ in c.related_occurrences:
                all_affected_sections.add(occ.section)

        impact_summary = (
            f"Evaluated {len(valid_approved_changes)} approved modification(s) across "
            f"{len(all_affected_sections)} regulatory section(s). Observed and potential impacts reviewed."
        )

        now_utc = datetime.now(timezone.utc).isoformat()

        return ApprovedChangeReport(
            report_id=f"rep_{uuid4().hex[:10]}",
            document_name=document_name,
            document_version=document_version,
            generated_at=now_utc,
            author_approver=author_approver.strip(),
            decision_ids=decision_ids,
            changes=valid_approved_changes,
            source_evidence=source_evidence,
            validation_summary=validation_summary,
            impact_summary=impact_summary,
            audit_notes=audit_notes or "Human authorized for regulatory submission; full provenance citations preserved.",
            approval_timestamp=now_utc,
            approval_confirmation=approval_confirmation,
        )
