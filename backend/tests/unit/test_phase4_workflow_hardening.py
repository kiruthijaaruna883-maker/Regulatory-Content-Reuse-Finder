"""Phase 4 Step 8: End-to-end workflow hardening and governance boundary verification.

Verifies:
1. Complete lifecycle: Document Review -> Comparison -> Human Decision -> Proposal ->
   Occurrence Detection -> Confirmation/Exclusion -> Impact Analysis -> Deterministic Validation ->
   Human Approval Gate -> Approved Change Report -> Hash-Chained Audit Trail -> PDF Generation -> PDF Download.
2. Human Decision Gates:
   - REJECT decisions never formulate change proposals.
   - REUSE and ADAPT decisions formulate expected controlled proposals.
   - Unresolved PENDING occurrences strictly block report approval (Rule REG-VAL-006).
   - EXCLUDED occurrences are omitted from coordinated change impact calculations.
   - CONFIRMED occurrences are included in affected sections and content counts.
   - Validation failures block approval.
   - Approval gate strictly requires explicit human confirmation (approval_confirmation=True).
   - Expected audit events (REVIEWER_DECISION_CREATED, CHANGE_PROPOSAL_CREATED,
     OCCURRENCES_CONFIRMED, CHANGE_VALIDATED, CHANGE_APPROVED, APPROVED_REPORT_CREATED) are emitted.
   - PDF generation is read-only and emits NO audit events.
   - Approved report state in SQLite is immutable during PDF generation and export.
3. Audit Trail Hardening:
   - Cryptographic SHA-256 hash chaining across the entire lifecycle.
   - Tamper-detection: data modification, hash modification, or broken hash links cause verification failure.
   - Exact audit hashes are preserved in generated PDF text.
4. SQLite Persistence Hardening:
   - Reconstruction of workflow entities across service restarts.
   - Schema version 2 integrity.
5. API Edge Cases:
   - 400 / 404 / 422 error boundaries for review, occurrence confirmation, approval, and PDF download.
"""

import io
from pathlib import Path
import sqlite3
import pypdf
import pytest
from starlette.testclient import TestClient

from app.agents.document_change_agent import RegulatoryDocumentChangeAgent
from app.graph.workflow import RegulatoryWorkflowGraph
from app.main import app
from app.models.audit import (
    AuditEvent,
    AuditEventType,
    AuditVerificationResult,
    compute_event_hash,
)
from app.models.comparison import EvidenceTrace
from app.models.content import RegulatoryContentItem
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
from app.routes.document_review import change_manager
from app.services.change_manager import ChangeManagerService
from app.services.pdf_generator import PDFReportGenerator
from app.services.validation import ValidationService


# ==============================================================================
# 1. HUMAN DECISION GATES HARDENING
# ==============================================================================


def test_reject_decision_blocks_proposal_formulation(tmp_path):
    """Verify that a human REJECT decision cannot formulate a change proposal for approval."""
    db_file = tmp_path / "reject_gate.db"
    manager = ChangeManagerService(db_path=str(db_file))

    reject_dec = ReviewerDecision(
        decision_id="dec_reject_01",
        target_content_id="tc_reject_01",
        candidate_id="cand_ext_01",
        decision=ReviewDecisionType.REJECT,
        reviewer_name="Dr. Safety Officer",
        reviewer_notes="Candidate content does not meet clinical specificity requirements.",
    )
    manager.record_decision(reject_dec)

    # Direct service call must raise ValueError
    with pytest.raises(ValueError, match="Cannot create a change proposal for a REJECT decision"):
        manager.create_change_proposal(
            decision=reject_dec,
            section="Contraindications",
            original_text="Preserved internal text baseline.",
            proposed_text="Attempted replacement text.",
            rationale="Rejected candidate proposal.",
        )

    # Agent 2 formulation must return None
    agent = RegulatoryDocumentChangeAgent()
    proposal = agent.formulate_change_proposal(
        decision=reject_dec,
        section="Contraindications",
        original_text="Preserved baseline.",
        candidate_text="Candidate text.",
    )
    assert proposal is None


