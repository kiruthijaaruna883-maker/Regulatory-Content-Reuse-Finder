"""Targeted unit tests for Phase 4 Step 6: Server-Side PDF Report Generator.

Verifies:
1. Approved report generates valid PDF bytes starting with '%PDF-'.
2. Generated PDF is non-empty.
3. PDF endpoint returns HTTP 200 for an approved report.
4. Endpoint returns media type 'application/pdf' with appropriate Content-Disposition.
5. Missing report returns appropriate 404 Not Found response.
6. Unapproved report (approval_confirmation=False) cannot be exported (HTTP 400).
7. Governance and statutory disclaimers are present in the PDF output.
8. Document and approver metadata are accurately represented.
9. Proposed and approved changes (section, original text, proposed text, rationale) are included.
10. External evidence provenance citations (source, URL, Set ID, exact quote) are represented.
11. Related occurrence dispositions (CONFIRMED vs EXCLUDED) are clearly distinguished.
12. Validation findings and rule IDs are represented.
13. Audit event information and exact SHA-256 event hashes are preserved in PDF output.
14. PDF generation is strictly read-only and does NOT mutate the stored report or audit trail.
15. Minimal/fallback reports render cleanly without errors.
16. End-to-end API workflow from approval to PDF export.
"""

import io
from pathlib import Path
import sqlite3
import pypdf
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.models.audit import AuditEvent, compute_event_hash
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
from app.routes.document_review import change_manager
from app.services.change_manager import ChangeManagerService
from app.services.pdf_generator import PDFReportGenerator

client = TestClient(app)


# ==============================================================================
# TEST FIXTURES & HELPERS
# ==============================================================================


def create_sample_approved_report(
    report_id: str = "rep_pdf_test_001",
    approval_confirmation: bool = True,
    approver_name: str = "Dr. Eleanor Vance, PharmD",
) -> ApprovedChangeReport:
    """Construct a comprehensive ApprovedChangeReport for verification."""
    occ_confirmed = RelatedOccurrence(
        occurrence_id="occ_pdf_01",
        section="Warnings and Precautions",
        location="Paragraph 3",
        current_text="Dosage monitoring is advised in elderly patients.",
        matched_text="Dosage monitoring is advised in elderly patients.",
        match_type="normalized_match",
        relevance="DIRECT",
        status="CONFIRMED",
    )
    occ_excluded = RelatedOccurrence(
        occurrence_id="occ_pdf_02",
        section="Clinical Pharmacology",
        location="Subsection 12.3",
        current_text="Baseline pharmacokinetic profile observed.",
        matched_text="Baseline pharmacokinetic profile observed.",
        match_type="semantic_match",
        relevance="INDIRECT",
        status="EXCLUDED",
    )

    finding1 = ValidationFinding(
        rule_id="REG-VAL-001",
        rule_name="Dose Threshold Integrity",
        severity="INFO",
        message="Dose modification within approved pediatric safety threshold.",
        passed=True,
    )
    finding2 = ValidationFinding(
        rule_id="REG-VAL-002",
        rule_name="Cross-Section Coordination",
        severity="WARNING",
        message="Coordinated update in Warnings section verified.",
        passed=True,
    )

    change = ProposedChange(
        change_id="chg_pdf_01",
        decision_id="dec_pdf_01",
        document_name="Pediatric Oncology Core Sheet",
        document_version="4.2",
        section="Dosage and Administration",
        original_text="Initial dosage is 15 mg/m2 orally once daily.",
        proposed_text="Initial dosage is 20 mg/m2 orally once daily with meal.",
        decision_type=ReviewDecisionType.ADAPT,
        rationale="Adjusted to align with updated FDA pediatric clinical guidance.",
        status="APPROVED",
        related_occurrences=[occ_confirmed, occ_excluded],
        validation_findings=[finding1, finding2],
    )

    evidence = EvidenceTrace(
        source="DailyMed",
        source_identifier="spl-fda-9988",
        source_url="https://dailymed.nlm.nih.gov/spl/9988",
        document_name="Reference Drug Label",
        section="Dosage",
        location="Table 2",
        loinc_code="34068-7",
        exact_quote="The recommended starting pediatric dose is 20 mg/m2 once daily with food.",
    )

    return ApprovedChangeReport(
        report_id=report_id,
        document_name="Pediatric Oncology Core Sheet",
        document_version="4.2",
        generated_at="2026-09-26T14:30:00Z",
        author_approver=approver_name,
        decision_ids=["dec_pdf_01"],
        changes=[change],
        source_evidence=[evidence],
        validation_summary="All 1 proposal(s) passed deterministic validation rules.",
        impact_summary="1 modification across 2 sections evaluated.",
        audit_notes="Approved for FDA annual supplement submission package.",
        approval_timestamp="2026-09-26T14:30:00Z",
        approval_confirmation=approval_confirmation,
    )


