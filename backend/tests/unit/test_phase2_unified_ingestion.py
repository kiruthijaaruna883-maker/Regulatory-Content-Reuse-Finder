"""Unit tests for Phase 2 Step 6: Unified Regulatory Document Ingestion.

Validates unified ingestion entry point:
- Format detection by extension (.txt, .md, .markdown, .json, .xml, .html, .htm, .pdf, .docx)
- Format detection by MIME type
- File-like object handling (BytesIO, StringIO)
- Metadata and provenance preservation
- Error handling (unsupported formats, corrupted files)
- RegulatoryChunker integration
"""

import io
import json
import pytest

from app.models.document import RegulatoryDocument, RegulatoryProvenance
from app.services.chunking.regulatory_chunker import RegulatoryChunker
from app.services.ingestion import (
    UnifiedIngestionService,
    ingest_and_chunk_document,
    ingest_document,
)
from tests.unit.test_phase2_pdf_docx import make_test_docx_bytes, make_test_pdf_bytes


# ============================================================================
# 1. EXTENSION-BASED FORMAT DETECTION & NORMALIZED OUTPUT
# ============================================================================

@pytest.mark.parametrize("filename,content,expected_title", [
    (
        "label.txt",
        "1. INDICATIONS AND USAGE\nDrug Alpha is indicated for hypertension.\n",
        "Label",
    ),
    (
        "dossier.md",
        "# 1. INDICATIONS AND USAGE\nDrug Beta is indicated for chronic symptoms.\n",
        "Dossier",
    ),
    (
        "summary.markdown",
        "# 1. INDICATIONS AND USAGE\nDrug Gamma is indicated for acute pain.\n",
        "Summary",
    ),
    (
        "product.json",
        json.dumps({"indications": "Drug Delta is indicated for allergy symptoms."}),
        "Product",
    ),
    (
        "report.xml",
        "<label><indications><paragraph>Drug Epsilon is indicated for relief.</paragraph></indications></label>",
        "Report",
    ),
    (
        "monograph.html",
        "<html><body><h1>1. Indications</h1><p>Drug Zeta is indicated for arthritis.</p></body></html>",
        "Monograph",
    ),
    (
        "notice.htm",
        "<html><body><h1>1. Indications</h1><p>Drug Eta is indicated for headache.</p></body></html>",
        "Notice",
    ),
])
def test_extension_based_ingestion(filename, content, expected_title):
    """Verify that file extension routes correctly to the corresponding parser."""
    doc = ingest_document(
        content=content,
        filename=filename,
        document_id=f"doc_{filename.replace('.', '_')}",
    )

    assert isinstance(doc, RegulatoryDocument)
    assert doc.document_id == f"doc_{filename.replace('.', '_')}"
    assert len(doc.sections) >= 1
    assert doc.sections[0].heading_raw is not None
    assert len(doc.sections[0].raw_text or "") > 0


def test_pdf_extension_ingestion():
    """Verify that .pdf extension ingests PDF files correctly."""
    pdf_bytes = make_test_pdf_bytes([
        ["1. INDICATIONS AND USAGE", "Drug Theta is indicated for pediatric care."]
    ])

    doc = ingest_document(
        content=pdf_bytes,
        filename="dossier.pdf",
        document_id="doc_pdf_unified",
    )

    assert isinstance(doc, RegulatoryDocument)
    assert doc.document_id == "doc_pdf_unified"
    assert len(doc.sections) == 1
    assert "INDICATIONS" in doc.sections[0].heading_raw.upper()


def test_docx_extension_ingestion():
    """Verify that .docx extension ingests DOCX files correctly."""
    docx_bytes = make_test_docx_bytes()

    doc = ingest_document(
        content=docx_bytes,
        filename="submission.docx",
        document_id="doc_docx_unified",
    )

    assert isinstance(doc, RegulatoryDocument)
    assert doc.document_id == "doc_docx_unified"
    assert len(doc.sections) == 2


# ============================================================================
# 2. MIME-TYPE BASED FORMAT DETECTION
# ============================================================================

@pytest.mark.parametrize("mime_type,content", [
    ("text/plain", "1. INDICATIONS\nDrug is indicated for insomnia.\n"),
    ("text/markdown", "# 1. INDICATIONS\nDrug is indicated for insomnia.\n"),
    ("application/json", json.dumps({"indications": "Drug is indicated for insomnia."})),
    ("application/xml", "<label><indications><p>Drug is indicated for insomnia.</p></indications></label>"),
    ("text/xml", "<label><indications><p>Drug is indicated for insomnia.</p></indications></label>"),
    ("text/html", "<html><body><h1>1. Indications</h1><p>Drug is indicated for insomnia.</p></body></html>"),
])
def test_mime_type_based_ingestion(mime_type, content):
    """Verify that explicit MIME types route properly without needing filenames."""
    doc = ingest_document(
        content=content,
        mime_type=mime_type,
        document_id="doc_mime_test",
        document_name="MIME Document",
    )

    assert isinstance(doc, RegulatoryDocument)
    assert doc.title == "MIME Document"
    assert len(doc.sections) >= 1


def test_pdf_mime_ingestion():
    """Verify PDF ingestion via application/pdf MIME type without filename."""
    pdf_bytes = make_test_pdf_bytes([["1. INDICATIONS", "Pediatric formulation."]])
    doc = ingest_document(content=pdf_bytes, mime_type="application/pdf")
    assert isinstance(doc, RegulatoryDocument)
    assert len(doc.sections) == 1


