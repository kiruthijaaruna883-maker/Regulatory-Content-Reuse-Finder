"""Targeted unit tests for Phase 7.4A: Deterministic Corrected Document Generator.

Verifies:
1. TXT confirmed occurrence is corrected.
2. TXT excluded occurrence remains unchanged.
3. TXT pending occurrence blocks generation.
4. Unapproved change/report blocks generation.
5. DOCX confirmed occurrence is corrected.
6. Original TXT bytes remain unchanged.
7. Original DOCX bytes remain unchanged.
8. Zero-match occurrence fails safely.
9. Multiple ambiguous matches fail safely.
10. Multiple confirmed occurrences are all applied correctly.
11. Output artifact has deterministic SHA-256 hash.
12. PDF is rejected as unsupported for correction.
13. No corrected artifact is returned after a failed generation.
14. Two documents remain isolated and cannot modify the wrong source.
15. DOCX table cell occurrences are resolved and corrected.
16. DOCX run-level formatting (bold, etc.) is preserved during targeted correction.
"""

import hashlib
import io
from pathlib import Path
import docx
import pytest

from app.models.document_change import (
    ApprovedChangeReport,
    ProposedChange,
    RelatedOccurrence,
    ReviewDecisionType,
)
from app.services.candidate_store import (
    get_candidate_store,
    reset_candidate_store,
)
from app.services.corrected_document_generator import (
    CorrectedDocumentGenerator,
    CorrectedDocumentResult,
    TargetResolutionError,
    UnapprovedReportError,
    UnresolvedOccurrencesError,
    UnsupportedFormatError,
)


@pytest.fixture(autouse=True)
def clean_store():
    """Reset candidate store before and after each test."""
    reset_candidate_store()
    yield
    reset_candidate_store()


def make_sample_docx(paragraphs=None, table_data=None) -> bytes:
    """Helper to create a sample DOCX byte stream with paragraphs and tables."""
    doc = docx.Document()
    if paragraphs:
        for p_info in paragraphs:
            if isinstance(p_info, str):
                doc.add_paragraph(p_info)
            elif isinstance(p_info, tuple):
                # (heading_text, level)
                doc.add_heading(p_info[0], level=p_info[1])
            elif isinstance(p_info, list):
                # list of runs: [(run_text, is_bold), ...]
                p = doc.add_paragraph()
                for run_text, is_bold in p_info:
                    r = p.add_run(run_text)
                    if is_bold:
                        r.bold = True
    if table_data:
        tbl = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
        for r_idx, row in enumerate(table_data):
            for c_idx, cell_text in enumerate(row):
                tbl.rows[r_idx].cells[c_idx].text = cell_text
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ==============================================================================
# TEST 1: TXT confirmed occurrence is corrected
# ==============================================================================


