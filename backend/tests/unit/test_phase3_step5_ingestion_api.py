"""Unit and API integration tests for Phase 3 Step 5: Multipart Ingestion + Candidate Discovery API.

Verifies:
1. Multipart document ingestion across all 7 supported formats (TXT, MD, JSON, XML, HTML, PDF, DOCX)
2. Pasted regulatory text ingestion
3. Input validation: neither file nor text, empty file, empty pasted text, unsupported format, corrupted file
4. Zero usable chunks handling without candidate fabrication
5. Candidate discovery endpoint POST /candidates/search
6. Source filters: ingested, internal, dailymed, openfda, all
7. Error handling and validation on search (empty query, invalid source filter, top_k range)
8. Traceability: document_id, content_id, section, location, page, source_url, source_identifier, cross_sources
9. Backward compatibility: /documents/upload, /regulatory/search, /content/analyze
10. Store isolation between tests
"""

import json
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.content import KeyInformation, RegulatoryContentItem, RegulatorySearchResult
from app.services.candidate_store import get_candidate_store, reset_candidate_store
from tests.unit.test_phase2_pdf_docx import make_test_docx_bytes, make_test_pdf_bytes

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_candidate_store():
    """Ensure candidate store isolation between all tests."""
    reset_candidate_store()
    yield
    reset_candidate_store()


# ==============================================================================
# 1. MULTIPART INGESTION ACROSS ALL SUPPORTED FORMATS
# ==============================================================================