def test_reuse_and_adapt_decisions_create_valid_proposals(tmp_path):
    """Verify that REUSE and ADAPT decisions formulate expected proposals with correct decision types."""
    db_file = tmp_path / "reuse_adapt.db"
    manager = ChangeManagerService(db_path=str(db_file))

    # REUSE
    reuse_dec = ReviewerDecision(
        decision_id="dec_reuse_01",
        target_content_id="tc_reuse_01",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Regulatory Lead",
        reviewer_notes="Direct reuse authorized.",
    )
    manager.record_decision(reuse_dec)
    reuse_prop = manager.create_change_proposal(
        decision=reuse_dec,
        section="Adverse Reactions",
        original_text="Headache (2%).",
        proposed_text="Headache (4%).",
        rationale="Aligned with external label reference.",
    )
    assert reuse_prop.decision_type == ReviewDecisionType.REUSE
    assert reuse_prop.status == "PROPOSED"

    # ADAPT
    adapt_dec = ReviewerDecision(
        decision_id="dec_adapt_01",
        target_content_id="tc_adapt_01",
        decision=ReviewDecisionType.ADAPT,
        reviewer_name="Dr. Regulatory Lead",
        reviewer_notes="Adaptation for pediatric population.",
        adaptation_instructions="Adjust dose to 10 mg/m2.",
    )
    manager.record_decision(adapt_dec)
    adapt_prop = manager.create_change_proposal(
        decision=adapt_dec,
        section="Dosage and Administration",
        original_text="Adult dose: 20 mg daily.",
        proposed_text="Pediatric dose: 10 mg/m2 daily.",
        rationale="Adapted for pediatric indication.",
    )
    assert adapt_prop.decision_type == ReviewDecisionType.ADAPT
    assert adapt_prop.status == "PROPOSED"


def test_pending_occurrences_strictly_block_approval():
    """Verify Rule REG-VAL-006: Any proposal with PENDING occurrences cannot be approved."""
    validator = ValidationService()
    agent = RegulatoryDocumentChangeAgent()

    pending_occ = RelatedOccurrence(
        occurrence_id="occ_pend_01",
        section="Warnings and Precautions",
        current_text="Unreviewed occurrence text.",
        status="PENDING",
    )

    proposal = ProposedChange(
        change_id="chg_pending_occ",
        decision_id="dec_test_occ",
        section="Adverse Reactions",
        original_text="Original text baseline.",
        proposed_text="Valid proposed replacement text.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Valid clinical rationale provided.",
        status="PROPOSED",
        related_occurrences=[pending_occ],
    )

    # validate_approval must generate an ERROR finding for REG-VAL-006
    findings = validator.validate_approval(
        approver_name="Dr. Authorizer",
        approval_confirmation=True,
        proposals=[proposal],
    )
    error_findings = [f for f in findings if f.severity == "ERROR" and not f.passed]
    assert any(f.rule_id == "REG-VAL-006" for f in error_findings)

    # Calling agent to compile report must fail with ValueError
    with pytest.raises(ValueError, match="REG-VAL-006|unresolved related occurrences"):
        agent.generate_approved_change_report(
            document_name="Test Core Sheet",
            approver_name="Dr. Authorizer",
            approval_confirmation=True,
            approved_changes=[proposal],
        )


def test_excluded_occurrences_are_omitted_from_impact_analysis():
    """Verify that EXCLUDED occurrences do not contribute to affected sections or content counts."""
    validator = ValidationService()

    occ_confirmed = RelatedOccurrence(
        occurrence_id="occ_conf_01",
        section="Precautions",
        current_text="Coordinated precaution update.",
        status="CONFIRMED",
    )
    occ_excluded = RelatedOccurrence(
        occurrence_id="occ_excl_01",
        section="Clinical Pharmacology",
        current_text="Preserved baseline text.",
        status="EXCLUDED",
    )

    proposal = ProposedChange(
        change_id="chg_occ_impact",
        decision_id="dec_occ_impact",
        section="Dosage and Administration",
        original_text="Original dosage baseline text.",
        proposed_text="Updated dosage instruction text.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Updated dosage rationale.",
        related_occurrences=[occ_confirmed, occ_excluded],
    )

    impact = validator.validate_proposal(proposal)

    # "Dosage and Administration" and "Precautions" are affected; "Clinical Pharmacology" is EXCLUDED
    assert "Dosage and Administration" in impact.affected_sections
    assert "Precautions" in impact.affected_sections
    assert "Clinical Pharmacology" not in impact.affected_sections
    assert impact.affected_sections_count == 2
    # Affected content count = 1 (main proposal) + 1 (confirmed) = 2
    assert impact.affected_content_count == 2


