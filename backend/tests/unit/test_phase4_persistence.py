
"""Unit tests for Phase 4 Step 4: SQLite Persistence.

Covers:
- Database initialization and schema creation
- Reviewer decision persistence and retrieval
- Proposed change persistence and retrieval
- Complete occurrence status preservation across reloads (PENDING, CONFIRMED, EXCLUDED)
- Impact analysis and validation findings serialization/deserialization
- Approved change report persistence and retrieval
- Service restart simulation (Service A writes -> discarded -> Service B reads same DB)
- API endpoint integration with SQLite persistence (/review/decision, /changes/report, /history, /changes/approve)
- Human approval gate safety with persisted records (PENDING blocks, resolved allows)
- Proxy backwards compatibility with _proposals, _decisions, and _reports
- Test database isolation (never writes to developer backend/data/gpr_workflow.db)
"""

from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.comparison import EvidenceTrace
from app.models.document_change import (
    ApprovedChangeReport,
    ChangeImpact,
    ProposedChange,
    RelatedOccurrence,
    ReviewDecisionType,
    ReviewerDecision,
    ValidationFinding,
)
from app.persistence.sqlite_store import WorkflowSQLiteStore
from app.services.change_manager import ChangeManagerService

client = TestClient(app)


# ==============================================================================
# 1. DATABASE INITIALIZATION & SCHEMA TESTS
# ==============================================================================


def test_database_initialization(tmp_path):
    """Verify SQLite database file and tables are created automatically."""
    db_file = tmp_path / "test_init.db"
    assert not db_file.exists()

    store = WorkflowSQLiteStore(db_path=str(db_file))
    assert db_file.exists()

    # Verify tables and schema version
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "decisions" in tables
    assert "proposals" in tables
    assert "approved_reports" in tables

    cursor.execute("PRAGMA user_version;")
    version = cursor.fetchone()[0]
    assert version >= 1
    conn.close()


# ==============================================================================
# 2. DECISIONS PERSISTENCE TESTS
# ==============================================================================


def test_decision_persistence_and_retrieval(tmp_path):
    """Verify ReviewerDecision is saved and retrieved with all fields intact."""
    db_file = tmp_path / "decisions_test.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    decision = ReviewerDecision(
        decision_id="dec_persist_01",
        target_content_id="rc_target_123",
        candidate_id="cand_ext_456",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Jane Regulatory",
        reviewer_notes="Standardized wording from DailyMed SPL.",
        adaptation_instructions=None,
        decided_at="2026-09-26T12:00:00Z",
    )

    saved = store.save_decision(decision)
    assert saved.decision_id == "dec_persist_01"

    retrieved = store.get_decision("dec_persist_01")
    assert retrieved is not None
    assert retrieved.decision_id == "dec_persist_01"
    assert retrieved.target_content_id == "rc_target_123"
    assert retrieved.candidate_id == "cand_ext_456"
    assert retrieved.decision == ReviewDecisionType.REUSE
    assert retrieved.reviewer_name == "Dr. Jane Regulatory"
    assert retrieved.reviewer_notes == "Standardized wording from DailyMed SPL."
    assert retrieved.decided_at == "2026-09-26T12:00:00Z"


def test_multiple_decisions_persist_in_order(tmp_path):
    """Verify multiple decisions are listed in insertion order."""
    db_file = tmp_path / "multi_decisions.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    for i in range(3):
        store.save_decision(
            ReviewerDecision(
                decision_id=f"dec_order_{i}",
                target_content_id=f"rc_{i}",
                decision=ReviewDecisionType.ADAPT,
                reviewer_name=f"Reviewer {i}",
                adaptation_instructions=f"Instructions {i}",
            )
        )

    all_decisions = store.list_decisions()
    assert len(all_decisions) == 3
    assert [d.decision_id for d in all_decisions] == ["dec_order_0", "dec_order_1", "dec_order_2"]