def test_multipart_ingest_txt():
    """Verify multipart upload of plain text (.txt) document."""
    txt_content = (
        "1. INDICATIONS AND USAGE\n"
        "Drug Alpha is indicated for the treatment of hypertension in adults.\n\n"
        "2. DOSAGE AND ADMINISTRATION\n"
        "Initial dose is 10 mg orally once daily. Maximum recommended dose is 40 mg daily.\n"
    ).encode("utf-8")

    response = client.post(
        "/documents/ingest",
        files={"file": ("alpha_label.txt", txt_content, "text/plain")},
        data={"document_name": "Alpha Label TXT", "product_name": "AlphaDrug"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Alpha Label TXT"
    assert data["sections_count"] >= 2
    assert data["chunks_count"] >= 2
    assert data["source_repository"] == "InternalDraft"
    assert "Successfully ingested" in data["message"]


def test_multipart_ingest_markdown():
    """Verify multipart upload of Markdown (.md) document."""
    md_content = (
        "# 1. INDICATIONS AND USAGE\n"
        "Drug Beta is indicated for acute pain management in adults.\n\n"
        "# 2. DOSAGE AND ADMINISTRATION\n"
        "Take 50 mg every 4 to 6 hours as needed for pain.\n"
    ).encode("utf-8")

    response = client.post(
        "/documents/ingest",
        files={"file": ("beta_label.md", md_content, "text/markdown")},
        data={"document_name": "Beta Label Markdown"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Beta Label Markdown"
    assert data["sections_count"] >= 2
    assert data["chunks_count"] >= 2


def test_multipart_ingest_json():
    """Verify multipart upload of JSON (.json) regulatory document."""
    json_data = {
        "indications": "Drug Gamma is indicated for the relief of allergic rhinitis.",
        "dosage": "Adults and children 12 years and older: 1 tablet daily.",
    }
    json_bytes = json.dumps(json_data).encode("utf-8")

    response = client.post(
        "/documents/ingest",
        files={"file": ("gamma_label.json", json_bytes, "application/json")},
        data={"document_name": "Gamma Label JSON"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Gamma Label JSON"
    assert data["chunks_count"] >= 1


def test_multipart_ingest_xml():
    """Verify multipart upload of XML (.xml) SPL label."""
    xml_content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<document>"
        "<section>"
        "<caption>1. INDICATIONS AND USAGE</caption>"
        "<text><paragraph>Drug Delta is indicated for migraine headache prophylaxis.</paragraph></text>"
        "</section>"
        "<section>"
        "<caption>2. DOSAGE AND ADMINISTRATION</caption>"
        "<text><paragraph>Administer 100 mg subcutaneously once monthly.</paragraph></text>"
        "</section>"
        "</document>"
    ).encode("utf-8")

    response = client.post(
        "/documents/ingest",
        files={"file": ("delta_label.xml", xml_content, "application/xml")},
        data={"document_name": "Delta Label XML"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Delta Label XML"
    assert data["chunks_count"] >= 2


def test_multipart_ingest_html():
    """Verify multipart upload of HTML (.html) product monograph."""
    html_content = (
        "<!DOCTYPE html>"
        "<html><body>"
        "<h1>1. INDICATIONS AND USAGE</h1>"
        "<p>Drug Epsilon is indicated for glycemic control in type 2 diabetes mellitus.</p>"
        "<h1>2. DOSAGE AND ADMINISTRATION</h1>"
        "<p>Starting dose is 5 mg orally once daily with morning meal.</p>"
        "</body></html>"
    ).encode("utf-8")

    response = client.post(
        "/documents/ingest",
        files={"file": ("epsilon_label.html", html_content, "text/html")},
        data={"document_name": "Epsilon Label HTML"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Epsilon Label HTML"
    assert data["chunks_count"] >= 2


def test_multipart_ingest_pdf():
    """Verify multipart upload of PDF (.pdf) multi-page document."""
    pdf_bytes = make_test_pdf_bytes([
        ["1. INDICATIONS AND USAGE", "Drug Zeta is indicated for severe rheumatoid arthritis."],
        ["2. DOSAGE AND ADMINISTRATION", "Administer 40 mg by subcutaneous injection every other week."],
    ])

    response = client.post(
        "/documents/ingest",
        files={"file": ("zeta_label.pdf", pdf_bytes, "application/pdf")},
        data={"document_name": "Zeta Label PDF"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Zeta Label PDF"
    assert data["chunks_count"] >= 2


def test_multipart_ingest_docx():
    """Verify multipart upload of DOCX (.docx) clinical report."""
    docx_bytes = make_test_docx_bytes([
        ("1. INDICATIONS AND USAGE", "Drug Eta is indicated for chronic plaque psoriasis."),
        ("2. DOSAGE AND ADMINISTRATION", "Inject 150 mg subcutaneously at week 0, week 4, then every 12 weeks."),
    ])

    response = client.post(
        "/documents/ingest",
        files={"file": ("eta_label.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"document_name": "Eta Label DOCX"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Eta Label DOCX"
    assert data["chunks_count"] >= 2


# ==============================================================================
# 2. PASTED REGULATORY TEXT INGESTION
# ==============================================================================


def test_pasted_regulatory_text_ingest():
    """Verify ingestion of raw pasted regulatory text via form data."""
    pasted_content = (
        "1. INDICATIONS AND USAGE\n"
        "Lisinopril is indicated for the treatment of hypertension in adults.\n\n"
        "2. DOSAGE AND ADMINISTRATION\n"
        "Initial dose is 10 mg orally once daily. Titrate up to 40 mg daily as needed.\n"
    )

    response = client.post(
        "/documents/ingest",
        data={
            "pasted_text": pasted_content,
            "document_name": "Pasted Lisinopril Label",
            "jurisdiction": "US_FDA",
            "document_type": "REGULATORY_LABEL",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Pasted Lisinopril Label"
    assert data["sections_count"] == 2
    assert data["chunks_count"] == 2
    assert data["jurisdiction"] == "US_FDA"


def test_pasted_text_json_fallback():
    """Verify ingestion of pasted text sent via JSON payload fallback."""
    pasted_content = (
        "1. WARNINGS AND PRECAUTIONS\n"
        "Fetal Toxicity: When pregnancy is detected, discontinue Lisinopril as soon as possible.\n"
    )

    response = client.post(
        "/documents/ingest",
        json={
            "pasted_text": pasted_content,
            "document_name": "JSON Lisinopril Warnings",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "JSON Lisinopril Warnings"
    assert data["chunks_count"] >= 1


# ==============================================================================
# 3. INPUT VALIDATION & ERROR HANDLING
# ==============================================================================


def test_validation_neither_file_nor_text():
    """Verify HTTP 400 when neither file nor pasted_text is provided."""
    response = client.post("/documents/ingest", data={})
    assert response.status_code == 400
    assert "Either file or pasted_text must be provided" in response.json()["detail"]


def test_validation_empty_file():
    """Verify HTTP 400 when uploaded file is zero bytes."""
    response = client.post(
        "/documents/ingest",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 400
    assert "Document content cannot be empty" in response.json()["detail"]


def test_validation_whitespace_only_file():
    """Verify HTTP 400 when uploaded file contains only whitespace."""
    response = client.post(
        "/documents/ingest",
        files={"file": ("whitespace.txt", b"   \n  \t  ", "text/plain")},
    )
    assert response.status_code == 400
    assert "Document content cannot be empty" in response.json()["detail"]


def test_validation_empty_pasted_text():
    """Verify HTTP 400 when pasted text is empty or whitespace."""
    response = client.post(
        "/documents/ingest",
        data={"pasted_text": "   \n  "},
    )
    assert response.status_code == 400
    assert "Document content cannot be empty" in response.json()["detail"]


def test_validation_unsupported_file_extension():
    """Verify HTTP 400 when file extension is not supported, listing allowed formats."""
    response = client.post(
        "/documents/ingest",
        files={"file": ("report.xyz", b"Some random proprietary binary content", "application/octet-stream")},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Unsupported document format" in detail
    assert ".txt" in detail
    assert ".pdf" in detail
    assert ".docx" in detail


def test_validation_corrupt_pdf_document():
    """Verify HTTP 400 with clean parser error on corrupted PDF content."""
    corrupt_bytes = b"%PDF-1.4 CORRUPTED JUNK AND INVALID STRUCTURE"
    response = client.post(
        "/documents/ingest",
        files={"file": ("corrupt.pdf", corrupt_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    assert "Invalid PDF" in response.json()["detail"] or "parsing error" in response.json()["detail"].lower()


def test_zero_usable_chunks_handling():
    """Verify HTTP 200 with chunks_count: 0 when content is too brief to produce chunks."""
    # Text shorter than min_chunk_chars (25 chars) and lacking headings
    brief_text = "Brief note."
    response = client.post(
        "/documents/ingest",
        data={"pasted_text": brief_text, "document_name": "Brief Document"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "Brief Document"
    assert data["chunks_count"] == 0
    assert "0 usable regulatory candidate chunks" in data["message"]


# ==============================================================================
# 4. CANDIDATE DISCOVERY API (POST /candidates/search)
# ==============================================================================


def test_candidate_discovery_ingested_filter():
    """Verify search with source_filter='ingested' discovers candidates from candidate store."""
    # 1. Ingest a document
    client.post(
        "/documents/ingest",
        data={
            "pasted_text": (
                "1. DOSAGE AND ADMINISTRATION\n"
                "Initial dose of Lisinopril is 10 mg orally once daily in adult patients.\n"
            ),
            "document_name": "Lisinopril Tablets PI",
        },
    )

    # 2. Search candidates
    response = client.post(
        "/candidates/search",
        json={
            "query": "lisinopril",
            "source_filter": "ingested",
            "section": "Dosage and Administration",
            "target_text": "Initial dose of Lisinopril is 10 mg orally once daily.",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "lisinopril"
    assert data["source"] == "ingested"
    assert data["total_results"] >= 1
    item = data["items"][0]
    assert item["source"] == "InternalDraft"
    assert item["document_name"] == "Lisinopril Tablets PI"
    assert "10 mg" in item["text"]


def test_candidate_discovery_internal_filter():
    """Verify search with source_filter='internal' behaves equivalently to 'ingested'."""
    client.post(
        "/documents/ingest",
        data={
            "pasted_text": (
                "1. INDICATIONS AND USAGE\n"
                "Amlodipine is indicated for the treatment of hypertension.\n"
            ),
            "document_name": "Amlodipine Monograph",
        },
    )

    response = client.post(
        "/candidates/search",
        json={
            "query": "amlodipine",
            "source_filter": "internal",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "internal"
    assert data["total_results"] >= 1
    assert "Amlodipine" in data["items"][0]["text"]


def test_candidate_discovery_dailymed_filter():
    """Verify search with source_filter='dailymed' queries live DailyMed source."""
    mock_item = RegulatoryContentItem(
        content_id="rc_dm_test_01",
        document_name="DailyMed Atorvastatin",
        source="DailyMed",
        source_identifier="set-atorvastatin-01",
        source_url="https://dailymed.nlm.nih.gov/lookup.cfm?setid=set-atorvastatin-01",
        version="1",
        section="DOSAGE AND ADMINISTRATION",
        text="The recommended starting dose of atorvastatin is 10 or 20 mg once daily.",
    )
    mock_result = RegulatorySearchResult(
        query="atorvastatin",
        total_results=1,
        source="dailymed",
        items=[mock_item],
    )

    with patch(
        "app.routes.candidate_discovery.retriever.sources.search",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = mock_result

        response = client.post(
            "/candidates/search",
            json={
                "query": "atorvastatin",
                "source_filter": "dailymed",
                "top_k": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "dailymed"
        assert data["total_results"] == 1
        assert data["items"][0]["source"] == "DailyMed"
        assert data["items"][0]["source_identifier"] == "set-atorvastatin-01"


def test_candidate_discovery_openfda_filter():
    """Verify search with source_filter='openfda' queries live openFDA source."""
    mock_item = RegulatoryContentItem(
        content_id="rc_fda_test_01",
        document_name="openFDA Metformin Label",
        source="openFDA",
        source_identifier="fda-metformin-01",
        source_url="https://api.fda.gov/drug/label.json?id=fda-metformin-01",
        version="2",
        section="DOSAGE AND ADMINISTRATION",
        text="The starting dose of metformin hydrochloride is 500 mg orally twice a day.",
    )
    mock_result = RegulatorySearchResult(
        query="metformin",
        total_results=1,
        source="openfda",
        items=[mock_item],
    )

    with patch(
        "app.routes.candidate_discovery.retriever.sources.search",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = mock_result

        response = client.post(
            "/candidates/search",
            json={
                "query": "metformin",
                "source_filter": "openfda",
                "top_k": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "openfda"
        assert data["total_results"] == 1
        assert data["items"][0]["source"] == "openFDA"


def test_candidate_discovery_all_sources():
    """Verify search with source_filter='all' queries both candidate store and live sources with deduplication."""
    # 1. Ingest local candidate
    client.post(
        "/documents/ingest",
        data={
            "pasted_text": (
                "1. DOSAGE AND ADMINISTRATION\n"
                "Adults: Initial dose of lisinopril is 10 mg orally once daily.\n"
            ),
            "document_name": "Internal Lisinopril Draft",
        },
    )

    # 2. Mock external source returning near-duplicate candidate
    mock_dm_item = RegulatoryContentItem(
        content_id="rc_dm_lis_01",
        document_name="DailyMed Lisinopril",
        source="DailyMed",
        source_identifier="set-lis-dm",
        source_url="https://dailymed.nlm.nih.gov/set-lis-dm",
        section="DOSAGE AND ADMINISTRATION",
        text="Adults: Initial dose of lisinopril is 10 mg orally once daily.",
    )
    mock_result = RegulatorySearchResult(
        query="lisinopril",
        total_results=1,
        source="all",
        items=[mock_dm_item],
    )

    with patch(
        "app.routes.candidate_discovery.retriever.sources.search",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = mock_result

        response = client.post(
            "/candidates/search",
            json={
                "query": "lisinopril",
                "source_filter": "all",
                "target_text": "Adults: Initial dose of lisinopril is 10 mg orally once daily.",
                "top_k": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "all"
        assert data["total_results"] >= 1
        # Check cross-source provenance merged into metadata
        item = data["items"][0]
        cross_sources = item.get("metadata", {}).get("cross_sources", [])
        assert "DailyMed" in cross_sources or "InternalDraft" in cross_sources


def test_candidate_discovery_invalid_source_filter():
    """Verify HTTP 400 when an invalid source_filter is supplied."""
    response = client.post(
        "/candidates/search",
        json={"query": "lisinopril", "source_filter": "invalid_source"},
    )
    assert response.status_code == 400
    assert "Invalid source_filter" in response.json()["detail"]


def test_candidate_discovery_empty_query():
    """Verify HTTP 400 or 422 when query is empty."""
    response = client.post(
        "/candidates/search",
        json={"query": "   ", "source_filter": "all"},
    )
    assert response.status_code in (400, 422)


def test_candidate_discovery_top_k_validation():
    """Verify HTTP 400 or 422 when top_k is outside 1-50 range."""
    res_low = client.post("/candidates/search", json={"query": "lisinopril", "top_k": 0})
    assert res_low.status_code in (400, 422)

    res_high = client.post("/candidates/search", json={"query": "lisinopril", "top_k": 100})
    assert res_high.status_code in (400, 422)


# ==============================================================================
# 5. TRACEABILITY & PROVENANCE PRESERVATION
# ==============================================================================


def test_traceability_fields_preservation():
    """Verify that all Phase 3 Step 4 traceability fields are preserved on discovered candidates."""
    # Ingest document with rich metadata
    ingest_res = client.post(
        "/documents/ingest",
        data={
            "pasted_text": (
                "1. DOSAGE AND ADMINISTRATION\n"
                "Adults: Take 10 mg once daily.\n"
            ),
            "document_name": "Traceable Clinical Label",
            "jurisdiction": "US_FDA",
            "product_name": "TraceableProduct",
            "active_ingredient": "TraceableSubstance",
            "version": "2.1",
        },
    )
    assert ingest_res.status_code == 200
    doc_id = ingest_res.json()["document_id"]

    search_res = client.post(
        "/candidates/search",
        json={"query": "traceablesubstance", "source_filter": "ingested"},
    )
    assert search_res.status_code == 200
    items = search_res.json()["items"]
    assert len(items) >= 1
    cand = items[0]

    # Verify all Step 4 traceability fields are present and uncorrupted
    assert cand["content_id"].startswith("chk_")
    assert cand["document_id"] == doc_id
    assert cand["document_name"] == "Traceable Clinical Label"
    assert cand["source"] == "InternalDraft"
    assert "pasted_content" in cand["source_url"]
    assert cand["source_identifier"] == doc_id
    assert cand["version"] == "2.1"
    assert cand["section"] == "1. DOSAGE AND ADMINISTRATION"
    assert cand["content_type"] == "paragraph"
    assert "cross_sources" in cand.get("metadata", {})


def test_pdf_page_location_traceability_preservation():
    """Verify that page numbers and exact locations are preserved from PDF ingestion into candidates."""
    pdf_bytes = make_test_pdf_bytes([
        ["1. INDICATIONS AND USAGE", "Drug PageTest is indicated for hypertension."],
        ["2. DOSAGE AND ADMINISTRATION", "Take 20 mg once daily with water."],
    ])

    ingest_res = client.post(
        "/documents/ingest",
        files={"file": ("pagetest_label.pdf", pdf_bytes, "application/pdf")},
        data={"document_name": "PDF Pagination Label"},
    )
    assert ingest_res.status_code == 200
    doc_id = ingest_res.json()["document_id"]

    search_res = client.post(
        "/candidates/search",
        json={"query": "pagetest", "source_filter": "ingested"},
    )
    assert search_res.status_code == 200
    items = search_res.json()["items"]
    assert len(items) >= 1
    cand = items[0]

    assert cand["document_id"] == doc_id
    assert cand["page"] is not None
    assert cand["page"] in (1, 2)
    assert cand["location"] is not None


# ==============================================================================
# 6. BACKWARD COMPATIBILITY PRESERVATION
# ==============================================================================


def test_legacy_documents_upload_compatibility():
    """Verify legacy Phase 1 POST /documents/upload remains functional."""
    response = client.post(
        "/documents/upload",
        json={
            "document_name": "Legacy Upload Test",
            "content": "INDICATIONS AND USAGE\nIndicated for migraine relief.\n\nDOSAGE AND ADMINISTRATION\nTake 1 tablet.",
        },
    )
    assert response.status_code == 200
    sections = response.json()
    assert len(sections) == 2
    assert "INDICATIONS" in sections[0]["section"].upper()


def test_legacy_regulatory_search_compatibility():
    """Verify legacy GET /regulatory/search remains functional."""
    mock_item = RegulatoryContentItem(
        source="DailyMed",
        source_url="https://dailymed.nlm.nih.gov/test",
        source_identifier="legacy-setid",
        document_name="Legacy Aspirin",
        section="Dosage and Administration",
        text="Take 1 tablet daily.",
    )
    mock_result = RegulatorySearchResult(
        query="aspirin",
        total_results=1,
        source="dailymed",
        items=[mock_item],
    )

    with patch(
        "app.routes.regulatory.source_service.search",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = mock_result

        response = client.get("/regulatory/search?query=aspirin&source=dailymed")
        assert response.status_code == 200
        assert response.json()["total_results"] == 1


def test_legacy_content_analyze_compatibility():
    """Verify existing POST /content/analyze continues to work with candidate items."""
    cand = RegulatoryContentItem(
        content_id="chk_compat_01",
        document_name="Reference Label",
        source="InternalDraft",
        section="Dosage and Administration",
        text="Adults: Take 10 mg orally once daily.",
    )

    response = client.post(
        "/content/analyze",
        json={
            "target_text": "Adults: Take 10 mg orally once daily.",
            "section_name": "Dosage and Administration",
            "candidates": [cand.model_dump()],
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["comparison_id"] is not None
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["requires_human_review"] is True
    assert len(result["candidates"][0]["evidence"]) >= 1
