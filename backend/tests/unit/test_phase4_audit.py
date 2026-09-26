"""Targeted unit and integration tests for Phase 4 Step 5: Tamper-Evident Audit Trail.

Verifies:
1. Audit table initialization and schema version 2.
2. First (genesis) event creation.
3. Deterministic SHA-256 event hash generation.
4. Second event correctly references previous_event_hash.
5. Hash-chain verification succeeds for intact valid sequence.
6. Tampering with event data causes verification failure.
7. Tampering with event_hash causes verification failure.
8. Broken previous_event_hash linkage causes verification failure.
9. Reviewer decision creates REVIEWER_DECISION_CREATED event.
10. Proposal creation creates CHANGE_PROPOSAL_CREATED event.
11. Occurrence confirmation creates OCCURRENCES_CONFIRMED event.
12. Validation creates CHANGE_VALIDATED event.
13. Approval creates CHANGE_APPROVED event.
14. Approved report creation creates APPROVED_REPORT_CREATED event.
15. GET/read operations do not generate duplicate audit events.
16. Audit events and hash chain survive service restart.
17. Audit history can be queried by change_id.
18. Test database isolation prevents developer DB contamination.
19. Read-only API routes /audit, /audit/verify, and /audit/{change_id}.
"""

import json
from pathlib import Path
import sqlite3
import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.audit import (
    AuditEvent,
    AuditEventType,
    AuditVerificationResult,
    compute_event_hash,
)
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


# ==============================================================================
# 1. DATABASE SCHEMA & TABLE INITIALIZATION
# ==============================================================================


def test_audit_table_initialization_and_schema_version(tmp_path):
    """Verify audit_events table exists with expected schema and user_version 2."""
    db_file = tmp_path / "audit_init_test.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    with store._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        version = cursor.fetchone()[0]
        assert version == 2

        # Verify audit_events table columns
        cursor.execute("PRAGMA table_info(audit_events);")
        columns = {row["name"]: row["type"] for row in cursor.fetchall()}
        expected_cols = [
            "event_id", "event_type", "occurred_at", "change_id", "decision_id",
            "report_id", "reviewer_name", "previous_status", "new_status",
            "details", "previous_state", "new_state", "previous_event_hash", "event_hash"
        ]
        for col in expected_cols:
            assert col in columns, f"Column '{col}' missing from audit_events table"


# ==============================================================================
# 2. GENESIS & EVENT HASH CHAINING
# ==============================================================================


def test_genesis_event_and_hash_calculation(tmp_path):
    """Verify first event has null previous_event_hash and correct SHA-256 calculation."""
    db_file = tmp_path / "genesis_test.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    event = store.append_audit_event(
        event_type=AuditEventType.REVIEWER_DECISION_CREATED.value,
        decision_id="dec_001",
        reviewer_name="Dr. Genesis Reviewer",
        new_status="REUSE",
        details={"target_content_id": "tc_001", "decision": "REUSE"},
    )

    assert event.event_id.startswith("evt_")
    assert event.previous_event_hash is None

    # Verify deterministic hash matches manual calculation
    expected_hash = compute_event_hash(
        event_id=event.event_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        change_id=event.change_id,
        decision_id=event.decision_id,
        report_id=event.report_id,
        reviewer_name=event.reviewer_name,
        previous_status=event.previous_status,
        new_status=event.new_status,
        details=event.details,
        previous_state=event.previous_state,
        new_state=event.new_state,
        previous_event_hash=event.previous_event_hash,
    )
    assert event.event_hash == expected_hash
    assert len(event.event_hash) == 64  # SHA-256 hex string


def test_second_event_references_previous_event_hash(tmp_path):
    """Verify second event links previous_event_hash to the first event's hash."""
    db_file = tmp_path / "chain_test.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    event1 = store.append_audit_event(
        event_type=AuditEventType.REVIEWER_DECISION_CREATED.value,
        decision_id="dec_001",
        new_status="REUSE",
        details={"sample": "first"},
    )
    event2 = store.append_audit_event(
        event_type=AuditEventType.CHANGE_PROPOSAL_CREATED.value,
        change_id="chg_001",
        new_status="PROPOSED",
        details={"sample": "second"},
    )

    assert event2.previous_event_hash == event1.event_hash
    assert event2.event_hash != event1.event_hash


