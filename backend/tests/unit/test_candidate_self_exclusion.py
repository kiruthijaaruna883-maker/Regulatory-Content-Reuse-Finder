"""Focused regression tests for source-document self-exclusion in GPR candidate discovery.

Verifies:
A. Candidate store:
   - Store Document A and Document B.
   - Search while excluding Document A.
   - Document A is completely absent from results.
   - Document B remains discoverable.
B. Retriever:
   - Target text belongs to Document A.
   - Exclude Document A via exclude_document_id.
   - Document A never appears in returned candidates.
   - Document B can still appear.
C. Agent analyze_and_retrieve:
   - target_document_id = Document A.
   - Candidate results never contain Document A.
   - Fallback resolution of document_id from target_content_id works safely.
D. Agent analyze_and_compare:
   - Supply candidate list containing both Document A and Document B.
   - target_document_id = Document A.
   - Document A is stripped before comparison.
   - Document B remains eligible for comparison.
E. Regression/API coverage:
   - Actual candidate-discovery path used by UI (/content/analyze and /candidates/search).
   - Ingested source document is completely absent from candidate results.
"""

import pytest
from fastapi.testclient import TestClient

from app.agents.content_analysis_agent import RegulatoryContentAnalysisAgent
from app.main import app
from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document import (
    RegulatoryChunk,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.candidate_store import (
    IngestedDocumentCandidateStore,
    get_candidate_store,
    reset_candidate_store,
)
from app.services.rag_retriever import LiveRAGRetriever

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_candidate_store():
    """Ensure candidate store isolation for every test."""
    reset_candidate_store()
    yield
    reset_candidate_store()


def _create_sample_doc(
    doc_id: str,
    title: str,
    drug_name: str,
    text: str,
    sec_id: str = "sec_01",
    chunk_id: str = "chk_01",
) -> RegulatoryDocument:
    """Helper to build a valid RegulatoryDocument with 1 section and 1 chunk."""
    return RegulatoryDocument(
        document_id=doc_id,
        title=title,
        document_type="REGULATORY_LABEL",
        jurisdiction="US_FDA",
        product_name=drug_name,
        active_ingredient=drug_name,
        provenance=RegulatoryProvenance(
            source_repository="InternalDraft",
            source_identifier=doc_id,
            source_url=f"file://{doc_id}.txt",
            version="1.0",
        ),
        sections=[
            RegulatorySection(
                section_id=sec_id,
                section_number="2",
                heading_raw="2. DOSAGE AND ADMINISTRATION",
                raw_text=text,
                chunks=[
                    RegulatoryChunk(
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        section_id=sec_id,
                        chunk_type="paragraph",
                        order_index=0,
                        structure_path=f"{title} > Dosage and Administration",
                        content=text,
                        document_name=title,
                        section_title="DOSAGE AND ADMINISTRATION",
                        section_number="2",
                        active_ingredient=drug_name,
                        product=drug_name,
                        source="InternalDraft",
                        source_identifier=doc_id,
                        exact_location="Paragraph 1",
                        page=1,
                        key_information=KeyInformation(
                            drug=drug_name,
                            active_ingredient=drug_name,
                            dose="10 mg",
                            frequency="once daily",
                            route="Oral",
                        ),
                    )
                ],
            )
        ],
    )


# ==============================================================================
# A. CANDIDATE STORE UNIT TESTS
# ==============================================================================


def test_candidate_store_excludes_source_document():
    """Verify candidate_store.search completely excludes source document by document_id."""
    store = IngestedDocumentCandidateStore()

    doc_a = _create_sample_doc(
        doc_id="doc_source_A",
        title="Document A Label",
        drug_name="Lisinopril",
        text="Adults: Recommended starting dose of Lisinopril is 10 mg orally once daily.",
        chunk_id="chk_A_001",
    )
    doc_b = _create_sample_doc(
        doc_id="doc_reference_B",
        title="Document B Reference",
        drug_name="Lisinopril",
        text="Adults: Usual maintenance dose of Lisinopril is 20 mg to 40 mg once daily.",
        chunk_id="chk_B_001",
    )

    store.add_document(doc_a)
    store.add_document(doc_b)

    # Search without exclusion: both documents can match
    all_results = store.search(query="Lisinopril", limit=10)
    all_doc_ids = {item.document_id for item in all_results}
    assert "doc_source_A" in all_doc_ids
    assert "doc_reference_B" in all_doc_ids

    # Search WITH exclusion of Document A
    filtered_results = store.search(
        query="Lisinopril",
        limit=10,
        exclude_document_id="doc_source_A",
    )

    filtered_doc_ids = {item.document_id for item in filtered_results}
    assert "doc_source_A" not in filtered_doc_ids
    assert "doc_reference_B" in filtered_doc_ids
    assert all(item.document_id != "doc_source_A" for item in filtered_results)


def test_candidate_store_excludes_by_content_id():
    """Verify candidate_store.search excludes candidate matching exclude_content_id."""
    store = IngestedDocumentCandidateStore()

    doc_a = _create_sample_doc(
        doc_id="doc_source_A",
        title="Document A Label",
        drug_name="Lisinopril",
        text="Adults: Recommended starting dose of Lisinopril is 10 mg orally once daily.",
        chunk_id="chk_A_001",
    )
    doc_b = _create_sample_doc(
        doc_id="doc_reference_B",
        title="Document B Reference",
        drug_name="Lisinopril",
        text="Adults: Usual maintenance dose of Lisinopril is 20 mg to 40 mg once daily.",
        chunk_id="chk_B_001",
    )

    store.add_document(doc_a)
    store.add_document(doc_b)

    filtered_results = store.search(
        query="Lisinopril",
        limit=10,
        exclude_content_id="chk_A_001",
    )

    filtered_content_ids = {item.content_id for item in filtered_results}
    assert "chk_A_001" not in filtered_content_ids
    assert "chk_B_001" in filtered_content_ids


# ==============================================================================
# B. RETRIEVER TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_retriever_excludes_source_document():
    """Verify LiveRAGRetriever completely excludes source document from candidate results."""
    store = IngestedDocumentCandidateStore()
    retriever = LiveRAGRetriever(candidate_store=store)

    doc_a = _create_sample_doc(
        doc_id="doc_source_A",
        title="Document A Label",
        drug_name="Atorvastatin",
        text="Adults: The recommended starting dose of Atorvastatin is 10 mg or 20 mg orally once daily.",
        chunk_id="chk_A_atorva",
    )
    doc_b = _create_sample_doc(
        doc_id="doc_reference_B",
        title="Document B Reference",
        drug_name="Atorvastatin",
        text="Patients: The recommended starting dose of Atorvastatin is 10 mg orally once daily.",
        chunk_id="chk_B_atorva",
    )

    store.add_document(doc_a)
    store.add_document(doc_b)

    target_text = "Adults: The recommended starting dose of Atorvastatin is 10 mg or 20 mg orally once daily."

    # When querying with exclude_document_id="doc_source_A"
    results = await retriever.retrieve_candidates(
        target_text=target_text,
        source_filter="ingested",
        top_k=5,
        exclude_document_id="doc_source_A",
    )

    returned_doc_ids = {cand.document_id for cand, _, _ in results}
    assert "doc_source_A" not in returned_doc_ids
    assert "doc_reference_B" in returned_doc_ids
    assert all(cand.document_id != "doc_source_A" for cand, _, _ in results)


# ==============================================================================
# C. AGENT ANALYZE_AND_RETRIEVE TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_agent_analyze_and_retrieve_excludes_source_document():
    """Verify analyze_and_retrieve never returns source document among candidates."""
    store = IngestedDocumentCandidateStore()
    retriever = LiveRAGRetriever(candidate_store=store)
    agent = RegulatoryContentAnalysisAgent(retriever=retriever)

    doc_a = _create_sample_doc(
        doc_id="doc_source_A",
        title="Document A Label",
        drug_name="Metformin",
        text="Adults: The starting dose of Metformin is 500 mg orally twice daily with meals.",
        chunk_id="chk_A_met",
    )
    doc_b = _create_sample_doc(
        doc_id="doc_reference_B",
        title="Document B Reference",
        drug_name="Metformin",
        text="Adults: The usual starting dose of Metformin is 500 mg twice a day taken with food.",
        chunk_id="chk_B_met",
    )

    store.add_document(doc_a)
    store.add_document(doc_b)

    target_text = "Adults: The starting dose of Metformin is 500 mg orally twice daily with meals."

    result = await agent.analyze_and_retrieve(
        target_text=target_text,
        section_name="DOSAGE AND ADMINISTRATION",
        source_filter="ingested",
        top_k=5,
        target_document_id="doc_source_A",
        target_content_id="chk_A_met",
    )

    returned_candidate_doc_ids = {c.content_item.document_id for c in result.candidates}
    returned_candidate_content_ids = {c.content_item.content_id for c in result.candidates}

    assert "doc_source_A" not in returned_candidate_doc_ids
    assert "chk_A_met" not in returned_candidate_content_ids
    assert "doc_reference_B" in returned_candidate_doc_ids


@pytest.mark.asyncio
async def test_agent_analyze_and_retrieve_fallback_exclusion_via_content_id():
    """Verify agent resolves document_id from candidate store if target_document_id is None."""
    store = IngestedDocumentCandidateStore()
    retriever = LiveRAGRetriever(candidate_store=store)
    agent = RegulatoryContentAnalysisAgent(retriever=retriever)

    doc_a = _create_sample_doc(
        doc_id="doc_source_A",
        title="Document A Label",
        drug_name="Metformin",
        text="Adults: The starting dose of Metformin is 500 mg orally twice daily with meals.",
        chunk_id="chk_A_met",
    )
    doc_b = _create_sample_doc(
        doc_id="doc_reference_B",
        title="Document B Reference",
        drug_name="Metformin",
        text="Adults: The usual starting dose of Metformin is 500 mg twice a day taken with food.",
        chunk_id="chk_B_met",
    )

    store.add_document(doc_a)
    store.add_document(doc_b)

    target_text = "Adults: The starting dose of Metformin is 500 mg orally twice daily with meals."

    # target_document_id is None, but target_content_id is provided
    result = await agent.analyze_and_retrieve(
        target_text=target_text,
        section_name="DOSAGE AND ADMINISTRATION",
        source_filter="ingested",
        top_k=5,
        target_document_id=None,
        target_content_id="chk_A_met",
    )

    returned_candidate_doc_ids = {c.content_item.document_id for c in result.candidates}
    assert "doc_source_A" not in returned_candidate_doc_ids
    assert "doc_reference_B" in returned_candidate_doc_ids


# ==============================================================================
# D. AGENT ANALYZE_AND_COMPARE TESTS
# ==============================================================================


def test_agent_analyze_and_compare_defensively_removes_source_document():
    """Verify analyze_and_compare strips source document even when supplied directly in candidate list."""
    agent = RegulatoryContentAnalysisAgent()

    item_a = RegulatoryContentItem(
        content_id="chk_A_direct",
        document_id="doc_source_A",
        document_name="Document A",
        source="InternalDraft",
        text="Adults: Take 10 mg orally once daily.",
        key_information=KeyInformation(drug="Amlodipine", dose="10 mg", frequency="once daily"),
    )
    item_b = RegulatoryContentItem(
        content_id="chk_B_direct",
        document_id="doc_reference_B",
        document_name="Document B",
        source="DailyMed",
        text="Adults: Recommended dose is 5 mg to 10 mg once daily.",
        key_information=KeyInformation(drug="Amlodipine", dose="5 mg to 10 mg", frequency="once daily"),
    )

    result = agent.analyze_and_compare(
        target_text="Adults: Take 10 mg orally once daily.",
        candidates=[item_a, item_b],
        target_document_id="doc_source_A",
        target_content_id="chk_A_direct",
    )

    # Document A candidate must be removed; only Document B is evaluated
    assert len(result.candidates) == 1
    assert result.candidates[0].content_item.document_id == "doc_reference_B"
    assert result.candidates[0].content_item.content_id == "chk_B_direct"
    assert all(c.content_item.document_id != "doc_source_A" for c in result.candidates)


# ==============================================================================
# E. REGRESSION / API COVERAGE TESTS
# ==============================================================================


def test_api_analyze_excludes_ingested_source_document():
    """Verify actual API flow: ingest document, then /content/analyze never returns the source document."""
    # 1. Ingest Document A
    ingest_payload = {
        "pasted_text": (
            "1. INDICATIONS AND USAGE\n"
            "Drug Alpha is indicated for hypertension in adult patients.\n\n"
            "2. DOSAGE AND ADMINISTRATION\n"
            "The recommended initial dosage is 10 mg orally once daily.\n"
        ),
        "document_name": "Source Document Alpha",
    }
    ingest_res = client.post("/documents/ingest", json=ingest_payload)
    assert ingest_res.status_code == 200
    doc_data = ingest_res.json()
    source_doc_id = doc_data["document_id"]
    sections = doc_data["sections"]
    assert len(sections) >= 2
    target_sec = sections[1]  # Section 2

    # Ingest a second document (Reference Document Beta) to serve as a valid reuse candidate
    ref_payload = {
        "pasted_text": (
            "1. INDICATIONS AND USAGE\n"
            "Drug Alpha is indicated for hypertension.\n\n"
            "2. DOSAGE AND ADMINISTRATION\n"
            "The initial dose of Drug Alpha is 10 mg once daily in the morning.\n"
        ),
        "document_name": "Reference Document Beta",
    }
    ref_res = client.post("/documents/ingest", json=ref_payload)
    assert ref_res.status_code == 200
    ref_data = ref_res.json()
    ref_doc_id = ref_data["document_id"]

    # 2. Trigger automatic discovery via /content/analyze for target section of Document Alpha
    analyze_payload = {
        "target_text": target_sec["text"],
        "section_name": target_sec.get("section"),
        "candidates": [],
        "retrieve_live": True,
        "source_filter": "ingested",
        "top_k": 10,
        "document_id": source_doc_id,
        "target_content_id": target_sec["content_id"],
        "document_name": "Source Document Alpha",
    }
    analyze_res = client.post("/content/analyze", json=analyze_payload)
    assert analyze_res.status_code == 200
    comp_result = analyze_res.json()

    candidates = comp_result.get("candidates", [])
    candidate_doc_ids = [c["content_item"]["document_id"] for c in candidates]
    candidate_content_ids = [c["content_item"]["content_id"] for c in candidates]

    # Source document MUST NEVER be in the similarity candidate results
    assert source_doc_id not in candidate_doc_ids
    assert target_sec["content_id"] not in candidate_content_ids
    # Reference Document Beta should be present
    assert ref_doc_id in candidate_doc_ids


def test_api_candidates_search_excludes_source_document():
    """Verify /candidates/search endpoint excludes source document when exclude_document_id is provided."""
    # Ingest Document A
    res_a = client.post(
        "/documents/ingest",
        json={
            "pasted_text": "Dosage: 50 mg orally once daily.",
            "document_name": "Document A",
        },
    )
    assert res_a.status_code == 200
    doc_a_id = res_a.json()["document_id"]

    # Ingest Document B
    res_b = client.post(
        "/documents/ingest",
        json={
            "pasted_text": "Dosage: 50 mg orally once daily with water.",
            "document_name": "Document B",
        },
    )
    assert res_b.status_code == 200
    doc_b_id = res_b.json()["document_id"]

    # Search with exclude_document_id=doc_a_id
    search_payload = {
        "query": "50 mg",
        "source_filter": "ingested",
        "top_k": 5,
        "exclude_document_id": doc_a_id,
    }
    search_res = client.post("/candidates/search", json=search_payload)
    assert search_res.status_code == 200
    search_data = search_res.json()

    results_doc_ids = [it["document_id"] for it in search_data.get("items", [])]
    assert doc_a_id not in results_doc_ids
    assert doc_b_id in results_doc_ids