def test_approval_strictly_requires_explicit_confirmation():
    """Verify that approval_confirmation=False strictly rejects report assembly."""
    agent = RegulatoryDocumentChangeAgent()

    proposal = ProposedChange(
        change_id="chg_valid_01",
        decision_id="dec_valid_01",
        section="Indications",
        original_text="Original indication baseline.",
        proposed_text="Expanded pediatric indication.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Supported by pediatric trial.",
        status="PROPOSED",
    )

    with pytest.raises(ValueError, match="Explicit human approval confirmation"):
        agent.generate_approved_change_report(
            document_name="Test Core Sheet",
            approver_name="Dr. Approver",
            approval_confirmation=False,  # Unapproved
            approved_changes=[proposal],
        )


def test_validation_failures_block_report_approval():
    """Verify that proposals failing deterministic validation (e.g. empty text) are blocked from approval."""
    validator = ValidationService()

    invalid_proposal = ProposedChange(
        change_id="chg_invalid_empty",
        decision_id="dec_invalid",
        section="Warnings",
        original_text="Valid baseline text.",
        proposed_text="   ",  # Fails text completeness check REG-VAL-001
        decision_type=ReviewDecisionType.REUSE,
        rationale="Short rationale.",
    )

    impact = validator.validate_proposal(invalid_proposal)
    assert impact.validation_passed is False
    assert impact.risk_level == "HIGH"
    assert any(f.rule_id == "REG-VAL-001" and f.severity == "ERROR" for f in impact.findings)


# ==============================================================================
# 2. AUDIT TRAIL HARDENING & TAMPER DETECTION
# ==============================================================================


def test_tamper_detection_in_stored_audit_events(tmp_path):
    """Verify that tampering with event data, hash, or previous hash breaks verification."""
    db_file = tmp_path / "tamper_test.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    # Append two valid events
    e1 = store.append_audit_event(
        event_type="REVIEWER_DECISION_CREATED",
        decision_id="dec_01",
        details={"decision": "REUSE"},
    )
    e2 = store.append_audit_event(
        event_type="CHANGE_PROPOSAL_CREATED",
        change_id="chg_01",
        decision_id="dec_01",
        details={"section": "Dosage"},
    )

    # Initial verification must pass
    assert store.verify_hash_chain().valid is True

    # 1. Tamper with stored details of e1
    with store._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE audit_events SET details = ? WHERE event_id = ?;",
            ('{"decision":"ADAPT"}', e1.event_id),
        )
    result_tampered_data = store.verify_hash_chain()
    assert result_tampered_data.valid is False
    assert result_tampered_data.first_invalid_event_id == e1.event_id

    # Restore e1
    with store._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE audit_events SET details = ? WHERE event_id = ?;",
            ('{"decision":"REUSE"}', e1.event_id),
        )
    assert store.verify_hash_chain().valid is True

    # 2. Tamper with event_hash of e2
    with store._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE audit_events SET event_hash = ? WHERE event_id = ?;",
            ("0" * 64, e2.event_id),
        )
    result_tampered_hash = store.verify_hash_chain()
    assert result_tampered_hash.valid is False
    assert result_tampered_hash.first_invalid_event_id == e2.event_id

    # Restore e2 hash
    with store._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE audit_events SET event_hash = ? WHERE event_id = ?;",
            (e2.event_hash, e2.event_id),
        )
    assert store.verify_hash_chain().valid is True

    # 3. Tamper with previous_event_hash link
    with store._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE audit_events SET previous_event_hash = ? WHERE event_id = ?;",
            ("f" * 64, e2.event_id),
        )
    result_broken_link = store.verify_hash_chain()
    assert result_broken_link.valid is False
    assert result_broken_link.first_invalid_event_id == e2.event_id


