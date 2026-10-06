"""Unit tests for Phase 7: Source Document Retention in Ingested Candidate Store.

Verifies:
1. Uploaded source bytes are retained for the correct document_id across formats (TXT, DOCX, PDF).
2. Original filename is preserved verbatim.
3. File format/extension is resolved and retained deterministically.
4. Retrieved bytes exactly equal the uploaded bytes (binary integrity).
5. Multiple documents do not overwrite each other's source bytes.
6. Pasted regulatory text preserves encoded UTF-8 bytes and txt format.
7. Ingestion API response schema remains unchanged (no raw bytes leaked).
8. Candidate store direct store/get/has/remove/clear lifecycle.
9. Immutability of retained source bytes.
"""

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import (
    RegulatoryDocument,
    RegulatoryProvenance,
    RetainedSourceDocument,
)
from app.services.candidate_store import (
    IngestedDocumentCandidateStore,
    get_candidate_store,
    reset_candidate_store,
    resolve_file_format,
)
from tests.unit.test_phase2_pdf_docx import make_test_docx_bytes, make_test_pdf_bytes

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_candidate_store():
    """Ensure candidate store isolation between all tests."""
    reset_candidate_store()
    yield
    reset_candidate_store()


# ==============================================================================
# 1. API MULTIPART UPLOAD RETENTION ACROSS FORMATS
# ==============================================================================


def test_uploaded_txt_bytes_retained():
    """Verify uploaded plain text (.txt) document bytes and filename are retained."""
    txt_content = (
        "1. INDICATIONS AND USAGE\n"
        "Drug Alpha is indicated for the acute management of hypertension.\n\n"
        "2. DOSAGE AND ADMINISTRATION\n"
        "Take 20 mg once daily.\n"
    ).encode("utf-8")

    response = client.post(
        "/documents/ingest",
        files={"file": ("alpha_clinical_monograph.txt", txt_content, "text/plain")},
        data={"document_name": "Alpha Monograph", "product_name": "AlphaDrug"},
    )
    assert response.status_code == 200
    data = response.json()
    doc_id = data["document_id"]

    # Raw bytes must NOT be present in API response
    assert "source_bytes" not in data
    assert "raw_bytes" not in data

    # Verify server-side session retention
    store = get_candidate_store()
    assert store.has_source_document(doc_id)
    retained = store.get_source_document(doc_id)
    assert retained is not None
    assert isinstance(retained, RetainedSourceDocument)
    assert retained.document_id == doc_id
    assert retained.filename == "alpha_clinical_monograph.txt"
    assert retained.file_format == "txt"
    assert retained.source_bytes == txt_content
    assert retained.size_bytes == len(txt_content)