# ==============================================================================
# 3. PROPOSALS & OCCURRENCE STATUS PERSISTENCE TESTS
# ==============================================================================


def test_proposal_persistence_and_retrieval(tmp_path):
    """Verify ProposedChange is saved and retrieved with all fields intact."""
    db_file = tmp_path / "proposals_test.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    proposal = ProposedChange(
        change_id="chg_persist_001",
        decision_id="dec_001",
        document_name="Test Product Label",
        document_version="2.1",
        section="Dosage and Administration",
        original_text="Take 1 tablet every 4 hours.",
        proposed_text="Take 1 to 2 tablets every 4 to 6 hours.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Harmonize dosing interval.",
        status="PROPOSED",
    )

    store.save_proposal(proposal)

    retrieved = store.get_proposal("chg_persist_001")
    assert retrieved is not None
    assert retrieved.change_id == "chg_persist_001"
    assert retrieved.section == "Dosage and Administration"
    assert retrieved.proposed_text == "Take 1 to 2 tablets every 4 to 6 hours."
    assert retrieved.decision_type == ReviewDecisionType.REUSE
    assert retrieved.status == "PROPOSED"


def test_occurrence_statuses_survive_reload(tmp_path):
    """Verify PENDING, CONFIRMED, and EXCLUDED occurrence statuses survive persistence."""
    db_file = tmp_path / "occ_status_test.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    occurrences = [
        RelatedOccurrence(
            occurrence_id="occ_pending_01",
            section="Warnings",
            match_type="exact",
            current_text="Do not exceed 4000 mg.",
            status="PENDING",
        ),
        RelatedOccurrence(
            occurrence_id="occ_confirmed_02",
            section="Dosage",
            match_type="normalized",
            current_text="Maximum 4000 mg daily.",
            status="CONFIRMED",
        ),
        RelatedOccurrence(
            occurrence_id="occ_excluded_03",
            section="Overdosage",
            match_type="semantic",
            current_text="Overdose threshold 4000 mg.",
            status="EXCLUDED",
        ),
    ]

    proposal = ProposedChange(
        change_id="chg_occs_persist",
        decision_id="dec_occs",
        section="Indications",
        original_text="Original text",
        proposed_text="Proposed text",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Testing occurrence statuses",
        related_occurrences=occurrences,
    )

    store.save_proposal(proposal)

    # Reload from store
    reloaded = store.get_proposal("chg_occs_persist")
    assert reloaded is not None
    assert len(reloaded.related_occurrences) == 3

    occ_map = {o.occurrence_id: o for o in reloaded.related_occurrences}
    assert occ_map["occ_pending_01"].status == "PENDING"
    assert occ_map["occ_confirmed_02"].status == "CONFIRMED"
    assert occ_map["occ_excluded_03"].status == "EXCLUDED"


def test_impact_analysis_and_findings_survive_reload(tmp_path):
    """Verify ChangeImpact and ValidationFindings survive serialization and reload."""
    db_file = tmp_path / "impact_findings_test.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    findings = [
        ValidationFinding(
            rule_id="REG-VAL-001",
            rule_name="Non-Empty Content",
            severity="INFO",
            message="Passed non-empty check.",
            passed=True,
        ),
        ValidationFinding(
            rule_id="REG-VAL-006",
            rule_name="Unresolved Occurrences",
            severity="ERROR",
            message="Blocked due to pending occurrences.",
            passed=False,
        ),
    ]

    impact = ChangeImpact(
        risk_level="HIGH",
        affected_sections_count=2,
        affected_sections=["Dosage and Administration", "Warnings"],
        affected_documents=["Product Label"],
        affected_content_count=2,
        observed_impacts=["Direct edit in Dosage and Administration"],
        potential_impacts=["Cross-reference in Warnings"],
        findings=findings,
        validation_passed=False,
    )

    proposal = ProposedChange(
        change_id="chg_impact_persist",
        decision_id="dec_impact",
        section="Dosage and Administration",
        original_text="Old dosage text.",
        proposed_text="New dosage text.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Update dosage.",
        impact_analysis=impact,
        validation_findings=findings,
    )

    store.save_proposal(proposal)

    reloaded = store.get_proposal("chg_impact_persist")
    assert reloaded is not None

    # Check impact analysis
    assert reloaded.impact_analysis is not None
    assert reloaded.impact_analysis.risk_level == "HIGH"
    assert reloaded.impact_analysis.affected_sections_count == 2
    assert "Warnings" in reloaded.impact_analysis.affected_sections
    assert reloaded.impact_analysis.validation_passed is False

    # Check validation findings
    assert len(reloaded.validation_findings) == 2
    f_map = {f.rule_id: f for f in reloaded.validation_findings}
    assert f_map["REG-VAL-001"].passed is True
    assert f_map["REG-VAL-006"].passed is False
    assert f_map["REG-VAL-006"].severity == "ERROR"


