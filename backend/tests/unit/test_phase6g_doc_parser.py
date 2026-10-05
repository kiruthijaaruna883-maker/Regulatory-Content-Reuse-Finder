"""Unit tests for Phase 6G.1: Legacy Microsoft Word (.doc) Document Parser & Metadata Auto-Extraction.

Verifies:
1. Parser detection (.doc extension, application/msword MIME type, OLE magic bytes)
2. Rejection of unrelated content
3. Controlled error handling for corrupted / non-Word OLE files
4. Deterministic parsing of valid legacy Word .doc binary streams into RegulatoryDocument
5. Integration with UnifiedIngestionService and RegulatoryChunker
6. API upload via POST /documents/ingest (.doc file)
7. Automatic metadata extraction (product_name, active_ingredient) when omitted
8. Explicit reviewer metadata preservation (never overwritten by auto-extraction)
"""

import io
import struct
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import RegulatoryDocument
from app.services.candidate_store import get_candidate_store, reset_candidate_store
from app.services.ingestion.unified_ingestion import (
    UnifiedIngestionService,
    ingest_and_chunk_document,
)
from app.services.parsers import (
    DocxDocumentParser,
    LegacyDocDocumentParser,
    get_parser,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_candidate_store():
    """Ensure candidate store isolation between all tests."""
    reset_candidate_store()
    yield
    reset_candidate_store()


# ==============================================================================
# IN-MEMORY MINIMAL OLE WORD DOCUMENT FIXTURE BUILDER
# ==============================================================================


def make_test_doc_bytes(text: str, doc_title: str = "") -> bytes:
    """Build a deterministic, minimal valid OLE Compound Document (.doc) in-memory.

    Creates an OLE CFBF container containing a valid WordDocument stream with
    Word 97 FIB header (0xA5EC) and UTF-16LE text stream at offset 512.
    """
    header = bytearray(512)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # OLE magic signature
    header[24:26] = b"\x3e\x00"  # Minor version
    header[26:28] = b"\x03\x00"  # Major version 3 (512-byte sector)
    header[28:30] = b"\xfe\xff"  # Little-endian byte order
    header[30:32] = b"\x09\x00"  # Sector size 2^9 = 512 bytes
    header[32:34] = b"\x06\x00"  # Mini sector size 2^6 = 64 bytes
    struct.pack_into("<I", header, 44, 1)  # Num FAT sectors = 1
    struct.pack_into("<I", header, 48, 0)  # First directory sector = 0
    struct.pack_into("<I", header, 56, 4096)  # Mini stream cutoff
    struct.pack_into("<I", header, 60, 0xFFFFFFFE)  # Mini FAT start (none)
    struct.pack_into("<I", header, 68, 0xFFFFFFFE)  # DIFAT start (none)
    struct.pack_into("<I", header, 76, 1)  # DIFAT[0] points to sector 1 (FAT)
    for i in range(1, 109):
        struct.pack_into("<I", header, 76 + i * 4, 0xFFFFFFFF)

    # Sector 0: Directory sector (128 bytes per entry)
    dir_sector = bytearray(512)

    # Entry 0: Root Entry
    root_name = "Root Entry\0".encode("utf-16le")
    dir_sector[0 : len(root_name)] = root_name
    struct.pack_into("<H", dir_sector, 64, len(root_name))
    dir_sector[66] = 5  # STGTY_ROOT
    dir_sector[67] = 1  # DE_BLACK
    struct.pack_into("<I", dir_sector, 68, 0xFFFFFFFF)  # Left sibling
    struct.pack_into("<I", dir_sector, 72, 0xFFFFFFFF)  # Right sibling
    struct.pack_into("<I", dir_sector, 76, 1)  # Child = Entry 1 (WordDocument)
    struct.pack_into("<I", dir_sector, 116, 0xFFFFFFFE)  # Stream start
    struct.pack_into("<I", dir_sector, 120, 0)  # Stream size

    # Prepare WordDocument stream (4096 bytes = 8 sectors)
    word_stream = bytearray(4096)
    struct.pack_into("<H", word_stream, 0, 0xA5EC)  # wIdent = Word 97
    struct.pack_into("<H", word_stream, 0x0A, 0x0000)  # flags
    fc_min = 512
    struct.pack_into("<I", word_stream, 0x18, fc_min)
    text_bytes = text.encode("utf-16le")
    struct.pack_into("<I", word_stream, 0x4C, len(text))  # ccpText
    word_stream[fc_min : fc_min + len(text_bytes)] = text_bytes

    # Entry 1: WordDocument stream entry (offset 128)
    doc_entry_offset = 128
    doc_name = "WordDocument\0".encode("utf-16le")
    dir_sector[doc_entry_offset : doc_entry_offset + len(doc_name)] = doc_name
    struct.pack_into("<H", dir_sector, doc_entry_offset + 64, len(doc_name))
    dir_sector[doc_entry_offset + 66] = 2  # STGTY_STREAM
    dir_sector[doc_entry_offset + 67] = 1  # DE_BLACK
    struct.pack_into("<I", dir_sector, doc_entry_offset + 68, 0xFFFFFFFF)
    struct.pack_into("<I", dir_sector, doc_entry_offset + 72, 0xFFFFFFFF)
    struct.pack_into("<I", dir_sector, doc_entry_offset + 76, 0xFFFFFFFF)
    struct.pack_into("<I", dir_sector, doc_entry_offset + 116, 2)  # Sector 2
    struct.pack_into("<I", dir_sector, doc_entry_offset + 120, len(word_stream))

    # Sector 1: FAT sector (allocates sectors 0 to 9)
    fat_sector = bytearray(512)
    struct.pack_into("<I", fat_sector, 0 * 4, 0xFFFFFFFE)  # Sector 0: Dir
    struct.pack_into("<I", fat_sector, 1 * 4, 0xFFFFFFFD)  # Sector 1: FAT
    for s in range(2, 9):
        struct.pack_into("<I", fat_sector, s * 4, s + 1)
    struct.pack_into("<I", fat_sector, 9 * 4, 0xFFFFFFFE)  # Sector 9: End
    for s in range(10, 128):
        struct.pack_into("<I", fat_sector, s * 4, 0xFFFFFFFF)

    return bytes(header) + bytes(dir_sector) + bytes(fat_sector) + bytes(word_stream)


def make_non_word_ole_bytes() -> bytes:
    """Build a valid OLE CFBF container that does NOT contain a WordDocument stream."""
    header = bytearray(512)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    header[24:26] = b"\x3e\x00"
    header[26:28] = b"\x03\x00"
    header[28:30] = b"\xfe\xff"
    header[30:32] = b"\x09\x00"
    header[32:34] = b"\x06\x00"
    struct.pack_into("<I", header, 44, 1)
    struct.pack_into("<I", header, 48, 0)
    struct.pack_into("<I", header, 56, 4096)
    struct.pack_into("<I", header, 60, 0xFFFFFFFE)
    struct.pack_into("<I", header, 68, 0xFFFFFFFE)
    struct.pack_into("<I", header, 76, 1)
    for i in range(1, 109):
        struct.pack_into("<I", header, 76 + i * 4, 0xFFFFFFFF)

    dir_sector = bytearray(512)
    root_name = "Root Entry\0".encode("utf-16le")
    dir_sector[0 : len(root_name)] = root_name
    struct.pack_into("<H", dir_sector, 64, len(root_name))
    dir_sector[66] = 5
    dir_sector[67] = 1
    struct.pack_into("<I", dir_sector, 68, 0xFFFFFFFF)
    struct.pack_into("<I", dir_sector, 72, 0xFFFFFFFF)
    struct.pack_into("<I", dir_sector, 76, 0xFFFFFFFF)  # No children
    struct.pack_into("<I", dir_sector, 116, 0xFFFFFFFE)
    struct.pack_into("<I", dir_sector, 120, 0)

    fat_sector = bytearray(512)
    struct.pack_into("<I", fat_sector, 0 * 4, 0xFFFFFFFE)
    struct.pack_into("<I", fat_sector, 1 * 4, 0xFFFFFFFD)
    for s in range(2, 128):
        struct.pack_into("<I", fat_sector, s * 4, 0xFFFFFFFF)

    return bytes(header) + bytes(dir_sector) + bytes(fat_sector)


# ==============================================================================
# 1. PARSER DETECTION TESTS
# ==============================================================================


def test_parser_detection_by_filename():
    """Verify LegacyDocDocumentParser identifies .doc files but not .docx or other extensions."""
    parser = LegacyDocDocumentParser()
    assert parser.can_parse(b"", filename="prescribing_info.doc") is True
    assert parser.can_parse(b"", filename="LABEL.DOC") is True
    assert parser.can_parse(b"", filename="prescribing_info.docx") is False
    assert parser.can_parse(b"", filename="document.txt") is False
    assert parser.can_parse(b"", filename="document.pdf") is False


def test_parser_detection_by_mime_type():
    """Verify LegacyDocDocumentParser identifies legacy Word MIME types."""
    parser = LegacyDocDocumentParser()
    assert parser.can_parse(b"", mime_type="application/msword") is True
    assert parser.can_parse(b"", mime_type="application/vnd.ms-word") is True
    assert parser.can_parse(b"", mime_type="application/x-msword") is True
    assert parser.can_parse(b"", mime_type="application/pdf") is False
    assert parser.can_parse(b"", mime_type="text/plain") is False


def test_parser_detection_by_content_magic():
    """Verify LegacyDocDocumentParser checks OLE magic and WordDocument stream presence."""
    parser = LegacyDocDocumentParser()
    valid_doc = make_test_doc_bytes("Sample test content\r")
    assert parser.can_parse(valid_doc) is True

    # Valid OLE without WordDocument stream should return False
    non_word_ole = make_non_word_ole_bytes()
    assert parser.can_parse(non_word_ole) is False

    # Non-OLE content should return False
    assert parser.can_parse(b"Plain text content") is False


def test_get_parser_registry_resolution():
    """Verify get_parser returns LegacyDocDocumentParser for .doc and Docx for .docx."""
    p_doc = get_parser(filename="monograph.doc")
    assert isinstance(p_doc, LegacyDocDocumentParser)

    p_docx = get_parser(filename="monograph.docx")
    assert isinstance(p_docx, DocxDocumentParser)


# ==============================================================================
# 2. ERROR HANDLING TESTS
# ==============================================================================


def test_parser_empty_content():
    """Empty or whitespace content returns empty RegulatoryDocument without raising error."""
    parser = LegacyDocDocumentParser()
    doc = parser.parse(b"", document_name="Empty Document")
    assert isinstance(doc, RegulatoryDocument)
    assert len(doc.sections) == 0
    assert doc.raw_content == ""
    assert "Paragraphs: 0" in doc.provenance.exact_location


def test_parser_corrupted_file_raises_controlled_value_error():
    """Corrupted binary bytes raise user-friendly ValueError."""
    parser = LegacyDocDocumentParser()
    corrupt_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 200  # Truncated OLE header
    with pytest.raises(ValueError) as exc_info:
        parser.parse(corrupt_bytes)
    assert "The Word document could not be read" in str(exc_info.value)


def test_parser_non_word_ole_raises_controlled_value_error():
    """Valid OLE file without WordDocument stream raises user-friendly ValueError."""
    parser = LegacyDocDocumentParser()
    non_word_bytes = make_non_word_ole_bytes()
    with pytest.raises(ValueError) as exc_info:
        parser.parse(non_word_bytes)
    assert "The Word document could not be read" in str(exc_info.value)


# ==============================================================================
# 3. DETERMINISTIC PARSING & STRUCTURE TESTS
# ==============================================================================


def test_parse_valid_legacy_doc():
    """Verify parsing a valid .doc file recovers sections and hierarchical structure."""
    raw_text = (
        "1. INDICATIONS AND USAGE\r"
        "Drug X is indicated for the treatment of hypertension in adults.\r"
        "2. DOSAGE AND ADMINISTRATION\r"
        "Administer 10 mg orally once daily.\r"
        "2.1 Adult Dosage\r"
        "For adult patients, the recommended initial dosage is 10 mg.\r"
    )
    doc_bytes = make_test_doc_bytes(raw_text)

    parser = LegacyDocDocumentParser()
    doc = parser.parse(doc_bytes, document_name="Drug X Monograph")

    assert isinstance(doc, RegulatoryDocument)
    assert doc.title == "Drug X Monograph"
    assert len(doc.sections) >= 2

    # Check top-level sections
    sec1 = doc.sections[0]
    assert "INDICATIONS" in sec1.heading_raw
    assert "hypertension" in sec1.raw_text

    sec2 = doc.sections[1]
    assert "DOSAGE" in sec2.heading_raw
    assert "10 mg" in sec2.raw_text

    # Check subsection nesting
    assert len(sec2.subsections) >= 1
    assert "Adult Dosage" in sec2.subsections[0].heading_raw


# ==============================================================================
# 4. UNIFIED INGESTION & CHUNKER INTEGRATION
# ==============================================================================


def test_unified_ingestion_legacy_doc():
    """Verify .doc file flows through UnifiedIngestionService and produces RegulatoryChunks."""
    content = (
        "1. INDICATIONS AND USAGE\r"
        "CardioGuard is indicated for adult hypertension.\r"
        "2. CONTRAINDICATIONS\r"
        "Do not administer to patients with cardiogenic shock.\r"
    )
    doc_bytes = make_test_doc_bytes(content)

    service = UnifiedIngestionService()
    doc, chunks = service.ingest_and_chunk_document(
        content=doc_bytes,
        filename="cardioguard.doc",
        document_name="CardioGuard Label",
    )

    assert isinstance(doc, RegulatoryDocument)
    assert len(chunks) > 0
    assert any("CardioGuard is indicated" in c.content for c in chunks)
    assert any("cardiogenic shock" in c.content for c in chunks)


# ==============================================================================
# 5. API UPLOAD TESTS (POST /documents/ingest)
# ==============================================================================


def test_api_upload_legacy_doc():
    """Verify POST /documents/ingest accepts legacy .doc file upload."""
    content = (
        "1. INDICATIONS AND USAGE\r"
        "Drug Z is indicated for acute coronary syndrome.\r"
        "2. DOSAGE AND ADMINISTRATION\r"
        "Initial dose of 50 mg orally.\r"
    )
    doc_bytes = make_test_doc_bytes(content)

    response = client.post(
        "/documents/ingest",
        files={"file": ("label.doc", io.BytesIO(doc_bytes), "application/msword")},
        data={"document_name": "Drug Z PI"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Drug Z PI"
    assert data["chunks_count"] > 0
    assert "Successfully ingested" in data["message"]


def test_api_upload_corrupt_doc_returns_clean_400():
    """Verify uploading a corrupt .doc returns HTTP 400 with user-facing error message."""
    response = client.post(
        "/documents/ingest",
        files={"file": ("corrupt.doc", io.BytesIO(b"Not an OLE file at all"), "application/msword")},
    )
    assert response.status_code == 400
    assert "The Word document could not be read" in response.json()["detail"]


# ==============================================================================
# 6. AUTOMATIC METADATA EXTRACTION TESTS
# ==============================================================================


def test_api_auto_extracts_missing_product_and_active_ingredient():
    """Verify automatic extraction of product_name and active_ingredient when omitted by reviewer."""
    content = (
        "1. INDICATIONS AND USAGE\r"
        "Take 50 mg of Metoprolol orally once daily for the management of hypertension.\r"
        "2. DOSAGE AND ADMINISTRATION\r"
        "Administer Metoprolol tablets with or immediately after meals.\r"
    )
    doc_bytes = make_test_doc_bytes(content)

    response = client.post(
        "/documents/ingest",
        files={"file": ("label.doc", io.BytesIO(doc_bytes), "application/msword")},
        data={},  # Reviewer provides neither product_name nor active_ingredient
    )

    assert response.status_code == 200
    data = response.json()
    doc_id = data["document_id"]

    # Verify registered candidate store document and chunks got populated
    store = get_candidate_store()
    doc = store.get_document(doc_id)
    assert doc is not None
    assert doc.active_ingredient == "Metoprolol"

    chunks = store.list_chunks(doc_id)
    assert len(chunks) > 0
    assert all(c.active_ingredient == "Metoprolol" for c in chunks)


def test_api_preserves_explicit_metadata_never_overwrites():
    """Verify reviewer-supplied metadata is preserved and never overwritten by auto-extraction."""
    content = (
        "1. INDICATIONS AND USAGE\r"
        "Take 20 mg of Lisinopril orally once daily.\r"
    )
    doc_bytes = make_test_doc_bytes(content)

    response = client.post(
        "/documents/ingest",
        files={"file": ("label.doc", io.BytesIO(doc_bytes), "application/msword")},
        data={
            "product_name": "ReviewerBrandName",
            "active_ingredient": "ReviewerActiveSubstance",
        },
    )

    assert response.status_code == 200
    data = response.json()
    doc_id = data["document_id"]

    store = get_candidate_store()
    doc = store.get_document(doc_id)
    assert doc is not None
    # Must preserve explicit values, not Lisinopril
    assert doc.product_name == "ReviewerBrandName"
    assert doc.active_ingredient == "ReviewerActiveSubstance"

    chunks = store.list_chunks(doc_id)
    assert all(c.product == "ReviewerBrandName" for c in chunks)
    assert all(c.active_ingredient == "ReviewerActiveSubstance" for c in chunks)
