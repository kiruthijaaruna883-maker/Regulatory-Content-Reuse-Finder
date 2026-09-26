"""Controlled change management service module.

Manages human regulatory professional decisions (Reuse, Adapt, Reject) and maintains
the controlled revision lifecycle. Never autonomously applies regulatory changes.
Durable persistence backed by SQLite through standard-library sqlite3.
"""

from typing import Any, Dict, List, Optional
from app.models.document_change import (
    ApprovedChangeReport,
    ProposedChange,
    ReviewDecisionType,
    ReviewerDecision,
)
from app.persistence.sqlite_store import WorkflowSQLiteStore


class _ProposalsProxy:
    """Dict-like proxy to maintain backwards compatibility with _proposals access."""

    def __init__(self, store: WorkflowSQLiteStore):
        self._store = store

    def __getitem__(self, change_id: str) -> ProposedChange:
        p = self._store.get_proposal(change_id)
        if p is None:
            raise KeyError(change_id)
        return p

    def __setitem__(self, change_id: str, proposal: ProposedChange) -> None:
        self._store.save_proposal(proposal)

    def __delitem__(self, change_id: str) -> None:
        if not self._store.delete_proposal(change_id):
            raise KeyError(change_id)

    def get(self, change_id: str, default: Optional[ProposedChange] = None) -> Optional[ProposedChange]:
        p = self._store.get_proposal(change_id)
        return p if p is not None else default

    def values(self) -> List[ProposedChange]:
        return self._store.list_proposals()

    def keys(self) -> List[str]:
        return [p.change_id for p in self._store.list_proposals()]

    def items(self):
        return [(p.change_id, p) for p in self._store.list_proposals()]

    def pop(self, change_id: str, default=None):
        p = self._store.get_proposal(change_id)
        if p is not None:
            self._store.delete_proposal(change_id)
            return p
        return default

    def clear(self) -> None:
        self._store.clear_proposals()

    def __len__(self) -> int:
        return len(self._store.list_proposals())

    def __contains__(self, change_id: str) -> bool:
        return self._store.get_proposal(change_id) is not None

    def __iter__(self):
        return iter(self.keys())


class _DecisionsProxy:
    """Dict-like proxy to maintain backwards compatibility with _decisions access."""

    def __init__(self, store: WorkflowSQLiteStore):
        self._store = store

    def __getitem__(self, decision_id: str) -> ReviewerDecision:
        d = self._store.get_decision(decision_id)
        if d is None:
            raise KeyError(decision_id)
        return d

    def __setitem__(self, decision_id: str, decision: ReviewerDecision) -> None:
        self._store.save_decision(decision)

    def __delitem__(self, decision_id: str) -> None:
        if not self._store.delete_decision(decision_id):
            raise KeyError(decision_id)

    def get(self, decision_id: str, default: Optional[ReviewerDecision] = None) -> Optional[ReviewerDecision]:
        d = self._store.get_decision(decision_id)
        return d if d is not None else default

    def values(self) -> List[ReviewerDecision]:
        return self._store.list_decisions()

    def keys(self) -> List[str]:
        return [d.decision_id for d in self._store.list_decisions()]

    def items(self):
        return [(d.decision_id, d) for d in self._store.list_decisions()]

    def pop(self, decision_id: str, default=None):
        d = self._store.get_decision(decision_id)
        if d is not None:
            self._store.delete_decision(decision_id)
            return d
        return default

    def clear(self) -> None:
        self._store.clear_decisions()

    def __len__(self) -> int:
        return len(self._store.list_decisions())

    def __contains__(self, decision_id: str) -> bool:
        return self._store.get_decision(decision_id) is not None

    def __iter__(self):
        return iter(self.keys())


