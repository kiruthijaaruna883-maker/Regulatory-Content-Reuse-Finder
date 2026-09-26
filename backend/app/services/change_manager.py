"""Controlled change management service module.

Manages human regulatory professional decisions (Reuse, Adapt, Reject) and maintains
the controlled revision lifecycle. Never autonomously applies regulatory changes.
"""

from typing import Dict, List, Optional
from app.models.document_change import (
    ApprovedChangeReport,
    ProposedChange,
    ReviewDecisionType,
    ReviewerDecision,
)


class ChangeManagerService:
    """Manages reviewer decisions, proposal tracking, and authorized audit reports."""

    def __init__(self):
        # In-memory storage for active session
        self._decisions: Dict[str, ReviewerDecision] = {}
        self._proposals: Dict[str, ProposedChange] = {}
        self._reports: Dict[str, ApprovedChangeReport] = {}

    def record_decision(self, decision: ReviewerDecision) -> ReviewerDecision:
        """Record a human regulatory professional's decision.

        Auditable for all decision types (REUSE, ADAPT, REJECT).
        """
        self._decisions[decision.decision_id] = decision
        return decision

    def list_decisions(self) -> List[ReviewerDecision]:
        """List all recorded decisions in the current session."""
        return list(self._decisions.values())

    def get_decision(self, decision_id: str) -> Optional[ReviewerDecision]:
        """Fetch a specific decision by ID."""
        return self._decisions.get(decision_id)

    def create_change_proposal(
        self,
        decision: ReviewerDecision,
        section: str,
        original_text: str,
        proposed_text: str,
        rationale: str,
        document_name: Optional[str] = None,
        document_version: Optional[str] = None,
    ) -> ProposedChange:
        """Formulate a controlled change proposal from a REUSE or ADAPT decision.

        MANDATORY GOVERNANCE:
        REJECT decisions must NEVER create a change proposal for approval.
        """
        if decision.decision == ReviewDecisionType.REJECT:
            raise ValueError(
                "Cannot create a change proposal for a REJECT decision. "
                "Original document content is strictly preserved."
            )

        proposal = ProposedChange(
            decision_id=decision.decision_id,
            document_name=document_name,
            document_version=document_version,
            section=section,
            original_text=original_text,
            proposed_text=proposed_text,
            decision_type=decision.decision,
            rationale=rationale,
            status="PROPOSED",
        )
        self._proposals[proposal.change_id] = proposal
        return proposal

    def get_proposal(self, change_id: str) -> Optional[ProposedChange]:
        """Fetch proposal by ID."""
        return self._proposals.get(change_id)

    def confirm_occurrences(
        self,
        change_id: str,
        confirmed_occurrence_ids: List[str],
        excluded_occurrence_ids: List[str],
        reviewer_notes: Optional[str] = None,
    ) -> ProposedChange:
        """Record reviewer confirmation or exclusion for detected related occurrences.

        Validates proposal, verifies occurrence ownership, updates statuses,
        and recalculates impact analysis.
        """
        proposal = self.get_proposal(change_id)
        if not proposal:
            raise KeyError(f"Proposal ID '{change_id}' not found.")

        # Guard: REJECT decisions or REJECTED status cannot receive occurrence confirmations
        if proposal.decision_type == ReviewDecisionType.REJECT or proposal.status == "REJECTED":
            raise ValueError(f"Cannot confirm occurrences for proposal '{change_id}' linked to a REJECT decision.")

        confirmed_set = set(confirmed_occurrence_ids or [])
        excluded_set = set(excluded_occurrence_ids or [])

        # Check: overlap between confirmed and excluded
        overlap = confirmed_set & excluded_set
        if overlap:
            raise ValueError(
                f"Occurrence IDs cannot be simultaneously confirmed and excluded: {sorted(list(overlap))}"
            )

        # Check: all supplied occurrence IDs actually belong to this proposal
        proposal_occ_map = {occ.occurrence_id: occ for occ in proposal.related_occurrences}
        all_supplied_ids = confirmed_set | excluded_set
        unknown_ids = all_supplied_ids - set(proposal_occ_map.keys())
        if unknown_ids:
            raise ValueError(
                f"Unknown occurrence IDs do not belong to proposal '{change_id}': {sorted(list(unknown_ids))}"
            )

        # Update occurrence statuses
        for occ_id in confirmed_set:
            proposal_occ_map[occ_id].status = "CONFIRMED"
        for occ_id in excluded_set:
            proposal_occ_map[occ_id].status = "EXCLUDED"

        if reviewer_notes and reviewer_notes.strip():
            proposal.rationale = f"{proposal.rationale} [Occurrence Review Notes: {reviewer_notes.strip()}]"

        # Recalculate impact analysis & validation
        from app.services.validation import ValidationService
        validator = ValidationService()
        impact = validator.validate_proposal(proposal)
        proposal.impact_analysis = impact
        proposal.validation_findings = impact.findings

        # Save back to in-memory store
        self._proposals[proposal.change_id] = proposal
        return proposal

    def update_proposal_status(self, change_id: str, status: str) -> Optional[ProposedChange]:
        """Update proposal status (PROPOSED, PENDING_APPROVAL, APPROVED, REJECTED)."""
        prop = self._proposals.get(change_id)
        if prop:
            prop.status = status
        return prop

    def list_proposals(self) -> List[ProposedChange]:
        """List all controlled change proposals."""
        return list(self._proposals.values())

    def list_approved_proposals(self) -> List[ProposedChange]:
        """List proposals that have been explicitly approved."""
        return [p for p in self._proposals.values() if p.status == "APPROVED"]

    def record_approved_report(self, report: ApprovedChangeReport) -> ApprovedChangeReport:
        """Persist authorized Approved Change Report in session."""
        self._reports[report.report_id] = report
        return report

    def get_latest_report(self) -> Optional[ApprovedChangeReport]:
        """Retrieve most recently generated report."""
        if not self._reports:
            return None
        return list(self._reports.values())[-1]

    def clear_session(self) -> None:
        """Reset session storage."""
        self._decisions.clear()
        self._proposals.clear()
        self._reports.clear()