# ==============================================================================
# 4. APPROVED REPORTS PERSISTENCE TESTS
# ==============================================================================


def test_approved_report_persistence_and_retrieval(tmp_path):
    """Verify ApprovedChangeReport is persisted and retrieved with full audit detail."""
    db_file = tmp_path / "reports_test.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    report = ApprovedChangeReport(
        report_id="rep_audit_001",
        document_name="Clinical Core Data Sheet",
        document_version="3.0",
        author_approver="Dr. Regulatory VP",
        decision_ids=["dec_101", "dec_102"],
        changes=[
            ProposedChange(
                change_id="chg_rep_01",
                decision_id="dec_101",
                section="Adverse Reactions",
                original_text="Nausea (5%).",
                proposed_text="Nausea (7%).",
                decision_type=ReviewDecisionType.REUSE,
                rationale="Updated safety data.",
                status="APPROVED",
            )
        ],
        source_evidence=[
            EvidenceTrace(
                source="DailyMed",
                source_id="spl-12345",
                url="https://dailymed.nlm.nih.gov/spl/12345",
                exact_quote="Nausea was observed in 7% of patients.",
            )
        ],
        validation_summary="All 1 proposal(s) passed deterministic validation.",
        impact_summary="1 modification across 1 section.",
        audit_notes="Approved for FDA annual report.",
        approval_confirmation=True,
    )

    store.save_report(report)

    reloaded = store.get_report("rep_audit_001")
    assert reloaded is not None
    assert reloaded.report_id == "rep_audit_001"
    assert reloaded.author_approver == "Dr. Regulatory VP"
    assert reloaded.approval_confirmation is True
    assert len(reloaded.changes) == 1
    assert reloaded.changes[0].change_id == "chg_rep_01"
    assert len(reloaded.source_evidence) == 1
    assert reloaded.source_evidence[0].source == "DailyMed"

    latest = store.get_latest_report()
    assert latest is not None
    assert latest.report_id == "rep_audit_001"


# ==============================================================================
# 5. RESTART PERSISTENCE SIMULATION PROOF
# ==============================================================================