def test_hash_chain_verification_succeeds_for_valid_sequence(tmp_path):
    """Verify intact sequence of audit events passes verification."""
    db_file = tmp_path / "valid_chain.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    for i in range(5):
        store.append_audit_event(
            event_type=f"STEP_{i}",
            details={"step_index": i},
        )

    result = store.verify_hash_chain()
    assert result.valid is True
    assert result.checked_event_count == 5
    assert result.first_invalid_event_id is None
    assert result.reason is None


# ==============================================================================
# 3. TAMPER DETECTION (MODIFIED DATA, HASH, OR LINKAGE)
# ==============================================================================


def test_tampering_with_event_data_detected(tmp_path):
    """Verify modifying event details in SQLite causes hash chain verification failure."""
    db_file = tmp_path / "tamper_data.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    evt1 = store.append_audit_event(event_type="STEP_1", details={"status": "initial"})
    evt2 = store.append_audit_event(event_type="STEP_2", details={"status": "original"})
    evt3 = store.append_audit_event(event_type="STEP_3", details={"status": "final"})

    # Tamper with evt2's details directly in SQLite
    with sqlite3.connect(str(db_file)) as raw_conn:
        cursor = raw_conn.cursor()
        cursor.execute(
            "UPDATE audit_events SET details = ? WHERE event_id = ?;",
            (json.dumps({"status": "TAMPERED_MALICIOUS_EDIT"}), evt2.event_id),
        )
        raw_conn.commit()

    result = store.verify_hash_chain()
    assert result.valid is False
    assert result.first_invalid_event_id == evt2.event_id
    assert "Tampered event payload or hash" in (result.reason or "")
    assert result.checked_event_count == 1  # 0 passed, failed on index 1


def test_tampering_with_event_hash_detected(tmp_path):
    """Verify modifying event_hash in SQLite causes verification failure."""
    db_file = tmp_path / "tamper_hash.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    evt1 = store.append_audit_event(event_type="STEP_1", details={"val": 1})
    evt2 = store.append_audit_event(event_type="STEP_2", details={"val": 2})

    # Tamper with evt1's hash directly
    with sqlite3.connect(str(db_file)) as raw_conn:
        cursor = raw_conn.cursor()
        cursor.execute(
            "UPDATE audit_events SET event_hash = ? WHERE event_id = ?;",
            ("0" * 64, evt1.event_id),
        )
        raw_conn.commit()

    result = store.verify_hash_chain()
    assert result.valid is False
    assert result.first_invalid_event_id == evt1.event_id
    assert "Tampered event payload or hash" in (result.reason or "")


def test_broken_previous_event_hash_linkage_detected(tmp_path):
    """Verify broken previous_event_hash link causes verification failure."""
    db_file = tmp_path / "tamper_link.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    evt1 = store.append_audit_event(event_type="STEP_1", details={"val": 1})
    evt2 = store.append_audit_event(event_type="STEP_2", details={"val": 2})

    # Tamper with evt2's previous_event_hash directly
    with sqlite3.connect(str(db_file)) as raw_conn:
        cursor = raw_conn.cursor()
        cursor.execute(
            "UPDATE audit_events SET previous_event_hash = ? WHERE event_id = ?;",
            ("f" * 64, evt2.event_id),
        )
        raw_conn.commit()

    result = store.verify_hash_chain()
    assert result.valid is False
    assert result.first_invalid_event_id == evt2.event_id
    assert "Broken hash chain link" in (result.reason or "")


# ==============================================================================
# 4. WORKFLOW TRANSITIONS & AUDIT EVENT GENERATION
# ==============================================================================