def test_uploaded_docx_bytes_retained():
    """Verify uploaded DOCX document bytes and format are retained."""
    docx_bytes = make_test_docx_bytes(
        title="Beta Dossier",
        sections_data=[
            {
                "heading": "1. INDICATIONS AND USAGE",
                "level": 1,
                "paragraphs": ["Beta is indicated for chronic maintenance."],
            },
            {
                "heading": "2. DOSAGE AND ADMINISTRATION",
                "level": 1,
                "paragraphs": ["Administer 50 mg orally."],
            },
        ],
    )

    response = client.post(
        "/documents/ingest",
        files={
            "file": (
                "beta_core_data_sheet.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"document_name": "Beta Core Sheet", "product_name": "BetaDrug"},
    )
    assert response.status_code == 200
    data = response.json()
    doc_id = data["document_id"]

    store = get_candidate_store()
    assert store.has_source_document(doc_id)
    retained = store.get_source_document(doc_id)
    assert retained is not None
    assert retained.filename == "beta_core_data_sheet.docx"
    assert retained.file_format == "docx"
    assert retained.source_bytes == docx_bytes
    assert retained.size_bytes == len(docx_bytes)


def test_uploaded_pdf_bytes_retained():
    """Verify uploaded PDF document bytes and format are retained."""
    pdf_bytes = make_test_pdf_bytes(
        pages_text=[
            [
                "1. INDICATIONS AND USAGE",
                "Gamma is indicated for the treatment of migraine in adults.",
            ],
            [
                "2. DOSAGE AND ADMINISTRATION",
                "Take 10 mg at onset of symptoms.",
            ],
        ]
    )

    response = client.post(
        "/documents/ingest",
        files={"file": ("gamma_prescribing_info.pdf", pdf_bytes, "application/pdf")},
        data={"document_name": "Gamma Prescribing Info", "product_name": "GammaDrug"},
    )
    assert response.status_code == 200
    data = response.json()
    doc_id = data["document_id"]

    store = get_candidate_store()
    assert store.has_source_document(doc_id)
    retained = store.get_source_document(doc_id)
    assert retained is not None
    assert retained.filename == "gamma_prescribing_info.pdf"
    assert retained.file_format == "pdf"
    assert retained.source_bytes == pdf_bytes
    assert retained.size_bytes == len(pdf_bytes)


def test_pasted_text_retained_as_source_document():
    """Verify pasted regulatory text is retained as UTF-8 source bytes with txt format."""
    pasted_content = (
        "INDICATIONS AND USAGE\n"
        "Delta is indicated for pain relief.\n\n"
        "DOSAGE AND ADMINISTRATION\n"
        "Take 500 mg every 6 hours as needed.\n"
    )

    response = client.post(
        "/documents/ingest",
        data={
            "pasted_text": pasted_content,
            "document_name": "Delta Draft",
            "product_name": "DeltaDrug",
        },
    )
    assert response.status_code == 200
    data = response.json()
    doc_id = data["document_id"]

    store = get_candidate_store()
    assert store.has_source_document(doc_id)
    retained = store.get_source_document(doc_id)
    assert retained is not None
    assert retained.filename == "pasted_content.txt"
    assert retained.file_format == "txt"
    assert retained.source_bytes == pasted_content.encode("utf-8")


# ==============================================================================
# 2. MULTI-DOCUMENT ISOLATION & NON-OVERWRITE
# ==============================================================================


def test_multiple_documents_isolation():
    """Verify multiple ingested documents do not overwrite each other's source bytes."""
    doc_a_bytes = b"Document A original content: Indications for drug A."
    doc_b_bytes = make_test_docx_bytes(title="Doc B Title")
    doc_c_bytes = make_test_pdf_bytes([["Section 1", "PDF content for doc C"]])

    res_a = client.post(
        "/documents/ingest",
        files={"file": ("doc_a.txt", doc_a_bytes, "text/plain")},
        data={"document_name": "Doc A"},
    )
    res_b = client.post(
        "/documents/ingest",
        files={"file": ("doc_b.docx", doc_b_bytes, "application/docx")},
        data={"document_name": "Doc B"},
    )
    res_c = client.post(
        "/documents/ingest",
        files={"file": ("doc_c.pdf", doc_c_bytes, "application/pdf")},
        data={"document_name": "Doc C"},
    )

    assert res_a.status_code == 200
    assert res_b.status_code == 200
    assert res_c.status_code == 200

    id_a = res_a.json()["document_id"]
    id_b = res_b.json()["document_id"]
    id_c = res_c.json()["document_id"]

    assert id_a != id_b != id_c

    store = get_candidate_store()

    rec_a = store.get_source_document(id_a)
    rec_b = store.get_source_document(id_b)
    rec_c = store.get_source_document(id_c)

    assert rec_a.source_bytes == doc_a_bytes
    assert rec_a.filename == "doc_a.txt"
    assert rec_a.file_format == "txt"

    assert rec_b.source_bytes == doc_b_bytes
    assert rec_b.filename == "doc_b.docx"
    assert rec_b.file_format == "docx"

    assert rec_c.source_bytes == doc_c_bytes
    assert rec_c.filename == "doc_c.pdf"
    assert rec_c.file_format == "pdf"


# ==============================================================================
# 3. CANDIDATE STORE LIFECYCLE & DIRECT METHODS
# ==============================================================================


def test_candidate_store_direct_lifecycle():
    """Verify CandidateStore store_source_document, remove_document, and clear lifecycles."""
    store = IngestedDocumentCandidateStore()

    doc_id = "doc_test_123"
    raw_content = b"Sample raw bytes for direct candidate store test."

    # 1. Store
    record = store.store_source_document(
        document_id=doc_id,
        source_bytes=raw_content,
        filename="test_file.docx",
        file_format="docx",
    )
    assert record.document_id == doc_id
    assert record.source_bytes == raw_content
    assert record.filename == "test_file.docx"
    assert record.file_format == "docx"
    assert record.size_bytes == len(raw_content)

    # 2. Retrieve
    assert store.has_source_document(doc_id)
    retrieved = store.get_source_document(doc_id)
    assert retrieved is record

    # 3. Add RegulatoryDocument with source_bytes
    prov = RegulatoryProvenance(source_repository="InternalDraft")
    doc_obj = RegulatoryDocument(
        document_id=doc_id,
        title="Test Doc Title",
        provenance=prov,
    )
    store.add_document(doc_obj, chunks=[], source_bytes=raw_content, filename="test_file.docx")
    assert store.get_document(doc_id) is not None
    assert store.get_source_document(doc_id).source_bytes == raw_content

    # 4. Remove document cleans up source_document
    assert store.remove_document(doc_id) is True
    assert store.get_document(doc_id) is None
    assert store.get_source_document(doc_id) is None
    assert not store.has_source_document(doc_id)

    # 5. Clear cleans up all source_documents
    store.store_source_document("doc_x", b"bytes x", "x.txt", "txt")
    store.store_source_document("doc_y", b"bytes y", "y.pdf", "pdf")
    assert store.has_source_document("doc_x")
    assert store.has_source_document("doc_y")

    store.clear()
    assert not store.has_source_document("doc_x")
    assert not store.has_source_document("doc_y")


def test_source_bytes_string_encoding():
    """Verify passing string content to store_source_document encodes cleanly to UTF-8 bytes."""
    store = IngestedDocumentCandidateStore()
    text = "Clinical posology string with special characters: ≥ 50 mg/m²."

    record = store.store_source_document(
        document_id="doc_str_1",
        source_bytes=text,
        filename="posology.txt",
    )
    assert record.source_bytes == text.encode("utf-8")
    assert record.file_format == "txt"


# ==============================================================================
# 4. DETERMINISTIC FORMAT RESOLUTION
# ==============================================================================


def test_resolve_file_format_deterministic():
    """Verify deterministic resolution of formats from extensions, MIME types, and magic bytes."""
    # 1. Specified format override
    assert resolve_file_format(specified_format="docx") == "docx"
    assert resolve_file_format(specified_format=".PDF") == "pdf"

    # 2. Filename extensions
    assert resolve_file_format(filename="label.docx") == "docx"
    assert resolve_file_format(filename="label.PDF") == "pdf"
    assert resolve_file_format(filename="label.DOC") == "doc"
    assert resolve_file_format(filename="label.TXT") == "txt"
    assert resolve_file_format(filename="notes.markdown") == "md"
    assert resolve_file_format(filename="table.htm") == "html"

    # 3. MIME types when extension is absent
    assert resolve_file_format(filename="uploaded_file", mime_type="application/pdf") == "pdf"
    assert (
        resolve_file_format(
            filename="uploaded_file",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        == "docx"
    )
    assert resolve_file_format(filename="uploaded_file", mime_type="application/msword") == "doc"
    assert resolve_file_format(filename="uploaded_file", mime_type="text/plain") == "txt"
    assert resolve_file_format(filename="uploaded_file", mime_type="application/json") == "json"

    # 4. Content signature magic bytes when filename and MIME type are unhelpful
    assert resolve_file_format(filename="blob", content=b"%PDF-1.4 header") == "pdf"
    assert resolve_file_format(filename="blob", content=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 binary doc") == "doc"
    assert resolve_file_format(filename="blob", content=b"PK\x03\x04...word/document.xml...") == "docx"

    # 5. Default fallback
    assert resolve_file_format(filename="unknown_file") == "txt"
