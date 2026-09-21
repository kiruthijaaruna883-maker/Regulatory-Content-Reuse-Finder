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