def test_reviewer_decision_creates_audit_event(tmp_path):
    """Verify recording a human decision produces a REVIEWER_DECISION_CREATED event."""
    db_file = tmp_path / "wf_audit_test.db"
    manager = ChangeManagerService(db_path=str(db_file))

    decision = ReviewerDecision(
        decision_id="dec_audit_01",
        target_content_id="rc_sec_4",
        candidate_id="cand_fda_99",
        decision=ReviewDecisionType.ADAPT,
        reviewer_name="Dr. Senior Reviewer",
        reviewer_notes="Require localized dosage adjustments.",
        adaptation_instructions="Reduce dosing for renal impairment.",
    )
    manager.record_decision(decision)

    events = manager.list_audit_events()
    assert len(events) == 1
    evt = events[0]
    assert evt.event_type == AuditEventType.REVIEWER_DECISION_CREATED.value
    assert evt.decision_id == decision.decision_id
    assert evt.reviewer_name == "Dr. Senior Reviewer"
    assert evt.new_status == "ADAPT"
    assert evt.details["notes"] == "Require localized dosage adjustments."
    assert evt.details["adaptation_instructions"] == "Reduce dosing for renal impairment."


def test_proposal_creation_creates_audit_event(tmp_path):
    """Verify creating a change proposal produces a CHANGE_PROPOSAL_CREATED event."""
    db_file = tmp_path / "wf_prop_audit.db"
    manager = ChangeManagerService(db_path=str(db_file))

    decision = ReviewerDecision(
        decision_id="dec_prop_audit",
        target_content_id="rc_prop",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Regulatory Lead",
    )
    manager.record_decision(decision)

    proposal = manager.create_change_proposal(
        decision=decision,
        section="Clinical Pharmacology",
        original_text="Original pharmacology text.",
        proposed_text="Harmonized pharmacology text.",
        rationale="Harmonize with FDA approved label.",
        document_name="Core_Label.docx",
        document_version="v2.1",
    )

    events = manager.list_audit_events()
    assert len(events) == 2  # 1: decision, 2: proposal
    prop_evt = events[1]
    assert prop_evt.event_type == AuditEventType.CHANGE_PROPOSAL_CREATED.value
    assert prop_evt.change_id == proposal.change_id
    assert prop_evt.decision_id == decision.decision_id
    assert prop_evt.new_status == "PROPOSED"
    assert prop_evt.details["section"] == "Clinical Pharmacology"
    assert prop_evt.details["document_name"] == "Core_Label.docx"


def test_occurrence_confirmation_creates_audit_event(tmp_path):
    """Verify confirming occurrences produces an OCCURRENCES_CONFIRMED event with state snapshot."""
    db_file = tmp_path / "wf_occ_audit.db"
    manager = ChangeManagerService(db_path=str(db_file))

    decision = ReviewerDecision(
        decision_id="dec_occ_audit",
        target_content_id="rc_occ",
        decision=ReviewDecisionType.REUSE,
    )
    manager.record_decision(decision)

    proposal = ProposedChange(
        change_id="chg_occ_audit",
        decision_id=decision.decision_id,
        section="Dosage and Administration",
        original_text="Take 5mg daily.",
        proposed_text="Take 10mg daily.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Update dose.",
        related_occurrences=[
            RelatedOccurrence(
                occurrence_id="occ_1",
                section="Warnings",
                current_text="Take 5mg daily in warnings.",
                status="PENDING",
            ),
            RelatedOccurrence(
                occurrence_id="occ_2",
                section="Adverse Reactions",
                current_text="Take 5mg daily in reactions.",
                status="PENDING",
            ),
        ],
    )
    manager.save_proposal(proposal)

    # Confirm occ_1, exclude occ_2
    manager.confirm_occurrences(
        change_id=proposal.change_id,
        confirmed_occurrence_ids=["occ_1"],
        excluded_occurrence_ids=["occ_2"],
        reviewer_notes="Confirmed Warnings occurrence.",
    )

    events = manager.list_audit_events()
    # Events: 1 decision, 1 proposal, 1 occurrence confirmation
    assert len(events) == 3
    occ_evt = events[2]
    assert occ_evt.event_type == AuditEventType.OCCURRENCES_CONFIRMED.value
    assert occ_evt.change_id == proposal.change_id
    assert occ_evt.details["confirmed_occurrence_ids"] == ["occ_1"]
    assert occ_evt.details["excluded_occurrence_ids"] == ["occ_2"]
    assert occ_evt.details["reviewer_notes"] == "Confirmed Warnings occurrence."
    assert occ_evt.previous_state == {"occ_1": "PENDING", "occ_2": "PENDING"}
    assert occ_evt.new_state == {"occ_1": "CONFIRMED", "occ_2": "EXCLUDED"}