def create_sample_audit_events(report: ApprovedChangeReport) -> list[AuditEvent]:
    """Generate a realistic SHA-256 hash-chained sequence of audit events."""
    events: list[AuditEvent] = []

    # 1. Decision created (Genesis)
    genesis_hash = compute_event_hash(
        event_id="evt_pdf_01",
        event_type="REVIEWER_DECISION_CREATED",
        occurred_at="2026-09-26T14:00:00Z",
        change_id=None,
        decision_id="dec_pdf_01",
        report_id=None,
        reviewer_name="Dr. Eleanor Vance, PharmD",
        previous_status=None,
        new_status="ADAPT",
        details={"decision": "ADAPT"},
        previous_state=None,
        new_state={"decision_id": "dec_pdf_01", "decision": "ADAPT"},
        previous_event_hash="0" * 64,
    )
    e1 = AuditEvent(
        event_id="evt_pdf_01",
        event_type="REVIEWER_DECISION_CREATED",
        occurred_at="2026-09-26T14:00:00Z",
        decision_id="dec_pdf_01",
        reviewer_name="Dr. Eleanor Vance, PharmD",
        new_status="ADAPT",
        details={"decision": "ADAPT"},
        previous_event_hash="0" * 64,
        event_hash=genesis_hash,
    )
    events.append(e1)

    # 2. Proposal created
    h2 = compute_event_hash(
        event_id="evt_pdf_02",
        event_type="CHANGE_PROPOSAL_CREATED",
        occurred_at="2026-09-26T14:05:00Z",
        change_id="chg_pdf_01",
        decision_id="dec_pdf_01",
        report_id=None,
        reviewer_name=None,
        previous_status=None,
        new_status="PROPOSED",
        details={"section": "Dosage and Administration"},
        previous_state=None,
        new_state={"status": "PROPOSED"},
        previous_event_hash=genesis_hash,
    )
    e2 = AuditEvent(
        event_id="evt_pdf_02",
        event_type="CHANGE_PROPOSAL_CREATED",
        occurred_at="2026-09-26T14:05:00Z",
        change_id="chg_pdf_01",
        decision_id="dec_pdf_01",
        new_status="PROPOSED",
        details={"section": "Dosage and Administration"},
        previous_event_hash=genesis_hash,
        event_hash=h2,
    )
    events.append(e2)

    # 3. Report created
    h3 = compute_event_hash(
        event_id="evt_pdf_03",
        event_type="APPROVED_REPORT_CREATED",
        occurred_at="2026-09-26T14:30:00Z",
        change_id=None,
        decision_id=None,
        report_id=report.report_id,
        reviewer_name="Dr. Eleanor Vance, PharmD",
        previous_status=None,
        new_status="APPROVED",
        details={"report_id": report.report_id},
        previous_state=None,
        new_state={"report_id": report.report_id},
        previous_event_hash=h2,
    )
    e3 = AuditEvent(
        event_id="evt_pdf_03",
        event_type="APPROVED_REPORT_CREATED",
        occurred_at="2026-09-26T14:30:00Z",
        report_id=report.report_id,
        reviewer_name="Dr. Eleanor Vance, PharmD",
        new_status="APPROVED",
        details={"report_id": report.report_id},
        previous_event_hash=h2,
        event_hash=h3,
    )
    events.append(e3)

    return events


# ==============================================================================
# 1. CORE GENERATION SERVICE TESTS
# ==============================================================================


def test_approved_report_pdf_generation_bytes():
    """Verify that an approved report generates valid, non-empty PDF bytes starting with %PDF-."""
    report = create_sample_approved_report()
    generator = PDFReportGenerator()

    pdf_bytes = generator.generate(report)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF-")