def test_txt_confirmed_occurrence_is_corrected():
    """Verify a confirmed occurrence in a TXT document is replaced with proposed text."""
    store = get_candidate_store()
    raw_text = (
        "INDICATIONS AND USAGE\n"
        "Indicated for acute migraine attacks in adults.\n\n"
        "DOSAGE AND ADMINISTRATION\n"
        "The initial dose is 10 mg orally once daily.\n"
    )
    store.store_source_document(
        document_id="doc_txt_01",
        source_bytes=raw_text.encode("utf-8"),
        filename="migraine_guide.txt",
        file_format="txt",
    )

    occ = RelatedOccurrence(
        occurrence_id="occ_01",
        section="DOSAGE AND ADMINISTRATION",
        current_text="The initial dose is 10 mg orally once daily.",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_01",
        decision_id="dec_01",
        section="DOSAGE AND ADMINISTRATION",
        original_text="The initial dose is 10 mg orally once daily.",
        proposed_text="The initial dose is 20 mg orally once daily.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Update per clinical trial findings.",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_01",
        document_id="doc_txt_01",
        author_approver="Dr. Eleanor Vance",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = generator.generate_corrected_document(report=report)

    assert isinstance(result, CorrectedDocumentResult)
    assert result.document_id == "doc_txt_01"
    assert result.input_format == "txt"
    assert result.output_format == "txt"

    corrected_text = result.corrected_bytes.decode("utf-8")
    assert "The initial dose is 20 mg orally once daily." in corrected_text
    assert "The initial dose is 10 mg orally once daily." not in corrected_text
    assert "Indicated for acute migraine attacks in adults." in corrected_text


# ==============================================================================
# TEST 2: TXT excluded occurrence remains unchanged
# ==============================================================================


def test_txt_excluded_occurrence_remains_unchanged():
    """Verify EXCLUDED occurrences are untouched while CONFIRMED occurrences are updated."""
    store = get_candidate_store()
    raw_text = (
        "DOSAGE AND ADMINISTRATION\n"
        "Primary dosage: 10 mg once daily.\n\n"
        "CLINICAL PHARMACOLOGY\n"
        "Baseline dose of 10 mg evaluated in renal study.\n"
    )
    store.store_source_document(
        document_id="doc_txt_02",
        source_bytes=raw_text.encode("utf-8"),
        filename="product_monograph.txt",
        file_format="txt",
    )

    occ_confirmed = RelatedOccurrence(
        occurrence_id="occ_conf",
        section="DOSAGE AND ADMINISTRATION",
        current_text="Primary dosage: 10 mg once daily.",
        status="CONFIRMED",
    )
    occ_excluded = RelatedOccurrence(
        occurrence_id="occ_excl",
        section="CLINICAL PHARMACOLOGY",
        current_text="Baseline dose of 10 mg evaluated in renal study.",
        status="EXCLUDED",
    )

    prop = ProposedChange(
        change_id="chg_02",
        decision_id="dec_02",
        section="DOSAGE AND ADMINISTRATION",
        original_text="Primary dosage: 10 mg once daily.",
        proposed_text="Primary dosage: 25 mg once daily.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Dose adjustment.",
        status="APPROVED",
        related_occurrences=[occ_confirmed, occ_excluded],
    )
    report = ApprovedChangeReport(
        report_id="rep_02",
        document_id="doc_txt_02",
        author_approver="Dr. Eleanor Vance",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = generator.generate_corrected_document(report=report)

    corrected_text = result.corrected_bytes.decode("utf-8")
    # Confirmed occurrence was modified
    assert "Primary dosage: 25 mg once daily." in corrected_text
    assert "Primary dosage: 10 mg once daily." not in corrected_text
    # Excluded occurrence remains strictly unchanged
    assert "Baseline dose of 10 mg evaluated in renal study." in corrected_text


# ==============================================================================
# TEST 3: TXT pending occurrence blocks generation
# ==============================================================================


def test_txt_pending_occurrence_blocks_generation():
    """Verify presence of unresolved PENDING occurrence raises an error and blocks generation."""
    store = get_candidate_store()
    store.store_source_document(
        document_id="doc_txt_03",
        source_bytes=b"Some baseline text.",
        filename="draft.txt",
        file_format="txt",
    )

    occ_pending = RelatedOccurrence(
        occurrence_id="occ_pend_01",
        section="DOSAGE",
        current_text="Some baseline text.",
        status="PENDING",
    )
    prop = ProposedChange(
        change_id="chg_03",
        decision_id="dec_03",
        section="DOSAGE",
        original_text="Some baseline text.",
        proposed_text="Some new text.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
        related_occurrences=[occ_pending],
    )
    report = ApprovedChangeReport(
        report_id="rep_03",
        document_id="doc_txt_03",
        author_approver="Dr. Authorizer",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    with pytest.raises(UnresolvedOccurrencesError, match="PENDING occurrence"):
        generator.generate_corrected_document(report=report)


# ==============================================================================
# TEST 4: Unapproved change/report blocks generation
# ==============================================================================


def test_unapproved_change_or_report_blocks_generation():
    """Verify reports lacking approval_confirmation=True strictly block document generation."""
    store = get_candidate_store()
    store.store_source_document(
        document_id="doc_txt_04",
        source_bytes=b"Safety text.",
        filename="label.txt",
        file_format="txt",
    )

    prop = ProposedChange(
        change_id="chg_04",
        decision_id="dec_04",
        section="SAFETY",
        original_text="Safety text.",
        proposed_text="Updated safety text.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="PROPOSED",
    )
    # approval_confirmation is False
    report = ApprovedChangeReport(
        report_id="rep_04",
        document_id="doc_txt_04",
        author_approver="Dr. Reviewer",
        approval_confirmation=False,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    with pytest.raises(UnapprovedReportError, match="explicit human approval confirmation"):
        generator.generate_corrected_document(report=report)


# ==============================================================================
# TEST 5: DOCX confirmed occurrence is corrected
# ==============================================================================


def test_docx_confirmed_occurrence_is_corrected():
    """Verify DOCX confirmed occurrence is cleanly corrected while preserving Word structure."""
    store = get_candidate_store()
    docx_bytes = make_sample_docx(
        paragraphs=[
            ("INDICATIONS AND USAGE", 1),
            "Indicated for hypertension.",
            ("DOSAGE AND ADMINISTRATION", 1),
            "Initial starting dose is 50 mg orally once daily.",
        ]
    )
    store.store_source_document(
        document_id="doc_docx_05",
        source_bytes=docx_bytes,
        filename="cardiology_label.docx",
        file_format="docx",
    )

    occ = RelatedOccurrence(
        occurrence_id="occ_docx_01",
        section="DOSAGE AND ADMINISTRATION",
        current_text="Initial starting dose is 50 mg orally once daily.",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_05",
        decision_id="dec_05",
        section="DOSAGE AND ADMINISTRATION",
        original_text="Initial starting dose is 50 mg orally once daily.",
        proposed_text="Initial starting dose is 75 mg orally once daily with food.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Updated clinical study.",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_05",
        document_id="doc_docx_05",
        author_approver="Dr. Eleanor Vance",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = generator.generate_corrected_document(report=report)

    assert result.input_format == "docx"
    assert result.output_format == "docx"
    assert result.output_filename == "Corrected_cardiology_label.docx"

    # Inspect generated DOCX in memory
    res_doc = docx.Document(io.BytesIO(result.corrected_bytes))
    all_text = " ".join(p.text for p in res_doc.paragraphs)
    assert "Initial starting dose is 75 mg orally once daily with food." in all_text
    assert "Initial starting dose is 50 mg orally once daily." not in all_text


# ==============================================================================
# TEST 6: Original TXT bytes remain unchanged
# ==============================================================================


def test_original_txt_bytes_remain_unchanged():
    """Verify original retained TXT bytes in candidate store are byte-for-byte immutable."""
    store = get_candidate_store()
    orig_bytes = b"ORIGINAL SOURCE CONTENT IMMUTABILITY TEST: Dosage is 10 mg."
    store.store_source_document(
        document_id="doc_txt_06",
        source_bytes=orig_bytes,
        filename="immutability_test.txt",
        file_format="txt",
    )

    occ = RelatedOccurrence(
        occurrence_id="occ_06",
        section="DOSAGE",
        current_text="Dosage is 10 mg.",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_06",
        decision_id="dec_06",
        section="DOSAGE",
        original_text="Dosage is 10 mg.",
        proposed_text="Dosage is 20 mg.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_06",
        document_id="doc_txt_06",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = generator.generate_corrected_document(report=report)

    # Output has new bytes
    assert result.corrected_bytes != orig_bytes
    assert b"Dosage is 20 mg." in result.corrected_bytes

    # Original bytes in store are strictly unchanged
    retained = store.get_source_document("doc_txt_06")
    assert retained.source_bytes == orig_bytes
    assert retained.source_bytes != result.corrected_bytes


# ==============================================================================
# TEST 7: Original DOCX bytes remain unchanged
# ==============================================================================


def test_original_docx_bytes_remain_unchanged():
    """Verify original retained DOCX bytes in candidate store are byte-for-byte immutable."""
    store = get_candidate_store()
    docx_bytes = make_sample_docx(paragraphs=["Original DOCX paragraph content."])
    store.store_source_document(
        document_id="doc_docx_07",
        source_bytes=docx_bytes,
        filename="original_draft.docx",
        file_format="docx",
    )

    occ = RelatedOccurrence(
        occurrence_id="occ_07",
        section="GENERAL",
        current_text="Original DOCX paragraph content.",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_07",
        decision_id="dec_07",
        section="GENERAL",
        original_text="Original DOCX paragraph content.",
        proposed_text="Modified DOCX paragraph content.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_07",
        document_id="doc_docx_07",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = generator.generate_corrected_document(report=report)

    retained = store.get_source_document("doc_docx_07")
    assert retained.source_bytes == docx_bytes
    assert retained.source_bytes != result.corrected_bytes


# ==============================================================================
# TEST 8: Zero-match occurrence fails safely
# ==============================================================================


def test_zero_match_occurrence_fails_safely():
    """Verify an occurrence targeting text not found in the source fails without generating output."""
    store = get_candidate_store()
    orig_text = "Actual text in the regulatory document."
    store.store_source_document(
        document_id="doc_txt_08",
        source_bytes=orig_text.encode("utf-8"),
        filename="zero_match.txt",
        file_format="txt",
    )

    occ = RelatedOccurrence(
        occurrence_id="occ_08",
        section="DOSAGE",
        current_text="Phantom text that never existed in the source document.",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_08",
        decision_id="dec_08",
        section="DOSAGE",
        original_text="Phantom text that never existed in the source document.",
        proposed_text="Replacement text.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_08",
        document_id="doc_txt_08",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    with pytest.raises(TargetResolutionError, match="Zero matches found"):
        generator.generate_corrected_document(report=report)

    # Retained bytes unaffected
    retained = store.get_source_document("doc_txt_08")
    assert retained.source_bytes == orig_text.encode("utf-8")


# ==============================================================================
# TEST 9: Multiple ambiguous matches fail safely
# ==============================================================================


def test_multiple_ambiguous_matches_fail_safely():
    """Verify occurrence with multiple ambiguous identical matches fails without generating output."""
    store = get_candidate_store()
    ambiguous_text = (
        "Take 10 mg orally once daily.\n"
        "Take 10 mg orally once daily.\n"
        "Take 10 mg orally once daily.\n"
    )
    store.store_source_document(
        document_id="doc_txt_09",
        source_bytes=ambiguous_text.encode("utf-8"),
        filename="ambiguous.txt",
        file_format="txt",
    )

    occ = RelatedOccurrence(
        occurrence_id="occ_09",
        section="UNSPECIFIED",
        current_text="Take 10 mg orally once daily.",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_09",
        decision_id="dec_09",
        section="UNSPECIFIED",
        original_text="Take 10 mg orally once daily.",
        proposed_text="Take 20 mg orally once daily.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_09",
        document_id="doc_txt_09",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    with pytest.raises(TargetResolutionError, match="Multiple ambiguous matches"):
        generator.generate_corrected_document(report=report)


# ==============================================================================
# TEST 10: Multiple confirmed occurrences all applied correctly
# ==============================================================================


def test_multiple_confirmed_occurrences_all_applied_correctly():
    """Verify multiple confirmed occurrences across different sections are all applied."""
    store = get_candidate_store()
    raw_text = (
        "INDICATIONS AND USAGE\n"
        "Approved for symptomatic therapy.\n\n"
        "DOSAGE AND ADMINISTRATION\n"
        "Initial dose: 10 mg once daily.\n\n"
        "WARNINGS AND PRECAUTIONS\n"
        "Monitoring required when dose exceeds 10 mg.\n"
    )
    store.store_source_document(
        document_id="doc_txt_10",
        source_bytes=raw_text.encode("utf-8"),
        filename="multi_target.txt",
        file_format="txt",
    )

    occ1 = RelatedOccurrence(
        occurrence_id="occ_10_a",
        section="DOSAGE AND ADMINISTRATION",
        current_text="Initial dose: 10 mg once daily.",
        status="CONFIRMED",
    )
    occ2 = RelatedOccurrence(
        occurrence_id="occ_10_b",
        section="WARNINGS AND PRECAUTIONS",
        current_text="Monitoring required when dose exceeds 10 mg.",
        status="CONFIRMED",
    )

    prop1 = ProposedChange(
        change_id="chg_10_a",
        decision_id="dec_10_a",
        section="DOSAGE AND ADMINISTRATION",
        original_text="Initial dose: 10 mg once daily.",
        proposed_text="Initial dose: 25 mg once daily.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale A",
        status="APPROVED",
        related_occurrences=[occ1],
    )
    prop2 = ProposedChange(
        change_id="chg_10_b",
        decision_id="dec_10_b",
        section="WARNINGS AND PRECAUTIONS",
        original_text="Monitoring required when dose exceeds 10 mg.",
        proposed_text="Monitoring required when dose exceeds 25 mg.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale B",
        status="APPROVED",
        related_occurrences=[occ2],
    )

    report = ApprovedChangeReport(
        report_id="rep_10",
        document_id="doc_txt_10",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop1, prop2],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = generator.generate_corrected_document(report=report)

    corrected = result.corrected_bytes.decode("utf-8")
    assert "Initial dose: 25 mg once daily." in corrected
    assert "Monitoring required when dose exceeds 25 mg." in corrected
    assert "Initial dose: 10 mg once daily." not in corrected
    assert "Monitoring required when dose exceeds 10 mg." not in corrected


# ==============================================================================
# TEST 11: Output artifact has deterministic SHA-256 hash
# ==============================================================================


def test_output_artifact_has_deterministic_sha256():
    """Verify output artifact contains accurate and deterministic SHA-256 hash."""
    store = get_candidate_store()
    raw_text = "Stable content line for hashing test: Value 10."
    store.store_source_document(
        document_id="doc_txt_11",
        source_bytes=raw_text.encode("utf-8"),
        filename="hash_test.txt",
        file_format="txt",
    )

    occ = RelatedOccurrence(
        occurrence_id="occ_11",
        section="GENERAL",
        current_text="Value 10.",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_11",
        decision_id="dec_11",
        section="GENERAL",
        original_text="Value 10.",
        proposed_text="Value 20.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_11",
        document_id="doc_txt_11",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result1 = generator.generate_corrected_document(report=report)
    result2 = generator.generate_corrected_document(report=report)

    # SHA-256 matches actual byte digest
    expected_hash = hashlib.sha256(result1.corrected_bytes).hexdigest()
    assert result1.sha256_hash == expected_hash
    assert result1.size_bytes == len(result1.corrected_bytes)
    assert result1.size == len(result1.corrected_bytes)

    # Determinism across runs
    assert result1.sha256_hash == result2.sha256_hash
    assert result1.corrected_bytes == result2.corrected_bytes


# ==============================================================================
# TEST 12: PDF corrected document generation succeeds and unsupported format rejected
# ==============================================================================


def test_pdf_corrected_document_generation_and_unsupported_format_guard():
    """Verify PDF corrected document generation succeeds and unsupported formats are cleanly rejected."""
    import pypdf
    from reportlab.pdfgen import canvas

    # 1. Valid PDF generation
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    c.drawString(72, 700, "Dosage: 10 mg once daily.")
    c.save()
    pdf_bytes = buf.getvalue()

    store = get_candidate_store()
    store.store_source_document(
        document_id="doc_pdf_12",
        source_bytes=pdf_bytes,
        filename="label.pdf",
        file_format="pdf",
    )

    prop = ProposedChange(
        change_id="chg_12",
        decision_id="dec_12",
        section="DOSAGE",
        original_text="Dosage: 10 mg once daily.",
        proposed_text="Dosage: 20 mg once daily.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
    )
    report = ApprovedChangeReport(
        report_id="rep_12",
        document_id="doc_pdf_12",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = generator.generate_corrected_document(report=report)
    assert result.corrected_bytes.startswith(b"%PDF-")
    assert result.output_filename == "Corrected_label.pdf"

    reader = pypdf.PdfReader(io.BytesIO(result.corrected_bytes))
    assert "20 mg" in reader.pages[0].extract_text()

    # 2. Unsupported legacy format (doc) is cleanly rejected
    store.store_source_document(
        document_id="doc_bin_12",
        source_bytes=b"\xd0\xcf\x11\xe0 legacy content",
        filename="legacy.doc",
        file_format="doc",
    )
    report_doc = ApprovedChangeReport(
        report_id="rep_doc_12",
        document_id="doc_bin_12",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )
    with pytest.raises(UnsupportedFormatError, match="not supported"):
        generator.generate_corrected_document(report=report_doc)


# ==============================================================================
# TEST 13: No corrected artifact is returned after a failed generation
# ==============================================================================


def test_no_corrected_artifact_returned_after_failed_generation():
    """Verify generation failure raises an exception and yields no partial artifact."""
    store = get_candidate_store()
    store.store_source_document(
        document_id="doc_txt_13",
        source_bytes=b"Some content.",
        filename="doc.txt",
        file_format="txt",
    )

    # Mismatched target that fails
    occ = RelatedOccurrence(
        occurrence_id="occ_13",
        section="DOSAGE",
        current_text="Nonexistent target string",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_13",
        decision_id="dec_13",
        section="DOSAGE",
        original_text="Nonexistent target string",
        proposed_text="New string",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_13",
        document_id="doc_txt_13",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = None
    try:
        result = generator.generate_corrected_document(report=report)
    except TargetResolutionError:
        pass

    assert result is None


# ==============================================================================
# TEST 14: Two documents remain isolated and cannot modify wrong source
# ==============================================================================


def test_two_documents_isolation_cannot_modify_wrong_source():
    """Verify documents remain isolated: correcting Doc A leaves Doc B untouched."""
    store = get_candidate_store()
    bytes_a = b"DOCUMENT A: Pediatric dosage 10 mg."
    bytes_b = b"DOCUMENT B: Oncology dosage 50 mg."

    store.store_source_document(
        document_id="doc_iso_a",
        source_bytes=bytes_a,
        filename="pediatric.txt",
        file_format="txt",
    )
    store.store_source_document(
        document_id="doc_iso_b",
        source_bytes=bytes_b,
        filename="oncology.txt",
        file_format="txt",
    )

    occ_a = RelatedOccurrence(
        occurrence_id="occ_a",
        section="DOSAGE",
        current_text="Pediatric dosage 10 mg.",
        status="CONFIRMED",
    )
    prop_a = ProposedChange(
        change_id="chg_a",
        decision_id="dec_a",
        section="DOSAGE",
        original_text="Pediatric dosage 10 mg.",
        proposed_text="Pediatric dosage 20 mg.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
        related_occurrences=[occ_a],
    )
    report_a = ApprovedChangeReport(
        report_id="rep_a",
        document_id="doc_iso_a",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop_a],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result_a = generator.generate_corrected_document(report=report_a)

    # Doc A corrected
    assert b"Pediatric dosage 20 mg." in result_a.corrected_bytes

    # Doc B in candidate store was NOT modified or touched
    retained_b = store.get_source_document("doc_iso_b")
    assert retained_b.source_bytes == bytes_b
    assert b"Oncology dosage 50 mg." in retained_b.source_bytes


# ==============================================================================
# TEST 15: DOCX table cell occurrences are resolved and corrected
# ==============================================================================


def test_docx_table_cell_occurrence_is_corrected():
    """Verify occurrences inside DOCX tables are resolved and corrected."""
    store = get_candidate_store()
    table_content = [
        ["Patient Group", "Recommended Dose"],
        ["Adults", "100 mg daily"],
        ["Pediatrics", "15 mg/m2 daily"],
    ]
    docx_bytes = make_sample_docx(
        paragraphs=[("DOSAGE TABLE SECTION", 1)],
        table_data=table_content,
    )
    store.store_source_document(
        document_id="doc_docx_tbl",
        source_bytes=docx_bytes,
        filename="table_label.docx",
        file_format="docx",
    )

    occ = RelatedOccurrence(
        occurrence_id="occ_tbl_01",
        section="DOSAGE TABLE SECTION",
        current_text="15 mg/m2 daily",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_tbl",
        decision_id="dec_tbl",
        section="DOSAGE TABLE SECTION",
        original_text="15 mg/m2 daily",
        proposed_text="20 mg/m2 daily",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Pediatric adjustment",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_tbl",
        document_id="doc_docx_tbl",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = generator.generate_corrected_document(report=report)

    res_doc = docx.Document(io.BytesIO(result.corrected_bytes))
    tbl = res_doc.tables[0]
    cell_texts = [cell.text for row in tbl.rows for cell in row.cells]
    assert "20 mg/m2 daily" in cell_texts
    assert "15 mg/m2 daily" not in cell_texts


# ==============================================================================
# TEST 16: DOCX run-level formatting preserved
# ==============================================================================


def test_docx_run_level_formatting_preserved():
    """Verify targeted DOCX replacement preserves existing run-level formatting (e.g. bold)."""
    store = get_candidate_store()
    # Paragraph with mixed bold runs:
    # Run 1: "Standard dose: " (not bold)
    # Run 2: "10 mg" (bold)
    # Run 3: " once daily." (not bold)
    docx_bytes = make_sample_docx(
        paragraphs=[
            [
                ("Standard dose: ", False),
                ("10 mg", True),
                (" once daily.", False),
            ]
        ]
    )
    store.store_source_document(
        document_id="doc_docx_run",
        source_bytes=docx_bytes,
        filename="runs.docx",
        file_format="docx",
    )

    occ = RelatedOccurrence(
        occurrence_id="occ_run",
        section="GENERAL",
        current_text="10 mg",
        status="CONFIRMED",
    )
    prop = ProposedChange(
        change_id="chg_run",
        decision_id="dec_run",
        section="GENERAL",
        original_text="10 mg",
        proposed_text="20 mg",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Rationale",
        status="APPROVED",
        related_occurrences=[occ],
    )
    report = ApprovedChangeReport(
        report_id="rep_run",
        document_id="doc_docx_run",
        author_approver="Approver",
        approval_confirmation=True,
        changes=[prop],
    )

    generator = CorrectedDocumentGenerator(candidate_store=store)
    result = generator.generate_corrected_document(report=report)

    res_doc = docx.Document(io.BytesIO(result.corrected_bytes))
    p = res_doc.paragraphs[0]
    assert p.text == "Standard dose: 20 mg once daily."
    # Run 2 was "10 mg" and bold -> now "20 mg" and still bold
    assert p.runs[1].text == "20 mg"
    assert p.runs[1].bold is True