def test_pdf_generation_preserves_exact_stored_audit_hashes(tmp_path):
    """Verify that PDF generation renders the exact SHA-256 event hashes stored in SQLite."""
    db_file = tmp_path / "pdf_hashes.db"
    manager = ChangeManagerService(db_path=str(db_file))

    dec = manager.record_decision(
        ReviewerDecision(
            decision_id="dec_audit_pdf",
            target_content_id="tc_audit_pdf",
            decision=ReviewDecisionType.REUSE,
            reviewer_name="Dr. Hash Validator",
        )
    )
    prop = manager.create_change_proposal(
        decision=dec,
        section="Warnings",
        original_text="Original warning text.",
        proposed_text="Updated warning text.",
        rationale="Safety alignment.",
    )
    manager.update_proposal_status(prop.change_id, "APPROVED", reviewer_name="Dr. Hash Validator")

    report = ApprovedChangeReport(
        report_id="rep_audit_pdf_01",
        author_approver="Dr. Hash Validator",
        approval_confirmation=True,
        changes=[prop],
    )
    manager.record_approved_report(report)

    audit_events = manager.list_audit_events_for_report(report)
    assert len(audit_events) >= 3

    # Generate PDF
    generator = PDFReportGenerator()
    pdf_bytes = generator.generate(report, audit_events=audit_events)

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join(page.extract_text() for page in reader.pages)

    # Every event's exact hash and previous hash must appear in the PDF
    for evt in audit_events:
        assert evt.event_hash in full_text
        if evt.previous_event_hash:
            assert evt.previous_event_hash in full_text


def test_pdf_generation_is_read_only_and_emits_no_audit_events(tmp_path):
    """Verify that generating or downloading a PDF never appends new audit events to SQLite."""
    db_file = tmp_path / "pdf_read_only.db"
    manager = ChangeManagerService(db_path=str(db_file))

    report = ApprovedChangeReport(
        report_id="rep_read_only_test",
        author_approver="Dr. Auditor",
        approval_confirmation=True,
    )
    manager.record_approved_report(report)

    initial_events = manager.list_audit_events()
    initial_count = len(initial_events)

    generator = PDFReportGenerator()
    # Generate multiple times
    generator.generate(report, audit_events=initial_events)
    generator.generate(report, audit_events=initial_events)

    after_events = manager.list_audit_events()
    assert len(after_events) == initial_count


# ==============================================================================
# 3. SQLITE PERSISTENCE HARDENING & RELOAD BOUNDARY
# ==============================================================================


def test_full_workflow_reconstruction_across_store_restarts(tmp_path):
    """Verify that decisions, proposals, occurrences, validation, reports, and audit events
    survive complete service/store reboots.
    """
    db_file = tmp_path / "reboot_persistence.db"

    # --- SESSION 1: Create and populate workflow entities ---
    manager1 = ChangeManagerService(db_path=str(db_file))

    occ = RelatedOccurrence(
        occurrence_id="occ_reboot_01",
        section="Warnings",
        current_text="Precaution text.",
        status="CONFIRMED",
    )
    finding = ValidationFinding(
        rule_id="REG-VAL-001",
        severity="INFO",
        passed=True,
        message="Validated in session 1.",
    )

    decision = manager1.record_decision(
        ReviewerDecision(
            decision_id="dec_reboot_01",
            target_content_id="tc_reboot_01",
            decision=ReviewDecisionType.REUSE,
            reviewer_name="Dr. Reboot Tester",
        )
    )
    proposal = ProposedChange(
        change_id="chg_reboot_01",
        decision_id=decision.decision_id,
        section="Dosage",
        original_text="10 mg once daily.",
        proposed_text="20 mg once daily.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Reboot test rationale.",
        related_occurrences=[occ],
        validation_findings=[finding],
        status="APPROVED",
    )
    manager1.save_proposal(proposal)

    report = ApprovedChangeReport(
        report_id="rep_reboot_01",
        document_name="Reboot Drug Label",
        document_version="1.0",
        author_approver="Dr. Reboot Tester",
        approval_confirmation=True,
        changes=[proposal],
        audit_notes="Persisted across service reboot.",
    )
    manager1.record_approved_report(report)

    # --- SESSION 2: Reboot service from the same SQLite DB file ---
    manager2 = ChangeManagerService(db_path=str(db_file))

    # Verify decision reloaded
    reloaded_dec = manager2.get_decision("dec_reboot_01")
    assert reloaded_dec is not None
    assert reloaded_dec.decision == ReviewDecisionType.REUSE
    assert reloaded_dec.reviewer_name == "Dr. Reboot Tester"

    # Verify proposal reloaded with occurrences and findings intact
    reloaded_prop = manager2.get_proposal("chg_reboot_01")
    assert reloaded_prop is not None
    assert reloaded_prop.status == "APPROVED"
    assert len(reloaded_prop.related_occurrences) == 1
    assert reloaded_prop.related_occurrences[0].status == "CONFIRMED"
    assert len(reloaded_prop.validation_findings) == 1

    # Verify approved report reloaded
    reloaded_rep = manager2.get_report("rep_reboot_01")
    assert reloaded_rep is not None
    assert reloaded_rep.document_name == "Reboot Drug Label"
    assert reloaded_rep.author_approver == "Dr. Reboot Tester"
    assert reloaded_rep.approval_confirmation is True

    # Verify audit chain reloaded and verified
    audit_events = manager2.list_audit_events()
    assert len(audit_events) >= 2
    verification = manager2.verify_audit_trail()
    assert verification.valid is True
    assert verification.checked_event_count >= 2