def test_docx_mime_ingestion():
    """Verify DOCX ingestion via standard OpenXML MIME type without filename."""
    docx_bytes = make_test_docx_bytes()
    doc = ingest_document(
        content=docx_bytes,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert isinstance(doc, RegulatoryDocument)
    assert len(doc.sections) == 2


# ============================================================================
# 3. FILE-LIKE OBJECTS SUPPORT
# ============================================================================

def test_file_like_object_support_stringio():
    """Verify ingest_document accepts StringIO file-like objects."""
    buf = io.StringIO("1. INDICATIONS\nDrug Lambda is indicated for pain.\n")
    buf.name = "dossier_lambda.txt"

    doc = ingest_document(content=buf)
    assert isinstance(doc, RegulatoryDocument)
    assert len(doc.sections) == 1
    assert "INDICATIONS" in doc.sections[0].heading_raw.upper()


def test_file_like_object_support_bytesio():
    """Verify ingest_document accepts BytesIO file-like objects for PDF/DOCX."""
    pdf_bytes = make_test_pdf_bytes([["1. DOSAGE", "Administer 10 mg daily."]])
    buf = io.BytesIO(pdf_bytes)
    buf.name = "label_theta.pdf"

    doc = ingest_document(content=buf)
    assert isinstance(doc, RegulatoryDocument)
    assert len(doc.sections) == 1
    assert "DOSAGE" in doc.sections[0].heading_raw.upper()


# ============================================================================
# 4. METADATA & PROVENANCE PRESERVATION
# ============================================================================

def test_provenance_and_metadata_preservation():
    """Verify that caller-supplied provenance and metadata are strictly preserved."""
    custom_prov = RegulatoryProvenance(
        source_repository="DailyMed",
        source_identifier="set-custom-999",
        source_url="https://dailymed.nlm.nih.gov/lookup?setid=set-custom-999",
        version="3.0",
    )

    doc = ingest_document(
        content="1. WARNINGS\nDo not operate heavy machinery.\n",
        filename="label.txt",
        document_id="DOC-CUSTOM-ID",
        document_name="Custom Drug Label",
        provenance=custom_prov,
        metadata={
            "product_name": "MachineryCare",
            "active_ingredient": "Substance X",
            "jurisdiction": "US_FDA",
            "document_type": "CORE_DATA_SHEET",
        },
    )

    assert doc.document_id == "DOC-CUSTOM-ID"
    assert doc.title == "Custom Drug Label"
    assert doc.product_name == "MachineryCare"
    assert doc.active_ingredient == "Substance X"
    assert doc.jurisdiction == "US_FDA"
    assert doc.document_type == "CORE_DATA_SHEET"
    assert doc.provenance.source_repository == "DailyMed"
    assert doc.provenance.source_identifier == "set-custom-999"
    assert doc.provenance.source_url == "https://dailymed.nlm.nih.gov/lookup?setid=set-custom-999"


# ============================================================================
# 5. ERROR HANDLING & UNSUPPORTED FORMATS
# ============================================================================

def test_unsupported_file_extension_error():
    """Verify unsupported extensions raise a descriptive ValueError."""
    with pytest.raises(ValueError, match="Unsupported document format"):
        ingest_document(
            content="Some random content",
            filename="unsupported.xyz",
        )


def test_unsupported_mime_type_error():
    """Verify unsupported MIME types raise a descriptive ValueError."""
    with pytest.raises(ValueError, match="Unsupported document format"):
        ingest_document(
            content="Some random content",
            mime_type="application/x-proprietary-archive",
        )


def test_unparseable_binary_content_error():
    """Verify unrecognized binary content without extension or MIME raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported document format"):
        ingest_document(
            content=b"\x00\x01\x02\x03\x04\xff\xfe\xfd",
        )


def test_corrupted_parser_error_propagation():
    """Verify format-specific parser errors are propagated cleanly without being swallowed."""
    with pytest.raises(ValueError, match="Invalid PDF content"):
        ingest_document(
            content=b"%PDF-1.4 CORRUPTED JUNK",
            filename="corrupt.pdf",
        )

    with pytest.raises(ValueError, match="Invalid JSON content"):
        ingest_document(
            content="{ unclosed_json: true, ",
            filename="corrupt.json",
        )


def test_empty_input_handling():
    """Verify empty input returns a clean RegulatoryDocument with empty sections."""
    empty_doc = ingest_document(content="", filename="empty.txt")
    assert isinstance(empty_doc, RegulatoryDocument)
    assert len(empty_doc.sections) == 0


# ============================================================================
# 6. CHUNKER INTEGRATION
# ============================================================================

def test_unified_ingest_and_chunk_pipeline():
    """Verify end-to-end ingestion and chunking via ingest_and_chunk_document."""
    content = (
        "1. INDICATIONS AND USAGE\n"
        "Drug Omega is indicated for cardiovascular stability.\n\n"
        "2. DOSAGE AND ADMINISTRATION\n"
        "The standard dose is 25 mg once daily.\n"
    )

    doc, chunks = ingest_and_chunk_document(
        content=content,
        filename="omega_label.txt",
        document_id="doc_omega_001",
        document_name="Omega Product Label",
    )

    assert isinstance(doc, RegulatoryDocument)
    assert len(doc.sections) == 2
    assert len(chunks) >= 2

    for chk in chunks:
        assert chk.document_id == "doc_omega_001"
        assert chk.chunk_id.startswith("chk_")
        assert len(chk.content.strip()) > 0
        item = chk.to_content_item()
        assert item.document_id == "doc_omega_001"