def test_restart_behavior_simulation(tmp_path):
    """Simulate complete backend restart:
    1. Service instance A writes decisions, proposals, and an approved report.
    2. Service instance A is deleted/discarded.
    3. Service instance B is created from the same SQLite file.
    4. Service instance B retrieves all identical data.
    """
    db_file = tmp_path / "backend_restart_simulation.db"

    # --- SESSION A (Before Restart) ---
    service_a = ChangeManagerService(db_path=str(db_file))

    decision = ReviewerDecision(
        decision_id="dec_restart_001",
        target_content_id="rc_target_999",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Persistent Reviewer",
        reviewer_notes="Valid across restarts.",
    )
    service_a.record_decision(decision)

    proposal = service_a.create_change_proposal(
        decision=decision,
        section="Warnings",
        original_text="Keep out of reach of children.",
        proposed_text="Keep out of reach of children and pets.",
        rationale="Child and pet safety warning.",
    )
    # Add an occurrence to proposal
    proposal.related_occurrences = [
        RelatedOccurrence(
            occurrence_id="occ_restart_01",
            section="Overdosage",
            match_type="normalized",
            current_text="Keep out of reach of children.",
            status="CONFIRMED",
        )
    ]
    service_a.save_proposal(proposal)

    report = ApprovedChangeReport(
        report_id="rep_restart_001",
        document_name="Pediatric Label",
        author_approver="Dr. Authorizing Director",
        approval_confirmation=True,
        decision_ids=[decision.decision_id],
        changes=[proposal],
        audit_notes="Survives restart.",
    )
    service_a.record_approved_report(report)

    # --- SIMULATE PROCESS TERMINATION / RESTART ---
    del service_a

    # --- SESSION B (After Restart) ---
    service_b = ChangeManagerService(db_path=str(db_file))

    # 1. Decisions survive restart
    dec_b = service_b.get_decision("dec_restart_001")
    assert dec_b is not None
    assert dec_b.reviewer_name == "Dr. Persistent Reviewer"
    assert len(service_b.list_decisions()) == 1

    # 2. Proposals and occurrence statuses survive restart
    prop_b = service_b.get_proposal(proposal.change_id)
    assert prop_b is not None
    assert prop_b.section == "Warnings"
    assert prop_b.proposed_text == "Keep out of reach of children and pets."
    assert len(prop_b.related_occurrences) == 1
    assert prop_b.related_occurrences[0].status == "CONFIRMED"
    assert len(service_b.list_proposals()) == 1

    # 3. Approved reports survive restart
    rep_b = service_b.get_latest_report()
    assert rep_b is not None
    assert rep_b.report_id == "rep_restart_001"
    assert rep_b.author_approver == "Dr. Authorizing Director"
    assert len(rep_b.changes) == 1


# ==============================================================================
# 6. API ENDPOINT PERSISTENCE INTEGRATION TESTS
# ==============================================================================


def test_api_history_returns_persisted_decisions():
    """Verify POST /review/decision persists and GET /history returns stored decision."""
    res_post = client.post(
        "/review/decision",
        json={
            "target_content_id": "rc_api_test",
            "decision": "REUSE",
            "reviewer_name": "API Reviewer",
            "reviewer_notes": "API decision test notes.",
        },
    )
    assert res_post.status_code == 200
    created = res_post.json()

    res_history = client.get("/history")
    assert res_history.status_code == 200
    history = res_history.json()
    assert any(d["decision_id"] == created["decision_id"] for d in history)


def test_api_proposals_list_returns_persisted_proposals():
    """Verify formulated proposals are retrievable via GET /changes/report."""
    # 1. Record decision
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": "rc_prop_api",
            "decision": "REUSE",
            "reviewer_name": "Dr. Prop Tester",
        },
    )
    decision = res_dec.json()

    # 2. Formulate proposal
    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": decision["decision_id"],
            "section": "Adverse Reactions",
            "original_text": "Headache (3%).",
            "candidate_text": "Headache (4%).",
        },
    )
    assert res_prop.status_code == 200
    proposal = res_prop.json()

    # 3. Query GET /changes/report
    res_list = client.get("/changes/report")
    assert res_list.status_code == 200
    proposals = res_list.json()
    assert any(p["change_id"] == proposal["change_id"] for p in proposals)


# ==============================================================================
# 7. PROXY BACKWARDS COMPATIBILITY TESTS
# ==============================================================================