def test_schema_user_version_2_integrity(tmp_path):
    """Verify that SQLite user_version is 2 and all required tables exist."""
    db_file = tmp_path / "schema_version.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    with store._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        assert "decisions" in tables
        assert "proposals" in tables
        assert "approved_reports" in tables
        assert "audit_events" in tables


# ==============================================================================
# 4. COMPREHENSIVE END-TO-END WORKFLOW TEST (STEPS A -> M)
# ==============================================================================


def test_complete_end_to_end_regulatory_workflow(tmp_path):
    """Execute and verify the full 16-stage GPR human-in-the-loop regulatory cycle:
    1. Decision -> 2. Proposal -> 3. Detect Occurrences -> 4. Confirm/Exclude ->
    5. Impact -> 6. Validate -> 7. Approve -> 8. Report -> 9. Audit -> 10. Verify Hash Chain ->
    11. Generate PDF -> 12. Signature %PDF- -> 13. PDF Content -> 14. Exact Hashes ->
    15. Report Immutability -> 16. Read-Only Download Check.
    """
    db_file = tmp_path / "e2e_full_lifecycle.db"
    manager = ChangeManagerService(db_path=str(db_file))
    agent = RegulatoryDocumentChangeAgent()
    validator = ValidationService()
    generator = PDFReportGenerator()

    # Stage A/B/C: Human Review Decision (ADAPT)
    decision = manager.record_decision(
        ReviewerDecision(
            decision_id="dec_e2e_01",
            target_content_id="sec_warnings_p1",
            candidate_id="cand_fda_spl_101",
            decision=ReviewDecisionType.ADAPT,
            reviewer_name="Dr. Marcus Bell, PharmD",
            reviewer_notes="Adapted based on pediatric safety advisory.",
            adaptation_instructions="Add hepatic monitoring requirement for pediatric cohort.",
        )
    )
    assert decision.decision == ReviewDecisionType.ADAPT

    # Stage D: Proposed Change Formulation
    proposal = agent.formulate_change_proposal(
        decision=decision,
        section="Warnings and Precautions",
        original_text="Patients should be monitored periodically.",
        candidate_text="Hepatic enzyme monitoring is recommended monthly.",
        document_name="Pediatric Labeling Core Document",
        document_version="5.1",
    )
    assert proposal is not None
    manager.save_proposal(proposal)

    # Stage E: Detect Related Occurrences across sections
    document_sections = [
        {"section": "Dosage and Administration", "text": "Hepatic enzyme baseline required before dosing."},
        {"section": "Clinical Pharmacology", "text": "Metabolized extensively in hepatic pathways."},
    ]
    occurrences = agent.detect_related_occurrences(
        target_phrase="Hepatic enzyme",
        document_sections=document_sections,
    )
    assert len(occurrences) >= 1
    proposal.related_occurrences = occurrences
    manager.save_proposal(proposal, emit_audit=False)

    # Stage F: Human Occurrence Confirmation / Exclusion
    # Confirm first occurrence, exclude second if present
    confirmed_ids = [occurrences[0].occurrence_id]
    excluded_ids = [occ.occurrence_id for occ in occurrences[1:]]

    updated_proposal = manager.confirm_occurrences(
        change_id=proposal.change_id,
        confirmed_occurrence_ids=confirmed_ids,
        excluded_occurrence_ids=excluded_ids,
        reviewer_notes="Confirmed dosage cross-reference; excluded pharmacology narrative.",
    )
    assert any(occ.status == "CONFIRMED" for occ in updated_proposal.related_occurrences)

    # Stage G/H: Impact Analysis & Deterministic Validation
    impact = validator.validate_proposal(updated_proposal)
    assert impact.validation_passed is True
    manager.record_validation(updated_proposal, impact)

    # Stage I/J: Human Approval Gate & Approved Change Report
    report = agent.generate_approved_change_report(
        document_name="Pediatric Labeling Core Document",
        document_version="5.1",
        approver_name="Dr. Marcus Bell, PharmD",
        approval_confirmation=True,
        approved_changes=[updated_proposal],
        audit_notes="Approved for FDA NDA supplement submission.",
    )
    assert report.approval_confirmation is True
    manager.update_proposal_status(updated_proposal.change_id, "APPROVED", reviewer_name="Dr. Marcus Bell, PharmD")
    manager.record_approved_report(report)

    # Stage K: Tamper-Evident Audit Trail
    audit_events = manager.list_audit_events_for_report(report)
    assert len(audit_events) >= 5

    # Verify SHA-256 hash-chain integrity
    verification = manager.verify_audit_trail()
    assert verification.valid is True
    assert verification.checked_event_count >= 5

    # Stage L: Server-Side PDF Generation
    initial_report_json = report.model_dump_json()
    initial_audit_count = len(manager.list_audit_events())

    pdf_bytes = generator.generate(report, audit_events=audit_events)

    # Stage M: PDF Quality, Signature, and Content Verification
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join(page.extract_text() for page in reader.pages)

    assert "Regulatory Content Reuse Finder" in full_text
    assert "Approved Change Report" in full_text
    assert "GOVERNANCE & STATUTORY DISCLAIMER" in full_text
    assert "Pediatric Labeling Core Document" in full_text
    assert "Dr. Marcus Bell, PharmD" in full_text
    assert "CONFIRMED" in full_text
    assert report.report_id in full_text

    # Verify exact audit hashes are embedded
    for evt in audit_events:
        assert evt.event_hash in full_text

    # Verify Report Immutability & Zero New Audit Events
    reloaded_report = manager.get_report(report.report_id)
    assert reloaded_report is not None
    assert reloaded_report.model_dump_json() == initial_report_json
    assert len(manager.list_audit_events()) == initial_audit_count