class _ReportsProxy:
    """Dict-like proxy to maintain backwards compatibility with _reports access."""

    def __init__(self, store: WorkflowSQLiteStore):
        self._store = store

    def __getitem__(self, report_id: str) -> ApprovedChangeReport:
        r = self._store.get_report(report_id)
        if r is None:
            raise KeyError(report_id)
        return r

    def __setitem__(self, report_id: str, report: ApprovedChangeReport) -> None:
        self._store.save_report(report)

    def __delitem__(self, report_id: str) -> None:
        if not self._store.delete_report(report_id):
            raise KeyError(report_id)

    def get(self, report_id: str, default: Optional[ApprovedChangeReport] = None) -> Optional[ApprovedChangeReport]:
        r = self._store.get_report(report_id)
        return r if r is not None else default

    def values(self) -> List[ApprovedChangeReport]:
        return self._store.list_reports()

    def keys(self) -> List[str]:
        return [r.report_id for r in self._store.list_reports()]

    def items(self):
        return [(r.report_id, r) for r in self._store.list_reports()]

    def pop(self, report_id: str, default=None):
        r = self._store.get_report(report_id)
        if r is not None:
            self._store.delete_report(report_id)
            return r
        return default

    def clear(self) -> None:
        self._store.clear_reports()

    def __len__(self) -> int:
        return len(self._store.list_reports())

    def __contains__(self, report_id: str) -> bool:
        return self._store.get_report(report_id) is not None

    def __iter__(self):
        return iter(self.keys())


class ChangeManagerService:
    """Manages reviewer decisions, proposal tracking, and authorized audit reports.

    Backed by durable SQLite persistence while preserving full service contract.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.store = WorkflowSQLiteStore(db_path=db_path)
        self._decisions = _DecisionsProxy(self.store)
        self._proposals = _ProposalsProxy(self.store)
        self._reports = _ReportsProxy(self.store)

    def record_decision(self, decision: ReviewerDecision) -> ReviewerDecision:
        """Record a human regulatory professional's decision.

        Auditable for all decision types (REUSE, ADAPT, REJECT).
        """
        return self.store.save_decision(decision)

    def list_decisions(self) -> List[ReviewerDecision]:
        """List all recorded decisions in insertion order."""
        return self.store.list_decisions()

    def get_decision(self, decision_id: str) -> Optional[ReviewerDecision]:
        """Fetch a specific decision by ID."""
        return self.store.get_decision(decision_id)

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
        return self.store.save_proposal(proposal)

    def save_proposal(self, proposal: ProposedChange) -> ProposedChange:
        """Persist or update an existing change proposal."""
        return self.store.save_proposal(proposal)

    def get_proposal(self, change_id: str) -> Optional[ProposedChange]:
        """Fetch proposal by ID."""
        return self.store.get_proposal(change_id)

    def confirm_occurrences(
        self,
        change_id: str,
        confirmed_occurrence_ids: List[str],
        excluded_occurrence_ids: List[str],
        reviewer_notes: Optional[str] = None,
    ) -> ProposedChange:
        """Record reviewer confirmation or exclusion for detected related occurrences.

        Validates proposal, verifies occurrence ownership, updates statuses,
        recalculates impact analysis, and persists to SQLite.
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

        # Save back to SQLite store
        return self.store.save_proposal(proposal)

    def update_proposal_status(self, change_id: str, status: str) -> Optional[ProposedChange]:
        """Update proposal status (PROPOSED, PENDING_APPROVAL, APPROVED, REJECTED)."""
        prop = self.get_proposal(change_id)
        if prop:
            prop.status = status
            self.store.save_proposal(prop)
        return prop

    def list_proposals(self) -> List[ProposedChange]:
        """List all controlled change proposals."""
        return self.store.list_proposals()

    def list_approved_proposals(self) -> List[ProposedChange]:
        """List proposals that have been explicitly approved."""
        return self.store.list_proposals(status="APPROVED")

    def record_approved_report(self, report: ApprovedChangeReport) -> ApprovedChangeReport:
        """Persist authorized Approved Change Report."""
        return self.store.save_report(report)

    def get_latest_report(self) -> Optional[ApprovedChangeReport]:
        """Retrieve most recently generated report."""
        return self.store.get_latest_report()

    def clear_session(self) -> None:
        """Reset workflow storage."""
        self.store.clear_all()
