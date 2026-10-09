"""Unit tests for remediation of candidate discovery, document restoration,
safe section text retrieval, and external source handling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient

from app.main import app
from app.models.content import KeyInformation, RegulatoryContentItem
from app.services.candidate_store import IngestedDocumentCandidateStore, get_candidate_store
from app.services.rag_retriever import LiveRAGRetriever, is_section_heading
from app.services.regulatory_source import DailyMedSource, OpenFDASource

client = TestClient(app)


def test_is_section_heading_detector():
    """Verify that section headings are accurately identified and real drug names are not."""
    # Section headings should return True
    assert is_section_heading("Section 1 — Storage") is True
    assert is_section_heading("1. INDICATIONS AND USAGE") is True
    assert is_section_heading("DOSAGE AND ADMINISTRATION") is True
    assert is_section_heading("Contraindications") is True
    assert is_section_heading("Warnings and Precautions") is True
    assert is_section_heading("Storage and Handling") is True
    assert is_section_heading("Part 2 — Adverse Reactions") is True

    # Real drug names must return False
    assert is_section_heading("Acetaminophen") is False
    assert is_section_heading("Lisinopril") is False
    assert is_section_heading("Atorvastatin Calcium") is False
    assert is_section_heading("Metformin HCl") is False
    assert is_section_heading("") is False
    assert is_section_heading(None) is False


def test_get_stored_document_and_section_endpoints():
    """Verify GET /documents/{document_id} and GET /documents/section/{content_id} endpoints."""
    # 1. Ingest a test document
    payload = {
        "pasted_text": (
            "1. INDICATIONS AND USAGE\n"
            "Drug Gamma is indicated for temporary headache relief.\n\n"
            "2. DOSAGE AND ADMINISTRATION\n"
            "Adults: Take 100 mg orally once daily with water.\n"
        ),
        "document_name": "Test Dossier Gamma",
        "jurisdiction": "US_FDA",
    }
    ingest_res = client.post("/documents/ingest", json=payload)
    assert ingest_res.status_code == 200
    doc_data = ingest_res.json()
    doc_id = doc_data["document_id"]
    doc_fp = doc_data["document_fingerprint"]
    sections = doc_data["sections"]
    assert len(sections) >= 2
    sec_content_id = sections[0]["content_id"]

    # 2. Retrieve document by ID
    get_doc_res = client.get(f"/documents/{doc_id}")
    assert get_doc_res.status_code == 200
    retrieved_doc = get_doc_res.json()
    assert retrieved_doc["document_id"] == doc_id
    assert retrieved_doc["document_fingerprint"] == doc_fp
    assert retrieved_doc["document_name"] == "Test Dossier Gamma"
    assert retrieved_doc["jurisdiction"] == "US_FDA"
    assert len(retrieved_doc["sections"]) >= 2
    assert retrieved_doc["sections"][0]["content_id"] == sec_content_id

    # 3. Retrieve specific section by content ID
    get_sec_res = client.get(f"/documents/section/{sec_content_id}")
    assert get_sec_res.status_code == 200
    retrieved_sec = get_sec_res.json()
    assert retrieved_sec["content_id"] == sec_content_id
    assert "Drug Gamma is indicated" in retrieved_sec["text"]
    assert retrieved_sec["document_id"] == doc_id

    # 4. Error cases: nonexistent IDs
    res_404_doc = client.get("/documents/nonexistent_document_xyz_123")
    assert res_404_doc.status_code == 404

    res_404_sec = client.get("/documents/section/nonexistent_section_xyz_123")
    assert res_404_sec.status_code == 404


@pytest.mark.asyncio
async def test_retriever_never_queries_dailymed_with_section_heading():
    """Verify that LiveRAGRetriever never sends a section heading to DailyMed as drug_name."""
    mock_candidate_store = MagicMock()
    mock_candidate_store.get_document.return_value = None
    mock_candidate_store.search.return_value = []
    mock_candidate_store.list_all_chunks.return_value = []

    mock_sources = MagicMock()
    mock_sources.search = AsyncMock()
    mock_sources.openfda = MagicMock()
    mock_sources.openfda.search = AsyncMock(return_value=[])

    retriever = LiveRAGRetriever(
        candidate_store=mock_candidate_store,
        source_service=mock_sources,
    )

    # When query is a section title and key_info has no drug name:
    results = await retriever.retrieve_candidates(
        target_text="Store at room temperature 20°C to 25°C.",
        section_hint="Section 1 — Storage",
        source_filter="dailymed",
        target_key_info=KeyInformation(drug=None, active_ingredient=None),
    )

    # DailyMed search MUST NOT be called with a section heading as the drug_name query
    mock_sources.search.assert_not_called()


@pytest.mark.asyncio
async def test_retriever_uses_verified_drug_name_when_available():
    """Verify that LiveRAGRetriever uses verified drug from key_info for external search."""
    mock_candidate_store = MagicMock()
    mock_candidate_store.get_document.return_value = None
    mock_candidate_store.search.return_value = []
    mock_candidate_store.list_all_chunks.return_value = []

    mock_sources = MagicMock()
    search_result_mock = MagicMock()
    search_result_mock.items = [
        RegulatoryContentItem(
            content_id="cand_1",
            document_id="doc_ext_1",
            document_name="Lisinopril Label",
            source="DailyMed",
            section="Storage",
            text="Store at 20°C to 25°C (68°F to 77°F). Protect from moisture.",
        )
    ]
    mock_sources.search = AsyncMock(return_value=search_result_mock)

    retriever = LiveRAGRetriever(
        candidate_store=mock_candidate_store,
        source_service=mock_sources,
    )

    results = await retriever.retrieve_candidates(
        target_text="Store at 20°C to 25°C (68°F to 77°F).",
        section_hint="Storage",
        source_filter="dailymed",
        target_key_info=KeyInformation(drug="Lisinopril"),
    )

    # DailyMed search should have been called with "Lisinopril"
    mock_sources.search.assert_called_once()
    called_args = mock_sources.search.call_args[1]
    assert called_args["query"] == "Lisinopril"
    assert len(results) == 1
    # Each result is a tuple: (candidate_item, similarity_score, embedding_provider)
    assert results[0][0].document_name == "Lisinopril Label"
