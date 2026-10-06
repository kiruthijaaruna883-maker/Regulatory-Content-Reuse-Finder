"""Focused unit and API tests for Phase 7.4B: Corrected Document Generation API + Audit.

Verifies at minimum:
1. Approved DOCX report can generate/download corrected document.
2. Approved TXT report can generate/download corrected document.
3. Unapproved report is blocked.
4. Pending occurrence blocks endpoint.
5. Excluded occurrence is not changed.
6. Only confirmed occurrence is applied.
7. Correct document_id resolves the correct retained source.
8. Two reports/documents remain isolated.
9. Unsupported PDF is rejected.
10. Generated response has correct Content-Type.
11. Generated response has correct Content-Disposition filename.
12. Successful generation creates CORRECTED_DOCUMENT_GENERATED audit event.
13. Audit event contains artifact SHA-256.
14. Original retained source remains unchanged after API generation.
15. Failed generation does not create a corrected artifact.
16. Failed generation does not incorrectly record a successful generation audit event.
17. Unsupported legacy DOC is rejected.
18. Idempotency: repeated generation returns deterministic bytes without duplicate audit events.
"""

import hashlib
import io
from pathlib import Path
from typing import List, Optional
import docx
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.models.audit import AuditEventType
from app.models.document_change import (
    ApprovedChangeReport,
    ProposedChange,
    RelatedOccurrence,
    ReviewDecisionType,
    ReviewerDecision,
)
from app.routes.document_review import change_manager
from app.services.candidate_store import (
    get_candidate_store,
    reset_candidate_store,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_stores():
    """Reset candidate store and sqlite session for each test."""
    reset_candidate_store()
    change_manager.clear_session()
    yield
    reset_candidate_store()
    change_manager.clear_session()


def make_docx_bytes(paragraphs: list) -> bytes:
    """Create in-memory DOCX bytes from paragraphs."""
    doc = docx.Document()
    for p in paragraphs:
        if isinstance(p, tuple):
            doc.add_heading(p[0], level=p[1])
        else:
            doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_occurrence(
    occurrence_id: str,
    section: str,
    current_text: str,
    status: str = "CONFIRMED",
    matched_text: Optional[str] = None,
) -> RelatedOccurrence:
    """Helper to instantiate a valid RelatedOccurrence model."""
    return RelatedOccurrence(
        occurrence_id=occurrence_id,
        section=section,
        current_text=current_text,
        matched_text=matched_text or current_text,
        status=status,
    )


def make_proposal(
    change_id: str,
    section: str,
    original_text: str,
    proposed_text: str,
    decision_id: str = "dec_default",
    decision_type: ReviewDecisionType = ReviewDecisionType.REUSE,
    rationale: str = "Approved clinical reuse rationale",
    status: str = "APPROVED",
    related_occurrences: Optional[List[RelatedOccurrence]] = None,
) -> ProposedChange:
    """Helper to instantiate a valid ProposedChange model."""
    return ProposedChange(
        change_id=change_id,
        decision_id=decision_id,
        section=section,
        original_text=original_text,
        proposed_text=proposed_text,
        decision_type=decision_type,
        rationale=rationale,
        status=status,
        related_occurrences=related_occurrences or [],
    )


# ==============================================================================
# TEST 1: Approved DOCX report can generate/download corrected document
# ==============================================================================


def test_approved_docx_report_generates_and_downloads_corrected_document():
    """Verify an approved report for a DOCX source generates and downloads corrected DOCX bytes."""
    store = get_candidate_store()
    docx_bytes = make_docx_bytes([
        ("INDICATIONS AND USAGE", 1),
        "Product X is indicated for migraine in adults aged 18 to 65.",
        ("DOSAGE AND ADMINISTRATION", 1),
        "Initial dose: 10 mg once daily.",
    ])
    store.store_source_document(
        document_id="doc_docx_01",
        source_bytes=docx_bytes,
        filename="label_product_x.docx",
        file_format="docx",
    )

    occ = make_occurrence(
        occurrence_id="occ_docx_01",
        section="INDICATIONS AND USAGE",
        current_text="migraine in adults aged 18 to 65",
        status="CONFIRMED",
    )
    change = make_proposal(
        change_id="chg_docx_01",
        section="INDICATIONS AND USAGE",
        original_text="migraine in adults aged 18 to 65",
        proposed_text="migraine in adults aged 18 years and older",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_docx_01",
        document_name="label_product_x.docx",
        document_version="1.0",
        author_approver="Dr. Regulatory Lead",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_docx_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    assert "openxmlformats-officedocument.wordprocessingml.document" in response.headers["content-type"]
    assert 'filename="Corrected_label_product_x.docx"' in response.headers["content-disposition"]

    # Verify output DOCX content
    res_doc = docx.Document(io.BytesIO(response.content))
    all_text = " ".join(p.text for p in res_doc.paragraphs)
    assert "migraine in adults aged 18 years and older" in all_text
    assert "migraine in adults aged 18 to 65" not in all_text


# ==============================================================================
# TEST 2: Approved TXT report can generate/download corrected document
# ==============================================================================


def test_approved_txt_report_generates_and_downloads_corrected_document():
    """Verify an approved report for a TXT source generates and downloads corrected TXT bytes."""
    store = get_candidate_store()
    raw_txt = (
        "CLINICAL PHARMACOLOGY\n"
        "Clearance is reduced by 25% in patients with hepatic impairment.\n"
    ).encode("utf-8")
    store.store_source_document(
        document_id="doc_txt_01",
        source_bytes=raw_txt,
        filename="clinical_pharm.txt",
        file_format="txt",
    )

    occ = make_occurrence(
        occurrence_id="occ_txt_01",
        section="CLINICAL PHARMACOLOGY",
        current_text="reduced by 25%",
        status="CONFIRMED",
    )
    change = make_proposal(
        change_id="chg_txt_01",
        section="CLINICAL PHARMACOLOGY",
        original_text="reduced by 25%",
        proposed_text="reduced by 30%",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_txt_01",
        document_name="clinical_pharm.txt",
        document_version="1.0",
        author_approver="Senior Reviewer",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_txt_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert 'filename="Corrected_clinical_pharm.txt"' in response.headers["content-disposition"]

    corrected_str = response.content.decode("utf-8")
    assert "Clearance is reduced by 30% in patients" in corrected_str
    assert "25%" not in corrected_str


# ==============================================================================
# TEST 3: Unapproved report is blocked
# ==============================================================================


def test_unapproved_report_is_blocked():
    """Verify endpoint rejects report lacking explicit human approval confirmation."""
    store = get_candidate_store()
    raw_txt = b"Some regulatory text."
    store.store_source_document(
        document_id="doc_unapp_01",
        source_bytes=raw_txt,
        filename="draft.txt",
        file_format="txt",
    )

    change = make_proposal(
        change_id="chg_unapp_01",
        section="SECTION 1",
        original_text="Some regulatory text.",
        proposed_text="Updated text.",
    )
    report = ApprovedChangeReport(
        report_id="rep_unapp_01",
        document_name="draft.txt",
        document_version="0.1",
        author_approver="Draft Reviewer",
        approval_confirmation=False,  # Unapproved!
        changes=[change],
        document_id="doc_unapp_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 409
    assert "approval_confirmation=true" in response.json()["detail"]


# ==============================================================================
# TEST 4: Pending occurrence blocks endpoint
# ==============================================================================


def test_pending_occurrence_blocks_endpoint():
    """Verify endpoint rejects generation if any unresolved PENDING occurrence remains."""
    store = get_candidate_store()
    raw_txt = b"Dosage is 10 mg daily."
    store.store_source_document(
        document_id="doc_pend_01",
        source_bytes=raw_txt,
        filename="dosage.txt",
        file_format="txt",
    )

    occ = make_occurrence(
        occurrence_id="occ_pend_01",
        section="DOSAGE",
        current_text="10 mg",
        status="PENDING",  # Unresolved!
    )
    change = make_proposal(
        change_id="chg_pend_01",
        section="DOSAGE",
        original_text="10 mg",
        proposed_text="20 mg",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_pend_01",
        document_name="dosage.txt",
        document_version="1.0",
        author_approver="Reviewer",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_pend_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 409
    assert "PENDING" in response.json()["detail"]


# ==============================================================================
# TEST 5: Excluded occurrence is not changed
# ==============================================================================


def test_excluded_occurrence_is_not_changed():
    """Verify EXCLUDED occurrence remains exactly as it was in the source document."""
    store = get_candidate_store()
    raw_txt = (
        "SECTION A\n"
        "Maximum dose is 50 mg for group 1.\n\n"
        "SECTION B\n"
        "Maximum dose is 50 mg for group 2.\n"
    ).encode("utf-8")
    store.store_source_document(
        document_id="doc_excl_01",
        source_bytes=raw_txt,
        filename="dosing_guide.txt",
        file_format="txt",
    )

    occ_confirmed = make_occurrence(
        occurrence_id="occ_conf_01",
        section="SECTION A",
        current_text="50 mg for group 1",
        status="CONFIRMED",
    )
    occ_excluded = make_occurrence(
        occurrence_id="occ_excl_01",
        section="SECTION B",
        current_text="50 mg for group 2",
        status="EXCLUDED",
    )
    change = make_proposal(
        change_id="chg_excl_01",
        section="SECTION A",
        original_text="50 mg for group 1",
        proposed_text="100 mg for group 1",
        related_occurrences=[occ_confirmed, occ_excluded],
    )
    report = ApprovedChangeReport(
        report_id="rep_excl_01",
        document_name="dosing_guide.txt",
        document_version="1.0",
        author_approver="Lead Auditor",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_excl_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    res_text = response.content.decode("utf-8")
    # Excluded occurrence preserved verbatim
    assert "Maximum dose is 50 mg for group 2." in res_text


# ==============================================================================
# TEST 6: Only confirmed occurrence is applied
# ==============================================================================


def test_only_confirmed_occurrence_is_applied():
    """Verify only CONFIRMED occurrences are modified by the generator."""
    store = get_candidate_store()
    raw_txt = (
        "SECTION A\n"
        "Standard dose: 25 mg.\n\n"
        "SECTION B\n"
        "Standard dose: 25 mg.\n"
    ).encode("utf-8")
    store.store_source_document(
        document_id="doc_conf_only",
        source_bytes=raw_txt,
        filename="dose_conf.txt",
        file_format="txt",
    )

    occ1 = make_occurrence("occ_1", "SECTION A", "Standard dose: 25 mg.", "CONFIRMED")
    occ2 = make_occurrence("occ_2", "SECTION B", "Standard dose: 25 mg.", "EXCLUDED")
    change = make_proposal(
        change_id="chg_conf_only",
        section="SECTION A",
        original_text="Standard dose: 25 mg.",
        proposed_text="Standard dose: 50 mg.",
        related_occurrences=[occ1, occ2],
    )
    report = ApprovedChangeReport(
        report_id="rep_conf_only",
        document_name="dose_conf.txt",
        author_approver="Auditor",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_conf_only",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    res_text = response.content.decode("utf-8")
    assert "SECTION A\nStandard dose: 50 mg." in res_text
    assert "SECTION B\nStandard dose: 25 mg." in res_text


# ==============================================================================
# TEST 7: Correct document_id resolves the correct retained source
# ==============================================================================


def test_correct_document_id_resolves_correct_retained_source():
    """Verify generator resolves document strictly through report.document_id."""
    store = get_candidate_store()
    txt_a = b"DOCUMENT ALPHA: Initial formulation."
    txt_b = b"DOCUMENT BETA: Initial formulation."
    store.store_source_document("doc_alpha", txt_a, "alpha.txt", "txt")
    store.store_source_document("doc_beta", txt_b, "beta.txt", "txt")

    change = make_proposal(
        change_id="chg_b",
        section="GENERAL",
        original_text="Initial formulation.",
        proposed_text="Revised formulation.",
    )
    report = ApprovedChangeReport(
        report_id="rep_beta",
        document_name="beta.txt",
        document_version="1.0",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_beta",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    res_text = response.content.decode("utf-8")
    assert "DOCUMENT BETA: Revised formulation." in res_text
    assert "DOCUMENT ALPHA" not in res_text


# ==============================================================================
# TEST 8: Two reports/documents remain isolated
# ==============================================================================


def test_two_reports_and_documents_remain_isolated():
    """Verify two separate documents/reports operate independently with zero crossover."""
    store = get_candidate_store()
    txt_1 = b"Protocol 1: 5 mg daily dose."
    txt_2 = b"Protocol 2: 10 mg daily dose."
    store.store_source_document("doc_iso_1", txt_1, "proto1.txt", "txt")
    store.store_source_document("doc_iso_2", txt_2, "proto2.txt", "txt")

    rep1 = ApprovedChangeReport(
        report_id="rep_iso_1",
        document_name="proto1.txt",
        document_version="1.0",
        author_approver="Approver 1",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="c1",
            section="P1",
            original_text="5 mg daily dose",
            proposed_text="7.5 mg daily dose",
        )],
        document_id="doc_iso_1",
    )
    rep2 = ApprovedChangeReport(
        report_id="rep_iso_2",
        document_name="proto2.txt",
        document_version="1.0",
        author_approver="Approver 2",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="c2",
            section="P2",
            original_text="10 mg daily dose",
            proposed_text="15 mg daily dose",
        )],
        document_id="doc_iso_2",
    )
    change_manager.record_approved_report(rep1)
    change_manager.record_approved_report(rep2)

    resp1 = client.post(f"/changes/report/{rep1.report_id}/corrected-document")
    resp2 = client.post(f"/changes/report/{rep2.report_id}/corrected-document")

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    out1 = resp1.content.decode("utf-8")
    out2 = resp2.content.decode("utf-8")

    assert "Protocol 1: 7.5 mg daily dose." in out1
    assert "Protocol 2" not in out1
    assert "Protocol 2: 15 mg daily dose." in out2
    assert "Protocol 1" not in out2


# ==============================================================================
# TEST 9: Unsupported PDF is rejected
# ==============================================================================


def test_unsupported_pdf_is_rejected():
    """Verify requesting corrected document generation for PDF source returns 400 Bad Request."""
    store = get_candidate_store()
    pdf_bytes = b"%PDF-1.4 Mock PDF regulatory document content."
    store.store_source_document(
        document_id="doc_pdf_01",
        source_bytes=pdf_bytes,
        filename="submission.pdf",
        file_format="pdf",
    )

    report = ApprovedChangeReport(
        report_id="rep_pdf_01",
        document_name="submission.pdf",
        document_version="1.0",
        author_approver="Lead Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="c_pdf",
            section="SUMMARY",
            original_text="Mock PDF",
            proposed_text="Updated PDF",
        )],
        document_id="doc_pdf_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 400
    assert "input-only" in response.json()["detail"].lower()


# ==============================================================================
# TEST 10: Generated response has correct Content-Type
# ==============================================================================


def test_generated_response_content_type_headers():
    """Verify correct MIME types are returned for DOCX and TXT."""
    store = get_candidate_store()

    # DOCX
    docx_bytes = make_docx_bytes(["Sample text for docx."])
    store.store_source_document("doc_mime_docx", docx_bytes, "test.docx", "docx")
    rep_docx = ApprovedChangeReport(
        report_id="rep_mime_docx",
        document_name="test.docx",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[make_proposal(change_id="cd", section="S", original_text="Sample text", proposed_text="Updated text")],
        document_id="doc_mime_docx",
    )
    change_manager.record_approved_report(rep_docx)
    resp_docx = client.post(f"/changes/report/{rep_docx.report_id}/corrected-document")
    assert resp_docx.status_code == 200
    assert resp_docx.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    # TXT
    store.store_source_document("doc_mime_txt", b"Sample text for txt.", "test.txt", "txt")
    rep_txt = ApprovedChangeReport(
        report_id="rep_mime_txt",
        document_name="test.txt",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[make_proposal(change_id="ct", section="S", original_text="Sample text", proposed_text="Updated text")],
        document_id="doc_mime_txt",
    )
    change_manager.record_approved_report(rep_txt)
    resp_txt = client.post(f"/changes/report/{rep_txt.report_id}/corrected-document")
    assert resp_txt.status_code == 200
    assert resp_txt.headers["content-type"] == "text/plain; charset=utf-8"


# ==============================================================================
# TEST 11: Generated response has correct Content-Disposition filename
# ==============================================================================


def test_generated_response_content_disposition_filename():
    """Verify Content-Disposition header formats filename correctly."""
    store = get_candidate_store()
    store.store_source_document("doc_disp", b"Section content here.", "clinical_summary_v2.txt", "txt")
    report = ApprovedChangeReport(
        report_id="rep_disp",
        document_name="clinical_summary_v2.txt",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[make_proposal(change_id="cdisp", section="S", original_text="content", proposed_text="overview")],
        document_id="doc_disp",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="Corrected_clinical_summary_v2.txt"'


# ==============================================================================
# TEST 12: Successful generation creates CORRECTED_DOCUMENT_GENERATED audit event
# ==============================================================================


def test_successful_generation_creates_audit_event():
    """Verify successful generation records CORRECTED_DOCUMENT_GENERATED event in audit history."""
    store = get_candidate_store()
    raw = b"Clinical pharmacology data: AUC is 120."
    store.store_source_document("doc_audit_evt", raw, "pk_evt.txt", "txt")

    change = make_proposal(
        change_id="chg_evt",
        section="PK",
        original_text="AUC is 120",
        proposed_text="AUC is 140",
    )
    report = ApprovedChangeReport(
        report_id="rep_audit_evt",
        document_name="pk_evt.txt",
        author_approver="Dr. Auditor",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_audit_evt",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200

    events = change_manager.list_audit_events_for_report(report)
    gen_events = [e for e in events if e.event_type == AuditEventType.CORRECTED_DOCUMENT_GENERATED.value]

    assert len(gen_events) == 1
    assert gen_events[0].report_id == report.report_id
    assert gen_events[0].reviewer_name == "Dr. Auditor"


# ==============================================================================
# TEST 13: Audit event contains artifact SHA-256
# ==============================================================================


def test_audit_event_contains_artifact_sha256():
    """Verify audit event details contain matching SHA-256 hash of generated bytes."""
    store = get_candidate_store()
    raw = b"Clinical pharmacology data: AUC is 120."
    store.store_source_document("doc_audit_sha", raw, "pk_sha.txt", "txt")

    change = make_proposal(
        change_id="chg_sha",
        section="PK",
        original_text="AUC is 120",
        proposed_text="AUC is 140",
    )
    report = ApprovedChangeReport(
        report_id="rep_audit_sha",
        document_name="pk_sha.txt",
        author_approver="Dr. Pharmacometrics",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_audit_sha",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    expected_hash = hashlib.sha256(response.content).hexdigest()

    events = change_manager.list_audit_events_for_report(report)
    gen_events = [e for e in events if e.event_type == AuditEventType.CORRECTED_DOCUMENT_GENERATED.value]

    assert len(gen_events) == 1
    evt = gen_events[0]
    assert evt.details["sha256_hash"] == expected_hash
    assert evt.details["size_bytes"] == len(response.content)
    assert evt.details["document_id"] == "doc_audit_sha"
    assert evt.details["output_filename"] == "Corrected_pk_sha.txt"


# ==============================================================================
# TEST 14: Original retained source remains unchanged after API generation
# ==============================================================================


def test_original_retained_source_remains_unchanged_after_api_generation():
    """Verify API generation does not alter original retained source bytes in candidate store."""
    store = get_candidate_store()
    original_bytes = b"IMMUTABLE SOURCE TEXT: Dose = 50 mg."
    store.store_source_document("doc_imm_api", original_bytes, "immutable.txt", "txt")

    report = ApprovedChangeReport(
        report_id="rep_imm_api",
        document_name="immutable.txt",
        author_approver="Lead Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_imm",
            section="MAIN",
            original_text="50 mg",
            proposed_text="100 mg",
        )],
        document_id="doc_imm_api",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200

    # Retained original bytes must be identical
    retained = store.get_source_document("doc_imm_api")
    assert retained is not None
    assert retained.source_bytes == original_bytes


# ==============================================================================
# TEST 15: Failed generation does not create a corrected artifact
# ==============================================================================


def test_failed_generation_does_not_create_corrected_artifact():
    """Verify failed generation returns an HTTP error and no document artifact."""
    store = get_candidate_store()
    raw = b"Source text."
    store.store_source_document("doc_fail_art", raw, "fail_art.txt", "txt")

    report = ApprovedChangeReport(
        report_id="rep_fail_art",
        document_name="fail_art.txt",
        author_approver="Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_fail_art",
            section="NONEXISTENT",
            original_text="DOES_NOT_EXIST_ANYWHERE",
            proposed_text="Replacement",
        )],
        document_id="doc_fail_art",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code in (400, 409)
    # Ensure error response is JSON error detail, not file artifact
    assert "attachment" not in response.headers.get("content-disposition", "")
    assert "detail" in response.json()


# ==============================================================================
# TEST 16: Failed generation does not record an audit event
# ==============================================================================


def test_failed_generation_does_not_record_audit_event():
    """Verify failed generation does not append a CORRECTED_DOCUMENT_GENERATED audit event."""
    store = get_candidate_store()
    raw = b"Source text."
    store.store_source_document("doc_fail_aud", raw, "fail_aud.txt", "txt")

    report = ApprovedChangeReport(
        report_id="rep_fail_aud",
        document_name="fail_aud.txt",
        author_approver="Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_fail_aud",
            section="NONEXISTENT",
            original_text="DOES_NOT_EXIST_ANYWHERE",
            proposed_text="Replacement",
        )],
        document_id="doc_fail_aud",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code in (400, 409)

    events = change_manager.list_audit_events_for_report(report)
    gen_events = [e for e in events if e.event_type == AuditEventType.CORRECTED_DOCUMENT_GENERATED.value]
    assert len(gen_events) == 0


# ==============================================================================
# TEST 17: Unsupported legacy DOC is rejected
# ==============================================================================


def test_unsupported_legacy_doc_is_rejected():
    """Verify legacy binary .doc format is rejected as input-only with 400 Bad Request."""
    store = get_candidate_store()
    doc_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 legacy doc bytes"
    store.store_source_document("doc_legacy_01", doc_bytes, "legacy.doc", "doc")

    report = ApprovedChangeReport(
        report_id="rep_legacy_01",
        document_name="legacy.doc",
        author_approver="Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_leg",
            section="S",
            original_text="legacy",
            proposed_text="modern",
        )],
        document_id="doc_legacy_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 400
    assert "input-only" in response.json()["detail"].lower()


# ==============================================================================
# TEST 18: Idempotent repeated generation does not duplicate audit records
# ==============================================================================


def test_idempotent_repeated_generation():
    """Verify repeated generation produces identical bytes without duplicate audit events."""
    store = get_candidate_store()
    raw = b"Repeated generation test document content."
    store.store_source_document("doc_rep_01", raw, "repeat.txt", "txt")

    report = ApprovedChangeReport(
        report_id="rep_repeat_01",
        document_name="repeat.txt",
        author_approver="Auditor Repeated",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_rep",
            section="SEC",
            original_text="test document content",
            proposed_text="verified content",
        )],
        document_id="doc_rep_01",
    )
    change_manager.record_approved_report(report)

    # First generation
    resp1 = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert resp1.status_code == 200

    # Second generation
    resp2 = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert resp2.status_code == 200

    assert resp1.content == resp2.content

    events = change_manager.list_audit_events_for_report(report)
    gen_events = [e for e in events if e.event_type == AuditEventType.CORRECTED_DOCUMENT_GENERATED.value]
    assert len(gen_events) == 1