def test_pdf_contains_required_sections_in_extracted_text():
    """Verify all 11 required regulatory and governance sections are present in extracted text."""
    report = create_sample_approved_report()
    audit_events = create_sample_audit_events(report)
    generator = PDFReportGenerator()

    pdf_bytes = generator.generate(report, audit_events=audit_events)

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join(page.extract_text() for page in reader.pages)

    # 1. Report Title
    assert "Regulatory Content Reuse Finder" in full_text
    assert "Approved Change Report" in full_text

    # 2. Governance Disclaimer
    assert "GOVERNANCE & STATUTORY DISCLAIMER" in full_text
    assert "internal, human-reviewed regulatory content reuse" in full_text
    assert "does NOT constitute statutory FDA, EMA" in full_text

    # 3. Document Metadata
    assert report.report_id in full_text
    assert "Pediatric Oncology Core Sheet" in full_text
    assert "4.2" in full_text
    assert "Dr. Eleanor Vance, PharmD" in full_text
    assert "CONFIRMED & AUTHORIZED" in full_text

    # 4. Executive Decision Summary
    assert "Executive Decision Summary" in full_text
    assert "Approved for FDA annual supplement submission package." in full_text

    # 5. Change Impact Summary
    assert "Change Impact Summary" in full_text
    assert "1 modification across 2 sections evaluated." in full_text

    # 6. Approved Regulatory Modifications
    assert "Dosage and Administration" in full_text
    assert "Initial dosage is 15 mg/m2 orally once daily." in full_text
    assert "Initial dosage is 20 mg/m2 orally once daily with meal." in full_text
    assert "Adjusted to align with updated FDA pediatric clinical guidance." in full_text
    assert "ADAPT" in full_text

    # 7. Evidence and Provenance
    assert "DailyMed" in full_text
    assert "spl-fda-9988" in full_text
    assert "https://dailymed.nlm.nih.gov/spl/9988" in full_text
    assert "The recommended starting pediatric dose is 20 mg/m2 once daily with food." in full_text

    # 8. Related Occurrence Disposition
    assert "CONFIRMED" in full_text
    assert "EXCLUDED" in full_text
    assert "Warnings and Precautions" in full_text
    assert "Clinical Pharmacology" in full_text

    # 9. Validation Findings
    assert "REG-VAL-001" in full_text
    assert "REG-VAL-002" in full_text
    assert "Dose modification within approved pediatric safety threshold." in full_text

    # 10. Audit Trail & Hash Integrity
    assert "Tamper-Evident Audit Trail" in full_text
    assert "evt_pdf_01" in full_text
    assert "evt_pdf_03" in full_text
    assert audit_events[0].event_hash in full_text
    assert audit_events[2].event_hash in full_text

    # 11. Final Approval Sign-off
    assert "Regulatory Sign-off & Human Authorization" in full_text
    assert "Dr. Eleanor Vance, PharmD" in full_text


def test_pdf_preserves_exact_sha256_audit_hashes():
    """Verify that existing SHA-256 audit hashes are included verbatim in the generated PDF."""
    report = create_sample_approved_report()
    audit_events = create_sample_audit_events(report)
    generator = PDFReportGenerator()

    pdf_bytes = generator.generate(report, audit_events=audit_events)

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join(page.extract_text() for page in reader.pages)

    for event in audit_events:
        assert event.event_hash in full_text
        if event.previous_event_hash:
            assert event.previous_event_hash in full_text


def test_pdf_minimal_report_fallback_rendering():
    """Verify minimal report with absent optional fields renders without errors."""
    minimal_report = ApprovedChangeReport(
        report_id="rep_minimal_01",
        author_approver="Reviewer Jane",
        approval_confirmation=True,
    )
    generator = PDFReportGenerator()

    pdf_bytes = generator.generate(minimal_report)

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "rep_minimal_01" in full_text
    assert "Reviewer Jane" in full_text
    assert "Not Specified" in full_text


# ==============================================================================
# 2. HTTP ENDPOINT TESTS (GET /changes/report/{report_id}/pdf)
# ==============================================================================