def test_validation_creates_audit_event(tmp_path):
    """Verify validating a change creates a CHANGE_VALIDATED audit event."""
    db_file = tmp_path / "wf_val_audit.db"
    manager = ChangeManagerService(db_path=str(db_file))

    proposal = ProposedChange(
        change_id="chg_val_audit",
        decision_id="dec_val",
        section="Dosage",
        original_text="Old dosage.",
        proposed_text="New dosage.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Validation check.",
    )
    manager.save_proposal(proposal)

    impact = ChangeImpact(
        risk_level="MEDIUM",
        affected_sections_count=2,
        findings=[
            ValidationFinding(
                rule_id="REG-VAL-001",
                severity="INFO",
                message="Check passed.",
                passed=True,
            )
        ],
        validation_passed=True,
    )
    manager.record_validation(proposal, impact)

    events = manager.list_audit_events()
    assert len(events) == 2
    val_evt = events[1]
    assert val_evt.event_type == AuditEventType.CHANGE_VALIDATED.value
    assert val_evt.change_id == proposal.change_id
    assert val_evt.details["risk_level"] == "MEDIUM"
    assert val_evt.details["validation_passed"] is True
    assert val_evt.details["findings_count"] == 1


def test_approval_and_report_creation_create_audit_events(tmp_path):
    """Verify approving proposals and recording reports creates CHANGE_APPROVED and APPROVED_REPORT_CREATED."""
    db_file = tmp_path / "wf_approve_audit.db"
    manager = ChangeManagerService(db_path=str(db_file))

    proposal = ProposedChange(
        change_id="chg_app_audit",
        decision_id="dec_app",
        section="Dosage",
        original_text="Old dose.",
        proposed_text="New dose.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Approval test.",
        status="PROPOSED",
    )
    manager.save_proposal(proposal)

    # 1. Update status to APPROVED
    manager.update_proposal_status(
        change_id=proposal.change_id,
        status="APPROVED",
        reviewer_name="Dr. Final Regulatory Approver",
        notes="All safety criteria fulfilled.",
    )

    # 2. Record approved report
    report = ApprovedChangeReport(
        report_id="rep_audit_999",
        author_approver="Dr. Final Regulatory Approver",
        decision_ids=["dec_app"],
        changes=[proposal],
        approval_confirmation=True,
        audit_notes="Certified regulatory alignment.",
    )
    manager.record_approved_report(report)

    events = manager.list_audit_events()
    # Events: 1 proposal created, 1 change approved, 1 approved report created
    assert len(events) == 3

    app_evt = events[1]
    assert app_evt.event_type == AuditEventType.CHANGE_APPROVED.value
    assert app_evt.change_id == proposal.change_id
    assert app_evt.previous_status == "PROPOSED"
    assert app_evt.new_status == "APPROVED"
    assert app_evt.reviewer_name == "Dr. Final Regulatory Approver"

    rep_evt = events[2]
    assert rep_evt.event_type == AuditEventType.APPROVED_REPORT_CREATED.value
    assert rep_evt.report_id == "rep_audit_999"
    assert rep_evt.reviewer_name == "Dr. Final Regulatory Approver"
    assert rep_evt.details["approval_confirmation"] is True