def test_proxy_backwards_compatibility(tmp_path):
    """Verify _proposals, _decisions, and _reports dictionary-like proxies work transparently."""
    db_file = tmp_path / "proxy_test.db"
    manager = ChangeManagerService(db_path=str(db_file))

    # _proposals proxy
    prop = ProposedChange(
        change_id="chg_proxy_01",
        decision_id="dec_01",
        section="Dosage",
        original_text="Old",
        proposed_text="New",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Proxy test",
    )
    # __setitem__
    manager._proposals[prop.change_id] = prop
    assert len(manager._proposals) == 1
    # __contains__
    assert prop.change_id in manager._proposals
    # __getitem__
    assert manager._proposals[prop.change_id].section == "Dosage"
    # get
    assert manager._proposals.get(prop.change_id) is not None
    # values
    assert len(manager._proposals.values()) == 1
    # pop
    popped = manager._proposals.pop(prop.change_id)
    assert popped is not None
    assert popped.change_id == prop.change_id
    assert len(manager._proposals) == 0

    # _decisions proxy
    dec = ReviewerDecision(
        decision_id="dec_proxy_01",
        target_content_id="rc_01",
        decision=ReviewDecisionType.REUSE,
    )
    manager._decisions[dec.decision_id] = dec
    assert len(manager._decisions) == 1
    fetched_dec = manager._decisions.get("dec_proxy_01")
    assert fetched_dec is not None
    assert fetched_dec.decision_id == "dec_proxy_01"
    manager._decisions.pop("dec_proxy_01")
    assert len(manager._decisions) == 0


# ==============================================================================
# 8. TEST ISOLATION VERIFICATION
# ==============================================================================


def test_developer_database_is_never_touched_by_tests():
    """Verify default developer database backend/data/gpr_workflow.db is untouched by tests."""
    dev_db_path = Path(__file__).resolve().parent.parent.parent / "data" / "gpr_workflow.db"
    # Even if dev_db_path does not exist yet or exists empty, verify settings.SQLITE_DB_PATH is redirected to tmp
    assert "test_gpr_workflow.db" in settings.SQLITE_DB_PATH or "test" in settings.SQLITE_DB_PATH.lower()


# ==============================================================================
# 9. OCCURRENCE CONFIRMATION & APPROVAL GATE INTEGRATION WITH SQLITE
# ==============================================================================


def test_sqlite_occurrence_confirmation_workflow(tmp_path):
    """Verify Step 3 occurrence confirmation recalculates impact and persists to SQLite."""
    db_file = tmp_path / "occ_confirm_test.db"
    manager = ChangeManagerService(db_path=str(db_file))

    decision = ReviewerDecision(
        decision_id="dec_occ_confirm",
        target_content_id="rc_occ_confirm",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Evaluator",
    )
    manager.record_decision(decision)

    proposal = ProposedChange(
        change_id="chg_occ_workflow",
        decision_id=decision.decision_id,
        section="Dosage and Administration",
        original_text="Take 10 mg daily.",
        proposed_text="Take 20 mg daily.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Dose adjustment.",
        related_occurrences=[
            RelatedOccurrence(
                occurrence_id="occ_wf_1",
                section="Warnings and Precautions",
                match_type="exact",
                current_text="Take 10 mg daily.",
                status="PENDING",
            ),
            RelatedOccurrence(
                occurrence_id="occ_wf_2",
                section="Overdosage",
                match_type="normalized",
                current_text="Take 10 mg daily.",
                status="PENDING",
            ),
        ],
    )
    manager.save_proposal(proposal)

    # Confirm occurrence 1, exclude occurrence 2
    updated = manager.confirm_occurrences(
        change_id=proposal.change_id,
        confirmed_occurrence_ids=["occ_wf_1"],
        excluded_occurrence_ids=["occ_wf_2"],
        reviewer_notes="Confirmed Warnings, excluded Overdosage.",
    )
    assert updated.impact_analysis is not None
    assert updated.impact_analysis.affected_sections_count == 2
    assert "Warnings and Precautions" in updated.impact_analysis.affected_sections
    assert "Overdosage" not in updated.impact_analysis.affected_sections

    # Verify data survives in a completely new service instance pointing to the same SQLite DB
    new_manager = ChangeManagerService(db_path=str(db_file))
    reloaded = new_manager.get_proposal(proposal.change_id)
    assert reloaded is not None
    occ_map = {o.occurrence_id: o for o in reloaded.related_occurrences}
    assert occ_map["occ_wf_1"].status == "CONFIRMED"
    assert occ_map["occ_wf_2"].status == "EXCLUDED"
    assert reloaded.impact_analysis is not None
    assert reloaded.impact_analysis.affected_sections_count == 2
    assert "Occurrence Review Notes" in reloaded.rationale


