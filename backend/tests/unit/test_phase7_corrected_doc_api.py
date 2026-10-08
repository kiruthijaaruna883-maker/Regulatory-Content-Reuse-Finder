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
# ==============================================================================
# TEST 9: Approved PDF report generates and downloads corrected PDF
# ==============================================================================


def make_pdf_bytes(lines: list, pagesize=(612, 792)) -> bytes:
    """Create in-memory PDF bytes from lines of text."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=pagesize)
    c.setFont("Helvetica", 12)
    y = 720
    for item in lines:
        if item == "---PAGE---":
            c.showPage()
            c.setFont("Helvetica", 12)
            y = 720
        else:
            c.drawString(72, y, str(item))
            y -= 25
    c.save()
    return buf.getvalue()


def test_approved_pdf_workflow_generates_corrected_pdf():
    """Verify an approved PDF report generates a new corrected PDF artifact."""
    import pypdf

    original_text = "Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours."
    pdf_bytes = make_pdf_bytes([
        "1. DOSAGE AND ADMINISTRATION",
        original_text,
    ])
    files = {
        "file": (
            "Acetaminophen_Dose.pdf",
            io.BytesIO(pdf_bytes),
            "application/pdf",
        )
    }

    # 1. Ingest PDF
    res_ingest = client.post("/documents/ingest", files=files)
    assert res_ingest.status_code == 200
    ingest_data = res_ingest.json()
    doc_id = ingest_data["document_id"]
    assert doc_id is not None
    sections = ingest_data["sections"]
    assert len(sections) > 0

    target_sec = next(s for s in sections if original_text in s["text"])

    # 2. Record decision
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": target_sec["content_id"],
            "decision": "ADAPT",
            "reviewer_name": "Senior Medical Officer",
            "reviewer_notes": "Revise dose interval",
            "adaptation_instructions": "Adults: Take 1 tablet (500 mg) orally every 6 to 8 hours.",
        },
    )
    assert res_dec.status_code == 200
    dec_id = res_dec.json()["decision_id"]

    # 3. Formulate proposal
    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": dec_id,
            "section": "DOSAGE AND ADMINISTRATION",
            "original_text": original_text,
            "document_name": "Acetaminophen_Dose.pdf",
            "document_id": doc_id,
        },
    )
    assert res_prop.status_code == 200
    prop_id = res_prop.json()["change_id"]

    # 4. Approve report
    res_rep = client.post(
        "/changes/approve",
        json={
            "approver_name": "Lead Regulatory Approver",
            "approval_confirmation": True,
            "proposal_ids": [prop_id],
            "document_name": "Acetaminophen_Dose.pdf",
        },
    )
    assert res_rep.status_code == 200
    rep_id = res_rep.json()["report_id"]
    assert res_rep.json()["document_id"] == doc_id

    # 5. Request corrected document
    response = client.post(f"/changes/report/{rep_id}/corrected-document")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert 'attachment; filename="Corrected_Acetaminophen_Dose.pdf"' in response.headers["content-disposition"]

    # 6. Verify valid PDF that can be opened by pypdf
    out_reader = pypdf.PdfReader(io.BytesIO(response.content))
    assert len(out_reader.pages) >= 1


def test_pdf_source_immutability_during_corrected_generation():
    """Verify original retained PDF bytes and SHA-256 hash remain strictly immutable."""
    import pypdf

    store = get_candidate_store()
    pdf_bytes = make_pdf_bytes([
        "Original immutable PDF source content that must never be altered.",
    ])
    pre_hash = hashlib.sha256(pdf_bytes).hexdigest()
    store.store_source_document("doc_pdf_immut", pdf_bytes, "immutable_source.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_immut",
        document_name="immutable_source.pdf",
        document_version="1.0",
        author_approver="Lead Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="c_pdf_im",
            section="GENERAL",
            original_text="Original immutable PDF source content",
            proposed_text="Updated regulatory PDF source content",
        )],
        document_id="doc_pdf_immut",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200

    retained_after = store.get_source_document("doc_pdf_immut")
    post_hash = hashlib.sha256(bytes(retained_after.source_bytes)).hexdigest()
    assert pre_hash == post_hash
    assert bytes(retained_after.source_bytes) == pdf_bytes


def test_pdf_corrected_document_actual_replacement():
    """Verify approved replacement text is present in the output PDF and unrelated text remains."""
    import pypdf

    store = get_candidate_store()
    phrase_original = "Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours."
    phrase_replacement = "Adults: Take 1 tablet (500 mg) orally every 6 to 8 hours."
    phrase_unrelated = "Warnings: Keep out of reach of children."

    pdf_bytes = make_pdf_bytes([
        "1. DOSAGE AND ADMINISTRATION",
        phrase_original,
        phrase_unrelated,
    ])
    store.store_source_document("doc_pdf_replace", pdf_bytes, "dosage_guide.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_replace",
        document_name="dosage_guide.pdf",
        document_version="1.0",
        author_approver="Chief Reviewer",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="c_pdf_rep",
            section="DOSAGE AND ADMINISTRATION",
            original_text=phrase_original,
            proposed_text=phrase_replacement,
        )],
        document_id="doc_pdf_replace",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200

    reader = pypdf.PdfReader(io.BytesIO(response.content))
    out_text = reader.pages[0].extract_text()
    assert phrase_replacement in out_text
    assert phrase_unrelated in out_text


def test_pdf_approval_gate_blocks_unapproved_generation():
    """Verify attempt to generate corrected PDF without approval confirmation is blocked."""
    store = get_candidate_store()
    pdf_bytes = make_pdf_bytes(["Test content for unapproved PDF."])
    store.store_source_document("doc_pdf_unapp", pdf_bytes, "unapproved.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_unapp",
        document_name="unapproved.pdf",
        author_approver="Auditor",
        approval_confirmation=False,
        changes=[make_proposal(
            change_id="c_pdf_unapp",
            section="GENERAL",
            original_text="Test content",
            proposed_text="Changed content",
            status="PROPOSED",
        )],
        document_id="doc_pdf_unapp",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 409
    assert "approval confirmation" in response.json()["detail"].lower()


def test_pdf_unresolved_target_raises_controlled_error():
    """Verify a target text that does not exist in the source PDF fails with TargetResolutionError (HTTP 409)."""
    store = get_candidate_store()
    pdf_bytes = make_pdf_bytes(["Real source content that exists in the PDF document."])
    store.store_source_document("doc_pdf_notfound", pdf_bytes, "notfound.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_notfound",
        document_name="notfound.pdf",
        author_approver="Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="c_pdf_nf",
            section="GENERAL",
            original_text="Nonexistent phantom text that is definitely not in the PDF",
            proposed_text="Replacement text",
        )],
        document_id="doc_pdf_notfound",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 409
    assert "zero matches" in response.json()["detail"].lower()



# ==============================================================================
# TEST 10: Generated response has correct Content-Type
# ==============================================================================


def test_generated_response_content_type_headers():
    """Verify correct MIME types are returned for DOCX, TXT, and PDF."""
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

    # PDF
    pdf_bytes = make_pdf_bytes(["Sample text for pdf."])
    store.store_source_document("doc_mime_pdf", pdf_bytes, "test.pdf", "pdf")
    rep_pdf = ApprovedChangeReport(
        report_id="rep_mime_pdf",
        document_name="test.pdf",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[make_proposal(change_id="cp", section="S", original_text="Sample text", proposed_text="Updated text")],
        document_id="doc_mime_pdf",
    )
    change_manager.record_approved_report(rep_pdf)
    resp_pdf = client.post(f"/changes/report/{rep_pdf.report_id}/corrected-document")
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"


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


# ==============================================================================
# TEST 19: Ingested DOCX exposes real parsed source text in sections
# ==============================================================================


def test_uploaded_docx_exposes_real_parsed_source_text():
    """Verify an uploaded DOCX exposes real parsed source text in ingestion response."""
    paragraphs = [
        ("1. INDICATIONS AND USAGE", 1),
        "Acetaminophen is indicated for temporary relief of minor aches and pains.",
        ("2. DOSAGE AND ADMINISTRATION", 1),
        "Adults and children 12 years and older: Take 2 tablets (650 mg) every 6 hours.",
    ]
    docx_bytes = make_docx_bytes(paragraphs)
    files = {
        "file": (
            "SYN-ACET-001_Synthetic_Regulatory_Test.docx",
            io.BytesIO(docx_bytes),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    response = client.post("/documents/ingest", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] is not None
    assert "sections" in data
    assert len(data["sections"]) > 0

    # Ensure exposed sections contain actual document text, not synthetic metadata
    texts = [s["text"] for s in data["sections"]]
    assert any("minor aches and pains" in t for t in texts)
    assert any("Adults and children 12 years" in t for t in texts)
    for t in texts:
        assert not t.startswith("File:")
        assert "content sections in store" not in t


# ==============================================================================
# TEST 20: Synthetic file metadata string rejected as original_text
# ==============================================================================


def test_synthetic_metadata_rejected_as_original_text():
    """Verify synthetic file metadata string can never become original_text for change proposals."""
    store = get_candidate_store()
    raw = b"Dummy content for test."
    store.store_source_document("doc_synth_test", raw, "test.docx", "docx")
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": "dummy_content_id",
            "decision": "ADAPT",
            "reviewer_name": "Dr. Reviewer",
            "reviewer_notes": "Clinical review notes",
            "adaptation_instructions": "Adapt instructions",
        },
    )
    assert res_dec.status_code == 200
    dec_id = res_dec.json()["decision_id"]

    # Attempt to pass synthetic status string as original_text
    synth_text = "File: SYN-ACET-001_Synthetic_Regulatory_Test.docx (Registered 62 content sections in store)"
    res_analyze = client.post(
        "/changes/analyze",
        json={
            "decision_id": dec_id,
            "section": "Dosage",
            "original_text": synth_text,
            "document_name": "SYN-ACET-001_Synthetic_Regulatory_Test.docx",
            "document_id": "doc_synth_test",
        },
    )
    assert res_analyze.status_code == 422
    assert "synthetic ingestion status/metadata strings cannot be used as target text" in res_analyze.json()["detail"]


# ==============================================================================
# TEST 21: Real source passage flows through corrected DOCX generation successfully
# ==============================================================================


def test_real_source_passage_flows_through_corrected_docx_generation():
    """Verify a real source passage from an uploaded DOCX flows through change proposal to corrected docx."""
    original_passage = "Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours with water."
    paragraphs = [
        ("1. DOSAGE AND ADMINISTRATION", 1),
        original_passage,
    ]
    docx_bytes = make_docx_bytes(paragraphs)
    files = {
        "file": (
            "Acetaminophen_Dose_Guide.docx",
            io.BytesIO(docx_bytes),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }

    # 1. Ingest DOCX
    res_ingest = client.post("/documents/ingest", files=files)
    assert res_ingest.status_code == 200
    ingest_data = res_ingest.json()
    doc_id = ingest_data["document_id"]
    sections = ingest_data["sections"]
    assert len(sections) > 0

    # Pick real section containing the passage
    target_sec = next(s for s in sections if original_passage in s["text"])
    real_text = target_sec["text"]

    # 2. Record decision
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": target_sec["content_id"],
            "decision": "ADAPT",
            "reviewer_name": "Senior Medical Reviewer",
            "reviewer_notes": "Update dosage interval per revised guidance.",
            "adaptation_instructions": "Change interval to every 6 to 8 hours with full glass of water.",
        },
    )
    assert res_dec.status_code == 200
    dec_id = res_dec.json()["decision_id"]

    # 3. Analyze change proposal with REAL source passage
    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": dec_id,
            "section": target_sec.get("section") or "DOSAGE AND ADMINISTRATION",
            "original_text": real_text,
            "document_name": "Acetaminophen_Dose_Guide.docx",
            "document_id": doc_id,
        },
    )
    assert res_prop.status_code == 200
    prop_data = res_prop.json()
    assert prop_data["original_text"] == real_text
    assert not prop_data["original_text"].startswith("File:")
    prop_id = prop_data["change_id"]

    # 4. Approve report
    res_rep = client.post(
        "/changes/approve",
        json={
            "approver_name": "Lead Regulatory Approver",
            "approval_confirmation": True,
            "proposal_ids": [prop_id],
            "document_name": "Acetaminophen_Dose_Guide.docx",
        },
    )
    assert res_rep.status_code == 200
    rep_id = res_rep.json()["report_id"]
    assert res_rep.json()["document_id"] == doc_id

    # 5. Generate corrected document
    res_corr = client.post(f"/changes/report/{rep_id}/corrected-document")
    assert res_corr.status_code == 200
    assert res_corr.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    # Verify generated document bytes contains synthesized adaptation and NOT original passage
    corr_doc = docx.Document(io.BytesIO(res_corr.content))
    corr_full_text = "\n".join(p.text for p in corr_doc.paragraphs)
    assert prop_data["proposed_text"] in corr_full_text
    assert original_passage not in corr_full_text


# ==============================================================================
# TEST 22: PDF Regression A — [Page N] breadcrumb prefix separates cleanly
# ==============================================================================


def test_pdf_regression_page_breadcrumb_prefix():
    """Verify target text with [Page N] prefix cleanly separates metadata and corrects page N."""
    import pypdf

    store = get_candidate_store()
    phrase_physical = "Patients should carefully read the dosage instructions before using the product."
    phrase_target = f"[Page 3]\n{phrase_physical}"
    phrase_rep = "Patients MUST review the dosage guidelines before product administration."

    # 3-page PDF where physical page 3 has the text without [Page 3]
    pdf_bytes = make_pdf_bytes([
        "Page 1: Overview and background information.",
        "---PAGE---",
        "Page 2: Clinical pharmacology and toxicology.",
        "---PAGE---",
        phrase_physical,
    ])
    store.store_source_document("doc_pdf_reg_a", pdf_bytes, "product_insert.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_reg_a",
        document_name="product_insert.pdf",
        document_version="1.0",
        author_approver="Lead Clinical Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_reg_a",
            section="Page 3",
            original_text=phrase_target,
            proposed_text=phrase_rep,
        )],
        document_id="doc_pdf_reg_a",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"

    reader = pypdf.PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 3
    # Page 3 extracted text should contain replacement
    p3_text = " ".join((reader.pages[2].extract_text() or "").split())
    assert "Patients MUST review the dosage guidelines" in p3_text
    # Original proposal target text unmodified in model
    assert report.changes[0].original_text == phrase_target


# ==============================================================================
# TEST 23: PDF Regression B — Line wrapping variation between target and PDF
# ==============================================================================


def test_pdf_regression_line_wrapping():
    """Verify target containing normal spaces matches across PDF line breaks."""
    import pypdf

    store = get_candidate_store()
    target_clean = "Patients should carefully read the dosage instructions before using the product."
    rep_text = "Patients MUST read dosage guidelines prior to first dose administration."

    # Physical PDF has line break between 'the' and 'dosage'
    pdf_bytes = make_pdf_bytes([
        "Patients should carefully read the",
        "dosage instructions before using the product.",
    ])
    store.store_source_document("doc_pdf_reg_b", pdf_bytes, "wrap_test.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_reg_b",
        document_name="wrap_test.pdf",
        document_version="1.0",
        author_approver="Review Officer",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_reg_b",
            section="GENERAL",
            original_text=target_clean,
            proposed_text=rep_text,
        )],
        document_id="doc_pdf_reg_b",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200

    reader = pypdf.PdfReader(io.BytesIO(response.content))
    out_text = " ".join((reader.pages[0].extract_text() or "").split())
    assert "Patients MUST read dosage guidelines" in out_text


# ==============================================================================
# TEST 24: PDF Regression C — Unicode punctuation and ligature normalization
# ==============================================================================


def test_pdf_regression_unicode_normalization():
    """Verify deterministic normalization resolves curly quotes, typographic dashes, and ligatures."""
    import pypdf

    store = get_candidate_store()
    # Physical PDF has curly double quotes, en-dash, and ligature 'fi'
    pdf_bytes = make_pdf_bytes([
        '“Dose range: 10–20 mg daily with fluid intake.”',
    ])
    store.store_source_document("doc_pdf_reg_c", pdf_bytes, "unicode_test.pdf", "pdf")

    # Target has straight ASCII quotes, ASCII hyphen '-'
    target_ascii = '"Dose range: 10-20 mg daily with fluid intake."'
    rep_text = '"Dose range: 15-25 mg daily with fluid intake."'

    report = ApprovedChangeReport(
        report_id="rep_pdf_reg_c",
        document_name="unicode_test.pdf",
        document_version="1.0",
        author_approver="Regulatory Approver",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_reg_c",
            section="DOSAGE",
            original_text=target_ascii,
            proposed_text=rep_text,
        )],
        document_id="doc_pdf_reg_c",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200

    reader = pypdf.PdfReader(io.BytesIO(response.content))
    out_text = reader.pages[0].extract_text() or ""
    assert "15-25 mg" in out_text


# ==============================================================================
# TEST 25: PDF Regression D — Duplicate phrase across pages resolves via page_hint
# ==============================================================================


def test_pdf_regression_duplicate_phrase_across_pages_resolved_via_page_hint():
    """Verify duplicate phrase on Page 1 and Page 3 is deterministically resolved to Page 3."""
    import pypdf

    store = get_candidate_store()
    common_phrase = "Administer with a full glass of water."
    target_with_p3 = f"[Page 3]\n{common_phrase}"
    rep_text = "Administer with 8 ounces of water or fruit juice."

    # Page 1 has common_phrase, Page 2 has other, Page 3 has common_phrase
    pdf_bytes = make_pdf_bytes([
        common_phrase,
        "---PAGE---",
        "Intervening clinical content on page 2.",
        "---PAGE---",
        common_phrase,
    ])
    store.store_source_document("doc_pdf_reg_d", pdf_bytes, "duplicate_pages.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_reg_d",
        document_name="duplicate_pages.pdf",
        document_version="1.0",
        author_approver="Lead Reviewer",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_reg_d",
            section="Page 3",
            original_text=target_with_p3,
            proposed_text=rep_text,
        )],
        document_id="doc_pdf_reg_d",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200

    reader = pypdf.PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 3

    # Page 1 must retain the original phrase UNTOUCHED
    p1_text = reader.pages[0].extract_text() or ""
    assert common_phrase in p1_text
    assert rep_text not in p1_text

    # Page 3 must contain the replacement
    p3_text = reader.pages[2].extract_text() or ""
    assert rep_text in p3_text


# ==============================================================================
# TEST 26: PDF Regression E — Genuine same-page ambiguity raises TargetResolutionError
# ==============================================================================


def test_pdf_regression_same_page_ambiguity_raises_target_resolution_error():
    """Verify duplicate occurrences on the SAME page with no unique location metadata fails safely."""
    store = get_candidate_store()
    duplicate_phrase = "Administer dose immediately before meals."

    # Both occurrences appear on Page 1
    pdf_bytes = make_pdf_bytes([
        duplicate_phrase,
        "Middle clinical advisory notes.",
        duplicate_phrase,
    ])
    store.store_source_document("doc_pdf_reg_e", pdf_bytes, "same_page_dup.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_reg_e",
        document_name="same_page_dup.pdf",
        document_version="1.0",
        author_approver="Safety Officer",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_reg_e",
            section="GENERAL",
            original_text=duplicate_phrase,
            proposed_text="Administer dose at least 30 minutes after meals.",
        )],
        document_id="doc_pdf_reg_e",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    # Must fail with 409 Conflict (TargetResolutionError)
    assert response.status_code == 409
    err_msg = response.json()["detail"].lower()
    assert "multiple ambiguous matches" in err_msg


# ==============================================================================
# TEST 27: PDF Regression F — Source immutability byte & SHA-256 validation
# ==============================================================================


def test_pdf_regression_source_immutability():
    """Verify source PDF bytes and SHA-256 remain strictly immutable before and after generation."""
    store = get_candidate_store()
    pdf_bytes = make_pdf_bytes([
        "Patients should carefully read the dosage instructions.",
    ])
    pre_sha = hashlib.sha256(pdf_bytes).hexdigest()
    store.store_source_document("doc_pdf_reg_f", pdf_bytes, "immutable_source.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_reg_f",
        document_name="immutable_source.pdf",
        document_version="1.0",
        author_approver="Governance Lead",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_reg_f",
            section="DOSAGE",
            original_text="Patients should carefully read the dosage instructions.",
            proposed_text="Patients MUST carefully read the dosage guidelines.",
        )],
        document_id="doc_pdf_reg_f",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200

    # Retrieve source from store and confirm byte-level equality
    source_after = store.get_source_document("doc_pdf_reg_f")
    assert source_after is not None
    post_sha = hashlib.sha256(bytes(source_after.source_bytes)).hexdigest()
    assert pre_sha == post_sha
    assert bytes(source_after.source_bytes) == pdf_bytes


# ==============================================================================
# TEST 28: PDF Multi-line safe expansion into verified vertical blank space
# ==============================================================================


def test_pdf_multiline_safe_expansion_into_verified_vertical_blank_space():
    """Verify multi-line target expands into verified blank vertical space below without touching downstream content."""
    import pypdf
    from reportlab.pdfgen import canvas

    store = get_candidate_store()
    line1 = "Initial standard dosing guidelines for adult patients:"
    line2 = "Administer 10 mg once daily."
    target_clean = f"{line1} {line2}"
    rep_text = (
        "Revised multi-line clinical dosing protocol: Administer 10 mg orally once daily with food "
        "and water for 14 consecutive days. Maintain regular blood pressure monitoring throughout course."
    )
    downstream_text = "3. CONTRAINDICATIONS AND WARNINGS: Do not administer to patients with hepatic failure."

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, line1)
    c.drawString(72, 695, line2)
    c.drawString(72, 500, downstream_text)
    c.save()
    pdf_bytes = buf.getvalue()

    store.store_source_document("doc_pdf_v_expand", pdf_bytes, "dosage_insert.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_v_expand",
        document_name="dosage_insert.pdf",
        document_version="1.0",
        author_approver="Lead Clinical Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_v_expand",
            section="DOSING",
            original_text=target_clean,
            proposed_text=rep_text,
        )],
        document_id="doc_pdf_v_expand",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"

    reader = pypdf.PdfReader(io.BytesIO(response.content))
    out_text = reader.pages[0].extract_text()
    assert "Revised multi-line clinical dosing protocol" in out_text
    assert "Maintain regular blood pressure monitoring" in out_text
    assert downstream_text in out_text


# ==============================================================================
# TEST 29: PDF Multi-line safe expansion into horizontal whitespace
# ==============================================================================


def test_pdf_multiline_safe_expansion_into_horizontal_whitespace():
    """Verify multi-line target whose final line ends early expands horizontally across safe line width."""
    import pypdf
    from reportlab.pdfgen import canvas

    store = get_candidate_store()
    line1 = "Administer the initial dose in the morning after breakfast"
    line2 = "with water."
    target_clean = f"{line1} {line2}"
    rep_text = (
        "Administer the initial dose in the morning after breakfast "
        "with 8 ounces of pure drinking water or orange juice."
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, line1)
    c.drawString(72, 695, line2)
    c.drawString(72, 640, "4. CLINICAL PHARMACOLOGY: Drug clearance is rapid.")
    c.save()
    pdf_bytes = buf.getvalue()

    store.store_source_document("doc_pdf_h_expand", pdf_bytes, "horiz_test.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_h_expand",
        document_name="horiz_test.pdf",
        document_version="1.0",
        author_approver="Lead Clinical Auditor",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_h_expand",
            section="GENERAL",
            original_text=target_clean,
            proposed_text=rep_text,
        )],
        document_id="doc_pdf_h_expand",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200

    reader = pypdf.PdfReader(io.BytesIO(response.content))
    out_text = " ".join((reader.pages[0].extract_text() or "").split())
    assert "with 8 ounces of pure drinking water or orange juice." in out_text
    assert "4. CLINICAL PHARMACOLOGY: Drug clearance is rapid." in out_text


# ==============================================================================
# TEST 30: PDF Multi-line blocks when obstacle immediately below
# ==============================================================================


def test_pdf_multiline_blocks_when_obstacle_immediately_below():
    """Verify multi-line target fails safely with TargetResolutionError when downstream obstacle prevents expansion."""
    from reportlab.pdfgen import canvas

    store = get_candidate_store()
    line1 = "Standard adult dosage is 10 mg."
    line2 = "Take once daily."
    target_clean = f"{line1} {line2}"
    # Replacement requiring multiple additional lines (>1400pt) that cannot fit in 2 lines even at 8pt
    rep_text = (
        "Revised comprehensive clinical dosing protocol requiring multiple paragraphs of detailed safety instructions: "
        "Administer initial dose of 10 mg orally once daily with food and water for 14 consecutive days. "
        "Patients must maintain regular daily blood pressure monitoring throughout the entire course of therapy. "
        "If systolic pressure exceeds 140 mmHg, immediately withhold administration and contact clinical investigator."
    )
    obstacle_text = "IMMEDIATE DOWNSTREAM SECTION HEADER"

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, line1)
    c.drawString(72, 705, line2)
    c.drawString(72, 692, obstacle_text)
    c.save()
    pdf_bytes = buf.getvalue()

    store.store_source_document("doc_pdf_obs_below", pdf_bytes, "obstacle_test.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_obs_below",
        document_name="obstacle_test.pdf",
        document_version="1.0",
        author_approver="Regulatory Lead",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_obs_below",
            section="DOSING",
            original_text=target_clean,
            proposed_text=rep_text,
        )],
        document_id="doc_pdf_obs_below",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 409
    assert "cannot safely fit" in response.json()["detail"].lower()


# ==============================================================================
# TEST 31: PDF Multi-line blocks at page bottom margin
# ==============================================================================


def test_pdf_multiline_blocks_at_page_bottom_margin():
    """Verify multi-line target fails safely with TargetResolutionError when expansion would cross bottom page margin."""
    from reportlab.pdfgen import canvas

    store = get_candidate_store()
    line1 = "Final footnote instruction line one."
    line2 = "Final footnote instruction line two."
    target_clean = f"{line1} {line2}"
    # Lengthy replacement requiring additional lines (>1400pt) that cannot fit in 2 lines even at 8pt
    rep_text = (
        "Revised comprehensive clinical dosing protocol requiring multiple paragraphs of detailed safety instructions: "
        "Administer initial dose of 10 mg orally once daily with food and water for 14 consecutive days. "
        "Patients must maintain regular daily blood pressure monitoring throughout the entire course of therapy. "
        "If systolic pressure exceeds 140 mmHg, immediately withhold administration and contact clinical investigator."
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    c.drawString(72, 55, line1)
    c.drawString(72, 42, line2)
    c.save()
    pdf_bytes = buf.getvalue()

    store.store_source_document("doc_pdf_bottom_margin", pdf_bytes, "margin_test.pdf", "pdf")

    report = ApprovedChangeReport(
        report_id="rep_pdf_bottom_margin",
        document_name="margin_test.pdf",
        document_version="1.0",
        author_approver="Compliance Officer",
        approval_confirmation=True,
        changes=[make_proposal(
            change_id="chg_bottom_margin",
            section="FOOTNOTE",
            original_text=target_clean,
            proposed_text=rep_text,
        )],
        document_id="doc_pdf_bottom_margin",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 409
    assert "cannot safely fit" in response.json()["detail"].lower()


# ==============================================================================
# PHASE 7 BEHAVIORAL VERIFICATION: REAL TEST DOCUMENT & TARGET EXTRACTION FIXES
# ==============================================================================


def test_behavioral_docx_real_replacement_and_immutability():
    """Verify DOCX: 'The product is administered once daily.' -> 'The product is administered twice daily.'
    - Generated file exists
    - Generated file is not merely the original bytes
    - Corrected phrase is present
    - Original phrase is replaced at the intended location
    - Original source bytes remain unchanged
    """
    store = get_candidate_store()
    orig_docx = make_docx_bytes([
        ("SECTION 1: CLINICAL PHARMACOLOGY", 1),
        "The product is administered once daily.",
        "Maintain monitoring as indicated.",
    ])
    store.store_source_document("doc_behav_docx_01", orig_docx, "label.docx", "docx")

    change = make_proposal(
        change_id="chg_behav_docx_01",
        section="SECTION 1: CLINICAL PHARMACOLOGY",
        original_text="The product is administered once daily.",
        proposed_text="The product is administered twice daily.",
    )
    report = ApprovedChangeReport(
        report_id="rep_behav_docx_01",
        document_name="label.docx",
        document_version="1.0",
        author_approver="QA Reviewer",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_behav_docx_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    gen_bytes = response.content

    # Generated file exists and is not merely original bytes
    assert len(gen_bytes) > 0
    assert gen_bytes != orig_docx

    # Read back generated DOCX content
    doc = docx.Document(io.BytesIO(gen_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs)

    # Corrected phrase is present
    assert "The product is administered twice daily." in full_text
    # Original phrase is replaced
    assert "The product is administered once daily." not in full_text

    # Original source bytes remain unchanged
    retained = store.get_source_document("doc_behav_docx_01")
    assert bytes(retained.source_bytes) == orig_docx


def test_behavioral_txt_crlf_and_multiline_real_replacement_and_immutability():
    """Verify TXT with CRLF and multiline:
    - Generated file exists
    - Generated file is not merely original bytes
    - Corrected phrase is present
    - Original phrase is replaced at intended location
    - Original source bytes remain unchanged
    - CRLF line endings preserved
    """
    store = get_candidate_store()
    orig_text = (
        "SECTION 1: CLINICAL PHARMACOLOGY\r\n"
        "The product is administered once daily.\r\n"
        "Maintain monitoring as indicated.\r\n"
    )
    orig_txt_bytes = orig_text.encode("utf-8")
    store.store_source_document("doc_behav_txt_01", orig_txt_bytes, "label.txt", "txt")

    change = make_proposal(
        change_id="chg_behav_txt_01",
        section="SECTION 1: CLINICAL PHARMACOLOGY",
        original_text="The product is administered once daily.",
        proposed_text="The product is administered twice daily.",
    )
    report = ApprovedChangeReport(
        report_id="rep_behav_txt_01",
        document_name="label.txt",
        document_version="1.0",
        author_approver="QA Reviewer",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_behav_txt_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    gen_bytes = response.content

    assert len(gen_bytes) > 0
    assert gen_bytes != orig_txt_bytes

    gen_text = gen_bytes.decode("utf-8")
    assert "The product is administered twice daily." in gen_text
    assert "The product is administered once daily." not in gen_text
    assert "\r\n" in gen_text

    # Immutability
    retained = store.get_source_document("doc_behav_txt_01")
    assert bytes(retained.source_bytes) == orig_txt_bytes


def test_behavioral_pdf_real_replacement_and_immutability():
    """Verify PDF:
    - Generated file exists
    - Generated file is not merely original bytes
    - Corrected phrase is present in extracted text
    - Original source bytes remain unchanged
    """
    import pypdf
    from reportlab.pdfgen import canvas

    store = get_candidate_store()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    c.drawString(72, 700, "SECTION 1: CLINICAL PHARMACOLOGY")
    c.drawString(72, 680, "The product is administered once daily.")
    c.save()
    orig_pdf_bytes = buf.getvalue()
    store.store_source_document("doc_behav_pdf_01", orig_pdf_bytes, "label.pdf", "pdf")

    change = make_proposal(
        change_id="chg_behav_pdf_01",
        section="SECTION 1: CLINICAL PHARMACOLOGY",
        original_text="The product is administered once daily.",
        proposed_text="The product is administered twice daily.",
    )
    report = ApprovedChangeReport(
        report_id="rep_behav_pdf_01",
        document_name="label.pdf",
        document_version="1.0",
        author_approver="QA Reviewer",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_behav_pdf_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    gen_bytes = response.content

    assert len(gen_bytes) > 0
    assert gen_bytes != orig_pdf_bytes

    # Verify extracted text contains corrected phrase
    reader = pypdf.PdfReader(io.BytesIO(gen_bytes))
    all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "The product is administered twice daily." in all_text

    # Retained original unchanged
    retained = store.get_source_document("doc_behav_pdf_01")
    assert bytes(retained.source_bytes) == orig_pdf_bytes


def test_primary_change_corrected_when_related_occurrences_are_excluded():
    """Verify primary change is STILL corrected even when related occurrences are EXCLUDED."""
    store = get_candidate_store()
    raw_txt = (
        "SECTION 1: CLINICAL PHARMACOLOGY\n"
        "The product is administered once daily.\n\n"
        "SECTION 2: DOSAGE AND ADMINISTRATION\n"
        "The product is administered once daily.\n"
    ).encode("utf-8")
    store.store_source_document("doc_prim_excl_01", raw_txt, "label.txt", "txt")

    occ_excluded = make_occurrence(
        occurrence_id="occ_excl_sec2",
        section="SECTION 2: DOSAGE AND ADMINISTRATION",
        current_text="The product is administered once daily.",
        status="EXCLUDED",
    )
    change = make_proposal(
        change_id="chg_prim_excl_01",
        section="SECTION 1: CLINICAL PHARMACOLOGY",
        original_text="The product is administered once daily.",
        proposed_text="The product is administered twice daily.",
        related_occurrences=[occ_excluded],
    )
    report = ApprovedChangeReport(
        report_id="rep_prim_excl_01",
        document_name="label.txt",
        document_version="1.0",
        author_approver="Lead Auditor",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_prim_excl_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    res_text = response.content.decode("utf-8")

    # Primary change in SECTION 1 was corrected
    assert "SECTION 1: CLINICAL PHARMACOLOGY\nThe product is administered twice daily." in res_text
    # Excluded occurrence in SECTION 2 remains unchanged
    assert "SECTION 2: DOSAGE AND ADMINISTRATION\nThe product is administered once daily." in res_text


def test_primary_change_and_confirmed_occurrence_both_corrected():
    """Verify primary change AND confirmed related occurrence are BOTH corrected."""
    store = get_candidate_store()
    raw_txt = (
        "SECTION 1: CLINICAL PHARMACOLOGY\n"
        "The product is administered once daily.\n\n"
        "SECTION 2: DOSAGE AND ADMINISTRATION\n"
        "The product is administered once daily.\n"
    ).encode("utf-8")
    store.store_source_document("doc_prim_conf_01", raw_txt, "label.txt", "txt")

    occ_confirmed = make_occurrence(
        occurrence_id="occ_conf_sec2",
        section="SECTION 2: DOSAGE AND ADMINISTRATION",
        current_text="The product is administered once daily.",
        status="CONFIRMED",
    )
    change = make_proposal(
        change_id="chg_prim_conf_01",
        section="SECTION 1: CLINICAL PHARMACOLOGY",
        original_text="The product is administered once daily.",
        proposed_text="The product is administered twice daily.",
        related_occurrences=[occ_confirmed],
    )
    report = ApprovedChangeReport(
        report_id="rep_prim_conf_01",
        document_name="label.txt",
        document_version="1.0",
        author_approver="Lead Auditor",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_prim_conf_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 200
    res_text = response.content.decode("utf-8")

    # Both locations corrected
    assert "SECTION 1: CLINICAL PHARMACOLOGY\nThe product is administered twice daily." in res_text
    assert "SECTION 2: DOSAGE AND ADMINISTRATION\nThe product is administered twice daily." in res_text
    assert "once daily" not in res_text


def test_no_valid_textual_change_fails_and_does_not_falsely_report_success():
    """Verify proposal with no textual change (original == proposed) and no confirmed occurrences
    fails with 409 TargetResolutionError and does NOT falsely report successful correction.
    """
    store = get_candidate_store()
    raw_txt = "The product is administered once daily.\n".encode("utf-8")
    store.store_source_document("doc_no_chg_01", raw_txt, "label.txt", "txt")

    change = make_proposal(
        change_id="chg_no_chg_01",
        section="UNSPECIFIED",
        original_text="The product is administered once daily.",
        proposed_text="The product is administered once daily.",
    )
    report = ApprovedChangeReport(
        report_id="rep_no_chg_01",
        document_name="label.txt",
        document_version="1.0",
        author_approver="Lead Auditor",
        approval_confirmation=True,
        changes=[change],
        document_id="doc_no_chg_01",
    )
    change_manager.record_approved_report(report)

    response = client.post(f"/changes/report/{report.report_id}/corrected-document")
    assert response.status_code == 409
    assert "no textual modifications" in response.json()["detail"].lower()