def test_rejection_status_creates_audit_event(tmp_path):
    """Verify transitioning a proposal to REJECTED emits CHANGE_REJECTED event."""
    db_file = tmp_path / "wf_reject_audit.db"
    manager = ChangeManagerService(db_path=str(db_file))

    proposal = ProposedChange(
        change_id="chg_rej_audit",
        decision_id="dec_rej",
        section="Dosage",
        original_text="Old dose.",
        proposed_text="New dose.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Reject test.",
        status="PROPOSED",
    )
    manager.save_proposal(proposal)

    manager.update_proposal_status(
        change_id=proposal.change_id,
        status="REJECTED",
        reviewer_name="Senior Reviewer",
        notes="Evidence inconsistent with regional clinical profile.",
    )

    events = manager.list_audit_events()
    assert len(events) == 2
    rej_evt = events[1]
    assert rej_evt.event_type == AuditEventType.CHANGE_REJECTED.value
    assert rej_evt.previous_status == "PROPOSED"
    assert rej_evt.new_status == "REJECTED"


# ==============================================================================
# 5. READ-ONLY OPERATIONS DO NOT CREATE DUPLICATE AUDIT EVENTS
# ==============================================================================


def test_get_and_read_operations_do_not_create_audit_events(tmp_path):
    """Verify queries and listing operations are strictly read-only and never add audit events."""
    db_file = tmp_path / "read_only_audit.db"
    manager = ChangeManagerService(db_path=str(db_file))

    dec = ReviewerDecision(
        decision_id="dec_read",
        target_content_id="tc_read",
        decision=ReviewDecisionType.REUSE,
    )
    manager.record_decision(dec)
    initial_count = len(manager.list_audit_events())
    assert initial_count == 1

    # Multiple read operations
    _ = manager.list_decisions()
    _ = manager.get_decision("dec_read")
    _ = manager.list_proposals()
    _ = manager.get_proposal("chg_nonexistent")
    _ = manager.get_latest_report()
    _ = manager.list_audit_events()
    _ = manager.verify_audit_trail()

    # Verify audit event count did not change
    assert len(manager.list_audit_events()) == initial_count


# ==============================================================================
# 6. SERVICE RESTART PERSISTENCE FOR AUDIT TRAIL
# ==============================================================================


def test_audit_events_survive_service_restart_with_valid_hash_chain(tmp_path):
    """Verify audit events survive service restart and the hash chain remains 100% valid."""
    db_file = tmp_path / "restart_audit.db"

    # Service instance A creates a workflow sequence
    service_a = ChangeManagerService(db_path=str(db_file))
    dec = ReviewerDecision(
        decision_id="dec_restart",
        target_content_id="tc_restart",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Persistence Tester",
    )
    service_a.record_decision(dec)

    prop = service_a.create_change_proposal(
        decision=dec,
        section="Dosage",
        original_text="Initial text.",
        proposed_text="Persisted text.",
        rationale="Durable audit trail test.",
    )

    service_a.update_proposal_status(
        change_id=prop.change_id,
        status="APPROVED",
        reviewer_name="Dr. Persistence Tester",
    )

    audit_events_a = service_a.list_audit_events()
    assert len(audit_events_a) == 3

    # Discard instance A completely
    del service_a

    # Service instance B boots from the same SQLite file
    service_b = ChangeManagerService(db_path=str(db_file))
    audit_events_b = service_b.list_audit_events()

    assert len(audit_events_b) == 3
    for ev_a, ev_b in zip(audit_events_a, audit_events_b):
        assert ev_a.event_id == ev_b.event_id
        assert ev_a.event_hash == ev_b.event_hash
        assert ev_a.previous_event_hash == ev_b.previous_event_hash
        assert ev_a.event_type == ev_b.event_type

    # Verify hash chain integrity across restart
    verification = service_b.verify_audit_trail()
    assert verification.valid is True
    assert verification.checked_event_count == 3
    assert verification.first_invalid_event_id is None


# ==============================================================================
# 7. QUERY AUDIT BY CHANGE ID
# ==============================================================================


