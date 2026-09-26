"""Controlled change management service module.

Manages human regulatory professional decisions (Reuse, Adapt, Reject) and maintains
the controlled revision lifecycle. Never autonomously applies regulatory changes.
Durable persistence backed by SQLite through standard-library sqlite3.
"""

from typing import Any, Dict, List, Optional
from app.models.audit import (
    AuditEvent,
    AuditEventType,
    AuditVerificationResult,
)
from app.models.document_change import (
    ApprovedChangeReport,
    ChangeImpact,
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
        saved = self.store.save_decision(decision)
        decision_val = (
            decision.decision.value
            if hasattr(decision.decision, "value")
            else str(decision.decision)
        )
        self.store.append_audit_event(
            event_type=AuditEventType.REVIEWER_DECISION_CREATED.value,
            decision_id=decision.decision_id,
            reviewer_name=decision.reviewer_name,
            new_status=decision_val,
            details={
                "target_content_id": decision.target_content_id,
                "candidate_id": decision.candidate_id,
                "decision": decision_val,
                "notes": decision.reviewer_notes,
                "adaptation_instructions": decision.adaptation_instructions,
            },
            previous_state=None,
            new_state={
                "decision_id": decision.decision_id,
                "decision": decision_val,
                "target_content_id": decision.target_content_id,
                "candidate_id": decision.candidate_id,
            },
        )
        return saved

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
        return self.save_proposal(proposal)

    def save_proposal(
        self,
        proposal: ProposedChange,
        emit_audit: bool = True,
    ) -> ProposedChange:
        """Persist or update an existing change proposal and emit audit event if new."""
        existing = self.get_proposal(proposal.change_id)
        is_new = existing is None
        saved = self.store.save_proposal(proposal)
        if is_new and emit_audit:
            decision_type_val = (
                saved.decision_type.value
                if hasattr(saved.decision_type, "value")
                else str(saved.decision_type)
            )
            self.store.append_audit_event(
                event_type=AuditEventType.CHANGE_PROPOSAL_CREATED.value,
                change_id=saved.change_id,
                decision_id=saved.decision_id,
                new_status=saved.status,
                details={
                    "section": saved.section,
                    "document_name": saved.document_name,
                    "document_version": saved.document_version,
                    "decision_type": decision_type_val,
                    "rationale": saved.rationale,
                    "related_occurrences_count": len(saved.related_occurrences),
                },
                previous_state=None,
                new_state={
                    "change_id": saved.change_id,
                    "status": saved.status,
                    "section": saved.section,
                },
            )
        return saved

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

        # Capture previous occurrence state snapshot
        prev_occ_state = {occ.occurrence_id: occ.status for occ in proposal.related_occurrences}

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

        # Save back to SQLite store (emit_audit=False to avoid duplicate proposal created events)
        saved = self.store.save_proposal(proposal)

        # Capture new occurrence state snapshot
        new_occ_state = {occ.occurrence_id: occ.status for occ in saved.related_occurrences}

        affected_count = (
            saved.impact_analysis.affected_sections_count
            if saved.impact_analysis and hasattr(saved.impact_analysis, "affected_sections_count")
            else None
        )
        self.store.append_audit_event(
            event_type=AuditEventType.OCCURRENCES_CONFIRMED.value,
            change_id=saved.change_id,
            decision_id=saved.decision_id,
            details={
                "confirmed_occurrence_ids": sorted(list(confirmed_set)),
                "excluded_occurrence_ids": sorted(list(excluded_set)),
                "reviewer_notes": reviewer_notes,
                "affected_sections_count": affected_count,
            },
            previous_state=prev_occ_state,
            new_state=new_occ_state,
        )

        return saved

    def update_proposal_status(
        self,
        change_id: str,
        status: str,
        reviewer_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[ProposedChange]:
        """Update proposal status (PROPOSED, PENDING_APPROVAL, APPROVED, REJECTED)."""
        prop = self.get_proposal(change_id)
        if prop:
            old_status = prop.status
            prop.status = status
            self.store.save_proposal(prop)
            if status == "APPROVED":
                self.store.append_audit_event(
                    event_type=AuditEventType.CHANGE_APPROVED.value,
                    change_id=prop.change_id,
                    decision_id=prop.decision_id,
                    reviewer_name=reviewer_name,
                    previous_status=old_status,
                    new_status=status,
                    details={"reviewer_notes": notes, "section": prop.section},
                    previous_state={"status": old_status},
                    new_state={"status": status},
                )
            elif status == "REJECTED":
                self.store.append_audit_event(
                    event_type=AuditEventType.CHANGE_REJECTED.value,
                    change_id=prop.change_id,
                    decision_id=prop.decision_id,
                    reviewer_name=reviewer_name,
                    previous_status=old_status,
                    new_status=status,
                    details={"reviewer_notes": notes, "section": prop.section},
                    previous_state={"status": old_status},
                    new_state={"status": status},
                )
        return prop

    def record_validation(
        self,
        proposal: ProposedChange,
        impact: ChangeImpact,
    ) -> AuditEvent:
        """Record validation check execution for a change proposal."""
        prev_passed = None
        if proposal.impact_analysis is not None:
            if hasattr(proposal.impact_analysis, "validation_passed"):
                prev_passed = proposal.impact_analysis.validation_passed
            elif isinstance(proposal.impact_analysis, dict):
                prev_passed = proposal.impact_analysis.get("validation_passed")

        return self.store.append_audit_event(
            event_type=AuditEventType.CHANGE_VALIDATED.value,
            change_id=proposal.change_id,
            decision_id=proposal.decision_id,
            details={
                "risk_level": impact.risk_level,
                "validation_passed": impact.validation_passed,
                "affected_sections_count": impact.affected_sections_count,
                "findings_count": len(impact.findings),
            },
            previous_state={"validation_passed": prev_passed},
            new_state={
                "validation_passed": impact.validation_passed,
                "risk_level": impact.risk_level,
            },
        )

    def list_proposals(self) -> List[ProposedChange]:
        """List all controlled change proposals."""
        return self.store.list_proposals()

    def list_approved_proposals(self) -> List[ProposedChange]:
        """List proposals that have been explicitly approved."""
        return self.store.list_proposals(status="APPROVED")

    def record_approved_report(self, report: ApprovedChangeReport) -> ApprovedChangeReport:
        """Persist authorized Approved Change Report and emit audit event."""
        saved = self.store.save_report(report)
        self.store.append_audit_event(
            event_type=AuditEventType.APPROVED_REPORT_CREATED.value,
            report_id=report.report_id,
            reviewer_name=report.author_approver,
            details={
                "document_name": report.document_name,
                "document_version": report.document_version,
                "author_approver": report.author_approver,
                "decision_ids": report.decision_ids,
                "changes_count": len(report.changes),
                "audit_notes": report.audit_notes,
                "approval_confirmation": report.approval_confirmation,
            },
            previous_state=None,
            new_state={
                "report_id": report.report_id,
                "author_approver": report.author_approver,
                "changes_count": len(report.changes),
            },
        )
        return saved

    def get_latest_report(self) -> Optional[ApprovedChangeReport]:
        """Retrieve most recently generated report."""
        return self.store.get_latest_report()

    def get_report(self, report_id: str) -> Optional[ApprovedChangeReport]:
        """Retrieve an approved change report by ID."""
        return self.store.get_report(report_id)

    def list_audit_events_for_report(self, report: ApprovedChangeReport) -> List[AuditEvent]:
        """Retrieve chronological audit events associated with an approved report and its changes."""
        change_ids = {c.change_id for c in report.changes if getattr(c, "change_id", None)}
        decision_ids = set(report.decision_ids or []) | {
            c.decision_id for c in report.changes if getattr(c, "decision_id", None)
        }
        all_events = self.store.list_audit_events()
        relevant_events = [
            e for e in all_events
            if (e.report_id == report.report_id)
            or (e.change_id and e.change_id in change_ids)
            or (e.decision_id and e.decision_id in decision_ids)
        ]
        return relevant_events

    def list_audit_events(self, limit: Optional[int] = None) -> List[AuditEvent]:
        """Retrieve audit history in chronological append order."""
        return self.store.list_audit_events(limit=limit)

    def list_audit_events_by_change(self, change_id: str) -> List[AuditEvent]:
        """Retrieve audit events linked to a specific change proposal."""
        return self.store.list_audit_events_by_change(change_id)

    def get_latest_audit_event(self) -> Optional[AuditEvent]:
        """Retrieve latest audit event in the chain."""
        return self.store.get_latest_audit_event()

    def verify_audit_trail(self) -> AuditVerificationResult:
        """Verify SHA-256 hash-chain integrity across all workflow audit events."""
        return self.store.verify_hash_chain()

    def clear_session(self) -> None:
        """Reset workflow storage."""
        self.store.clear_all()