def test_pdf_endpoint_returns_200_for_approved_report():
    """Verify GET /changes/report/{report_id}/pdf returns 200 and application/pdf."""
    report = create_sample_approved_report(report_id="rep_api_test_200")
    change_manager.store.save_report(report)

    resp = client.get(f"/changes/report/{report.report_id}/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert (
        resp.headers["content-disposition"]
        == f'attachment; filename="Approved_Change_Report_{report.report_id}.pdf"'
    )
    assert resp.content.startswith(b"%PDF-")
    assert len(resp.content) > 1000


def test_pdf_endpoint_missing_report_returns_404():
    """Verify GET /changes/report/{report_id}/pdf returns 404 when report does not exist."""
    resp = client.get("/changes/report/rep_nonexistent_xyz/pdf")

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_pdf_endpoint_unapproved_report_returns_400():
    """Verify GET /changes/report/{report_id}/pdf rejects unapproved reports with HTTP 400."""
    unapproved_report = create_sample_approved_report(
        report_id="rep_unapproved_test",
        approval_confirmation=False,
    )
    change_manager.store.save_report(unapproved_report)

    resp = client.get(f"/changes/report/{unapproved_report.report_id}/pdf")

    assert resp.status_code == 400
    assert "human regulatory approval" in resp.json()["detail"].lower()


def test_pdf_generation_does_not_mutate_stored_report():
    """Verify that generating and downloading a PDF does NOT mutate the stored report or audit state."""
    report = create_sample_approved_report(report_id="rep_idempotency_test")
    change_manager.store.save_report(report)

    # Initial snapshot
    initial_stored = change_manager.store.get_report(report.report_id)
    assert initial_stored is not None
    initial_dump = initial_stored.model_dump_json()
    initial_event_count = len(change_manager.store.list_audit_events())

    # Download PDF via HTTP endpoint multiple times
    resp1 = client.get(f"/changes/report/{report.report_id}/pdf")
    assert resp1.status_code == 200

    resp2 = client.get(f"/changes/report/{report.report_id}/pdf")
    assert resp2.status_code == 200

    # Verify report in store is completely identical
    reloaded = change_manager.store.get_report(report.report_id)
    assert reloaded is not None
    assert reloaded.model_dump_json() == initial_dump

    # Verify no audit events were created merely by downloading the PDF
    after_event_count = len(change_manager.store.list_audit_events())
    assert after_event_count == initial_event_count


def test_end_to_end_approval_workflow_to_pdf_export():
    """Verify complete lifecycle: record decision -> formulate proposal -> approve -> download PDF."""
    # 1. Record decision
    dec_resp = client.post(
        "/review/decision",
        json={
            "target_content_id": "e2e_sec_01",
            "decision": "ADAPT",
            "reviewer_name": "Dr. Workflow Lead",
            "reviewer_notes": "Pediatric dosing adaptation required.",
            "adaptation_instructions": "Modify daily dose to 20 mg/m2.",
        },
    )
    assert dec_resp.status_code == 200
    decision_id = dec_resp.json()["decision_id"]

    # 2. Formulate proposal
    prop_resp = client.post(
        "/changes/analyze",
        json={
            "decision_id": decision_id,
            "section": "Dosage and Administration",
            "original_text": "Standard dose is 15 mg/m2.",
            "candidate_text": "Adapted dose is 20 mg/m2.",
            "document_name": "Labeling Document E2E",
            "document_version": "1.0",
        },
    )
    assert prop_resp.status_code == 200
    change_id = prop_resp.json()["change_id"]

    # 3. Approve and generate report
    approve_resp = client.post(
        "/changes/approve",
        json={
            "approver_name": "Dr. Workflow Lead",
            "approval_confirmation": True,
            "document_name": "Labeling Document E2E",
            "document_version": "1.0",
            "audit_notes": "E2E workflow approved for submission.",
            "proposal_ids": [change_id],
        },
    )
    assert approve_resp.status_code == 200
    report_id = approve_resp.json()["report_id"]

    # 4. Download PDF
    pdf_resp = client.get(f"/changes/report/{report_id}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF-")

    # 5. Extract text from generated PDF and verify contents
    reader = pypdf.PdfReader(io.BytesIO(pdf_resp.content))
    extracted = "\n".join(page.extract_text() for page in reader.pages)

    assert "Labeling Document E2E" in extracted
    assert "Dr. Workflow Lead" in extracted
    assert "Dosage and Administration" in extracted
    assert report_id in extracted
    assert "GOVERNANCE & STATUTORY DISCLAIMER" in extracted