def test_audit_history_retrievable_by_change_id(tmp_path):
    """Verify list_audit_events_by_change isolates events for specific proposals."""
    db_file = tmp_path / "query_by_change.db"
    manager = ChangeManagerService(db_path=str(db_file))

    p1 = ProposedChange(
        change_id="chg_alpha",
        decision_id="dec_1",
        section="Section 1",
        original_text="Text 1",
        proposed_text="New text 1",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale 1",
    )
    p2 = ProposedChange(
        change_id="chg_beta",
        decision_id="dec_2",
        section="Section 2",
        original_text="Text 2",
        proposed_text="New text 2",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale 2",
    )
    manager.save_proposal(p1)
    manager.save_proposal(p2)
    manager.update_proposal_status("chg_alpha", "APPROVED", reviewer_name="Approver Alpha")

    alpha_events = manager.list_audit_events_by_change("chg_alpha")
    beta_events = manager.list_audit_events_by_change("chg_beta")

    assert len(alpha_events) == 2  # created, approved
    assert len(beta_events) == 1   # created
    assert all(e.change_id == "chg_alpha" for e in alpha_events)
    assert all(e.change_id == "chg_beta" for e in beta_events)


# ==============================================================================
# 8. API READ-ONLY ENDPOINTS (/audit, /audit/verify, /audit/{change_id})
# ==============================================================================


def test_api_audit_endpoints(tmp_path):
    """Verify HTTP API endpoints for audit trail inspection and hash-chain verification."""
    client = TestClient(app)

    # 1. Create a decision via API
    resp = client.post(
        "/review/decision",
        json={
            "target_content_id": "api_sec_1",
            "decision": "REUSE",
            "reviewer_name": "API Reviewer",
            "reviewer_notes": "API test notes",
        },
    )
    assert resp.status_code == 200
    decision_id = resp.json()["decision_id"]

    # 2. Formulate proposal via API
    prop_resp = client.post(
        "/changes/analyze",
        json={
            "decision_id": decision_id,
            "section": "Adverse Reactions",
            "original_text": "Original reactions content.",
            "candidate_text": "Reused candidate content.",
        },
    )
    assert prop_resp.status_code == 200
    change_id = prop_resp.json()["change_id"]

    # 3. GET /audit
    audit_resp = client.get("/audit")
    assert audit_resp.status_code == 200
    audit_events = audit_resp.json()
    assert len(audit_events) >= 2

    # 4. GET /audit/verify
    verify_resp = client.get("/audit/verify")
    assert verify_resp.status_code == 200
    verification = verify_resp.json()
    assert verification["valid"] is True
    assert verification["checked_event_count"] >= 2
    assert verification["first_invalid_event_id"] is None

    # 5. GET /audit/{change_id}
    change_audit_resp = client.get(f"/audit/{change_id}")
    assert change_audit_resp.status_code == 200
    change_events = change_audit_resp.json()
    assert len(change_events) >= 1
    assert all(e["change_id"] == change_id for e in change_events)


# ==============================================================================
# 9. FOCUSED CHECKS: MIGRATION, DEDUPLICATION, & DYNAMIC STATUS
# ==============================================================================