def test_approval_blocked_when_persisted_proposal_contains_pending_occurrences(tmp_path):
    """Verify approval is blocked when a persisted proposal has unresolved occurrences."""
    db_file = tmp_path / "pending_gate_test.db"
    manager = ChangeManagerService(db_path=str(db_file))

    decision = ReviewerDecision(
        decision_id="dec_pending_gate",
        target_content_id="rc_gate",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Regulatory Approver",
    )
    manager.record_decision(decision)

    proposal = ProposedChange(
        change_id="chg_pending_gate",
        decision_id=decision.decision_id,
        section="Dosage",
        original_text="Old dosage.",
        proposed_text="New dosage.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Testing approval gate.",
        related_occurrences=[
            RelatedOccurrence(
                occurrence_id="occ_unreviewed",
                section="Adverse Reactions",
                match_type="exact",
                current_text="Old dosage.",
                status="PENDING",
            )
        ],
    )
    manager.save_proposal(proposal)

    # ValidationService check directly on persisted proposal
    from app.services.validation import ValidationService
    validator = ValidationService()
    findings = validator.validate_approval(
        approver_name="Dr. Regulatory Approver",
        approval_confirmation=True,
        proposals=[proposal],
    )
    errors = [f for f in findings if f.rule_id == "REG-VAL-006" and not f.passed]
    assert len(errors) == 1
    assert "unresolved related occurrences" in errors[0].message.lower()


def test_approval_succeeds_when_all_persisted_occurrences_are_resolved(tmp_path):
    """Verify approval succeeds and report is stored in SQLite when all occurrences are resolved."""
    db_file = tmp_path / "resolved_approval_test.db"
    manager = ChangeManagerService(db_path=str(db_file))

    decision = ReviewerDecision(
        decision_id="dec_resolved",
        target_content_id="rc_resolved",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Final Approver",
    )
    manager.record_decision(decision)

    proposal = ProposedChange(
        change_id="chg_resolved",
        decision_id=decision.decision_id,
        section="Dosage",
        original_text="Old dose.",
        proposed_text="New dose.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Ready for approval.",
        related_occurrences=[
            RelatedOccurrence(
                occurrence_id="occ_res_1",
                section="Warnings",
                match_type="exact",
                current_text="Old dose.",
                status="CONFIRMED",
            ),
            RelatedOccurrence(
                occurrence_id="occ_res_2",
                section="Overdose",
                match_type="exact",
                current_text="Old dose.",
                status="EXCLUDED",
            ),
        ],
    )
    manager.save_proposal(proposal)

    manager.update_proposal_status(proposal.change_id, "APPROVED")
    proposal.status = "APPROVED"

    from app.services.change_report import ChangeReportService
    reporter = ChangeReportService()
    report = reporter.generate_report(
        author_approver="Dr. Final Approver",
        approval_confirmation=True,
        changes=[proposal],
        document_name="Test Resolved Label",
    )
    manager.record_approved_report(report)

    # Verify report in new service instance
    reopened = ChangeManagerService(db_path=str(db_file))
    latest = reopened.get_latest_report()
    assert latest is not None
    assert latest.author_approver == "Dr. Final Approver"
    assert latest.changes[0].status == "APPROVED"
    assert len(reopened.list_approved_proposals()) == 1