# ==============================================================================
# 5. API EDGE CASES & ERROR BOUNDARIES
# ==============================================================================


def test_api_review_decision_validation():
    """Verify validation boundaries on POST /review/decision."""
    test_client = TestClient(app)

    # Missing reviewer name returns 422
    resp1 = test_client.post(
        "/review/decision",
        json={"target_content_id": "tc_1", "decision": "REUSE", "reviewer_name": "  "},
    )
    assert resp1.status_code == 422

    # ADAPT without adaptation instructions returns 422
    resp2 = test_client.post(
        "/review/decision",
        json={"target_content_id": "tc_2", "decision": "ADAPT", "reviewer_name": "Dr. Valid"},
    )
    assert resp2.status_code == 422


def test_api_occurrences_confirm_validation():
    """Verify validation boundaries on POST /changes/occurrences/confirm."""
    test_client = TestClient(app)

    # Non-existent change ID returns 404
    resp = test_client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": "chg_nonexistent_xyz",
            "confirmed_occurrence_ids": [],
            "excluded_occurrence_ids": [],
        },
    )
    assert resp.status_code == 404


def test_api_approve_requires_explicit_confirmation():
    """Verify POST /changes/approve strictly rejects approval_confirmation=False with HTTP 400."""
    test_client = TestClient(app)

    resp = test_client.post(
        "/changes/approve",
        json={
            "approver_name": "Dr. Unconfirmed",
            "approval_confirmation": False,
        },
    )
    assert resp.status_code == 400
    assert "approval_confirmation=true" in resp.json()["detail"].lower()


def test_api_pdf_download_missing_and_unapproved():
    """Verify GET /changes/report/{report_id}/pdf error codes."""
    test_client = TestClient(app)

    # Missing report returns 404
    missing_resp = test_client.get("/changes/report/rep_absent_000/pdf")
    assert missing_resp.status_code == 404

    # Unapproved report returns 400
    unapproved = ApprovedChangeReport(
        report_id="rep_unapp_api_test",
        author_approver="Dr. Approver",
        approval_confirmation=False,
    )
    change_manager.store.save_report(unapproved)

    unapp_resp = test_client.get(f"/changes/report/{unapproved.report_id}/pdf")
    assert unapp_resp.status_code == 400
    assert "approval confirmation" in unapp_resp.json()["detail"].lower()