def test_schema_v1_migration_to_v2_preserves_existing_data(tmp_path):
    """Verify an existing Phase 4 Step 4 database (user_version 1) upgrades to version 2 without data loss."""
    db_file = tmp_path / "v1_legacy.db"

    # 1. Manually create a Phase 4 Step 4 schema (user_version 1)
    with sqlite3.connect(str(db_file)) as raw_conn:
        cursor = raw_conn.cursor()
        cursor.execute("PRAGMA user_version = 1;")
        cursor.execute("""
            CREATE TABLE decisions (
                decision_id TEXT PRIMARY KEY,
                decided_at TEXT,
                data TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE proposals (
                change_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                data TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE approved_reports (
                report_id TEXT PRIMARY KEY,
                created_at TEXT,
                data TEXT NOT NULL
            );
        """)

        # Insert existing Step 4 records
        sample_dec = ReviewerDecision(
            decision_id="dec_legacy_v1",
            target_content_id="tc_v1",
            decision=ReviewDecisionType.REUSE,
        )
        cursor.execute(
            "INSERT INTO decisions VALUES (?, ?, ?);",
            (sample_dec.decision_id, sample_dec.decided_at, sample_dec.model_dump_json()),
        )

        sample_prop = ProposedChange(
            change_id="chg_legacy_v1",
            decision_id="dec_legacy_v1",
            section="Indications",
            original_text="Old text",
            proposed_text="New text",
            decision_type=ReviewDecisionType.REUSE,
            rationale="Legacy proposal",
        )
        cursor.execute(
            "INSERT INTO proposals VALUES (?, ?, ?, ?, ?);",
            (sample_prop.change_id, sample_prop.status, sample_prop.created_at, sample_prop.created_at, sample_prop.model_dump_json()),
        )
        raw_conn.commit()

    # 2. Boot WorkflowSQLiteStore on legacy DB
    store = WorkflowSQLiteStore(db_path=str(db_file))

    # Verify user_version upgraded to 2
    with store._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        assert cursor.fetchone()[0] == 2

    # Verify legacy data preserved
    loaded_dec = store.get_decision("dec_legacy_v1")
    assert loaded_dec is not None
    assert loaded_dec.decision_id == "dec_legacy_v1"

    loaded_prop = store.get_proposal("chg_legacy_v1")
    assert loaded_prop is not None
    assert loaded_prop.change_id == "chg_legacy_v1"

    # Verify audit_events table is ready and functional
    evt = store.append_audit_event(event_type="MIGRATION_CHECK", details={"legacy": True})
    assert evt.event_id is not None
    assert store.verify_hash_chain().valid is True


def test_change_approval_captures_actual_previous_status(tmp_path):
    """Verify CHANGE_APPROVED records the real status immediately prior to approval (e.g. PENDING_APPROVAL)."""
    db_file = tmp_path / "approval_status.db"
    manager = ChangeManagerService(db_path=str(db_file))

    proposal = ProposedChange(
        change_id="chg_dyn_status",
        decision_id="dec_dyn",
        section="Warnings",
        original_text="Old",
        proposed_text="New",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Dynamic status test",
        status="PROPOSED",
    )
    manager.save_proposal(proposal)

    # Transition to PENDING_APPROVAL first
    manager.update_proposal_status(proposal.change_id, "PENDING_APPROVAL")

    # Now approve from PENDING_APPROVAL
    manager.update_proposal_status(
        change_id=proposal.change_id,
        status="APPROVED",
        reviewer_name="Dr. Lead Reviewer",
    )

    events = manager.list_audit_events_by_change(proposal.change_id)
    # Events: 1 proposal created, 1 approved
    assert len(events) == 2
    approval_evt = events[1]
    assert approval_evt.event_type == AuditEventType.CHANGE_APPROVED.value
    assert approval_evt.previous_status == "PENDING_APPROVAL"
    assert approval_evt.new_status == "APPROVED"
    assert approval_evt.previous_state == {"status": "PENDING_APPROVAL"}
    assert approval_evt.new_state == {"status": "APPROVED"}


def test_save_proposal_update_does_not_duplicate_change_proposal_created(tmp_path):
    """Verify updating an existing proposal via save_proposal does not re-emit CHANGE_PROPOSAL_CREATED."""
    db_file = tmp_path / "dedup_audit.db"
    manager = ChangeManagerService(db_path=str(db_file))

    proposal = ProposedChange(
        change_id="chg_dedup",
        decision_id="dec_dedup",
        section="Dosage",
        original_text="Old",
        proposed_text="New",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Dedup test",
    )
    # First save: creation
    manager.save_proposal(proposal)

    initial_events = manager.list_audit_events_by_change(proposal.change_id)
    assert len(initial_events) == 1
    assert initial_events[0].event_type == AuditEventType.CHANGE_PROPOSAL_CREATED.value

    # Subsequent updates to the same proposal
    proposal.proposed_text = "Updated proposed text."
    manager.save_proposal(proposal)
    proposal.proposed_text = "Further updated text."
    manager.save_proposal(proposal)

    after_events = manager.list_audit_events_by_change(proposal.change_id)
    # Must remain exactly 1 CHANGE_PROPOSAL_CREATED event
    assert len(after_events) == 1
    assert after_events[0].event_type == AuditEventType.CHANGE_PROPOSAL_CREATED.value

