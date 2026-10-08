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


def test_reingestion_idempotence_and_exclusion():
    """Test A: Re-ingesting document with same document_id cleanly replaces chunks and exclusion works."""
    store = IngestedDocumentCandidateStore()

    doc_v1 = _create_sample_doc(
        doc_id="doc_reingest_01",
        title="Sample Regulatory Product",
        drug_name="Acetaminophen",
        text="Adults: Take 500 mg orally every 4 to 6 hours.",
        sec_id="sec_v1",
        chunk_id="chk_v1_01",
    )
    store.add_document(doc_v1)
    assert store.count_documents() == 1
    assert store.count_chunks() == 1
    assert "chk_v1_01" in store._chunks

    # Re-ingest same document_id with updated/new chunks
    doc_v2 = _create_sample_doc(
        doc_id="doc_reingest_01",
        title="Sample Regulatory Product",
        drug_name="Acetaminophen",
        text="Adults: Take 500 mg orally every 4 to 6 hours with a full glass of water.",
        sec_id="sec_v2",
        chunk_id="chk_v2_01",
    )
    store.add_document(doc_v2)
    assert store.count_documents() == 1
    assert store.count_chunks() == 1
    assert "chk_v1_01" not in store._chunks
    assert "chk_v1_01" not in store._content_items
    assert "chk_v2_01" in store._chunks
    assert "chk_v2_01" in store._content_items

    # Searching with exclude_document_id="doc_reingest_01" returns NO chunks from that document
    res = store.search(query="Acetaminophen", exclude_document_id="doc_reingest_01")
    assert len(res) == 0


def test_same_document_name_not_used_for_exclusion():
    """Test B: Two documents with identical names but different document_id are distinguished by identity."""
    store = IngestedDocumentCandidateStore()

    doc_a = _create_sample_doc(
        doc_id="doc_A_100",
        title="Synthetic Regulatory Test",
        drug_name="Acetaminophen",
        text="Dosage: 500 mg orally every 6 hours.",
        sec_id="sec_A",
        chunk_id="chk_A_1",
    )
    doc_b = _create_sample_doc(
        doc_id="doc_B_200",
        title="Synthetic Regulatory Test",  # EXACT SAME NAME
        drug_name="Acetaminophen",
        text="Dosage: 500 mg orally every 4 hours.",
        sec_id="sec_B",
        chunk_id="chk_B_1",
    )
    store.add_document(doc_a)
    store.add_document(doc_b)
    assert store.count_documents() == 2
    assert store.count_chunks() == 2

    # Excluding doc_A by document_id excludes ONLY doc_A; doc_B remains eligible despite identical title
    res = store.search(query="Acetaminophen", exclude_document_id="doc_A_100")
    returned_doc_ids = [it.document_id for it in res]
    assert "doc_A_100" not in returned_doc_ids
    assert "doc_B_200" in returned_doc_ids


@pytest.mark.asyncio
async def test_end_to_end_retriever_internal_draft_exclusion():
    """Test D: Candidate retrieval with exclude_document_id=A never returns InternalDraft candidates from A."""
    store = IngestedDocumentCandidateStore()
    doc_a = _create_sample_doc(
        doc_id="doc_internal_A",
        title="SYN ACET 001 Synthetic Regulatory Test",
        drug_name="Acetaminophen",
        text="Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours.",
        sec_id="sec_A_1",
        chunk_id="chk_A_1",
    )
    # doc_a has provenance source_repository="InternalDraft" and chunk.source="InternalDraft"
    store.add_document(doc_a)

    doc_ref = _create_sample_doc(
        doc_id="doc_external_B",
        title="Reference Label Acetaminophen",
        drug_name="Acetaminophen",
        text="Adults: Take 1 or 2 tablets (500 mg) every 4 to 6 hours as needed.",
        sec_id="sec_B_1",
        chunk_id="chk_B_1",
    )
    store.add_document(doc_ref)

    retriever = LiveRAGRetriever(candidate_store=store)
    results = await retriever.retrieve_candidates(
        target_text="Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours.",
        section_hint="DOSAGE AND ADMINISTRATION",
        source_filter="all",
        exclude_document_id="doc_internal_A",
    )

    returned_doc_ids = [cand.document_id for cand, _, _ in results]

    # Source document A must NEVER appear
    assert "doc_internal_A" not in returned_doc_ids
    # External reference candidate B is returned
    assert "doc_external_B" in returned_doc_ids


# ==============================================================================
# F. DOCUMENT FINGERPRINT REGRESSION TESTS
# ==============================================================================


def test_repeated_upload_exact_same_document_excluded():
    """Test A: Ingest the exact same document twice (new random doc_ids).

    Analyze/search using doc_id_2; assert neither doc_id_1 nor doc_id_2 appears as a candidate.
    """
    sample_text = (
        "1. INDICATIONS AND USAGE\n"
        "Drug Acetaminophen is indicated for temporary relief of mild to moderate pain.\n\n"
        "2. DOSAGE AND ADMINISTRATION\n"
        "Adults: Take 1 or 2 tablets (500 mg each) every 4 to 6 hours as needed.\n"
    )
    # Also ingest a separate reference candidate to verify discovery works
    ref_res = client.post(
        "/documents/ingest",
        json={
            "pasted_text": (
                "1. INDICATIONS AND USAGE\n"
                "External Reference is indicated for fever and mild headache.\n\n"
                "2. DOSAGE AND ADMINISTRATION\n"
                "Adults: Take 500 mg once daily with a full glass of water.\n"
            ),
            "document_name": "External Reference Acetaminophen",
        },
    )
    assert ref_res.status_code == 200
    ref_doc_id = ref_res.json()["document_id"]

    # Upload 1
    res1 = client.post(
        "/documents/ingest",
        json={
            "pasted_text": sample_text,
            "document_name": "SYN ACET 001 Synthetic Regulatory Test",
        },
    )
    assert res1.status_code == 200
    data1 = res1.json()
    doc_id_1 = data1["document_id"]
    fp_1 = data1.get("document_fingerprint")
    assert fp_1 is not None

    # Upload 2 (exact same text, without passing document_id)
    res2 = client.post(
        "/documents/ingest",
        json={
            "pasted_text": sample_text,
            "document_name": "SYN ACET 001 Synthetic Regulatory Test",
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    doc_id_2 = data2["document_id"]
    fp_2 = data2.get("document_fingerprint")
    assert fp_2 is not None

    # Ensure document_id is distinct but document_fingerprint is identical
    assert doc_id_1 != doc_id_2
    assert fp_1 == fp_2

    # Analyze section of doc_id_2
    sec_2 = data2["sections"][1]  # Section 2
    comp_res = client.post(
        "/content/analyze",
        json={
            "target_text": sec_2["text"],
            "section_name": sec_2.get("section"),
            "candidates": [],
            "retrieve_live": True,
            "source_filter": "ingested",
            "top_k": 10,
            "document_id": doc_id_2,
            "target_content_id": sec_2["content_id"],
            "document_name": "SYN ACET 001 Synthetic Regulatory Test",
        },
    )
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    candidate_doc_ids = [c["content_item"]["document_id"] for c in comp_data.get("candidates", [])]

    # Neither doc_id_1 nor doc_id_2 must appear in candidates
    assert doc_id_1 not in candidate_doc_ids
    assert doc_id_2 not in candidate_doc_ids

    # External reference remains discoverable
    assert ref_doc_id in candidate_doc_ids


def test_pasted_text_crlf_vs_lf_produces_identical_fingerprint():
    """Test B: Ingest identical text once using CRLF and once using LF.

    Assert fingerprints are identical and earlier ingestion is excluded from candidate results.
    """
    base_text = (
        "1. INDICATIONS AND USAGE\n"
        "Synthetic Drug Alpha is indicated for acute hypertension.\n\n"
        "2. DOSAGE AND ADMINISTRATION\n"
        "Adults: The recommended dose is 20 mg once daily.\n"
    )
    text_crlf = base_text.replace("\n", "\r\n")
    text_lf = base_text.replace("\r\n", "\n")

    res_crlf = client.post(
        "/documents/ingest",
        json={"pasted_text": text_crlf, "document_name": "Doc CRLF"},
    )
    assert res_crlf.status_code == 200
    data_crlf = res_crlf.json()
    doc_id_crlf = data_crlf["document_id"]
    fp_crlf = data_crlf.get("document_fingerprint")

    res_lf = client.post(
        "/documents/ingest",
        json={"pasted_text": text_lf, "document_name": "Doc LF"},
    )
    assert res_lf.status_code == 200
    data_lf = res_lf.json()
    doc_id_lf = data_lf["document_id"]
    fp_lf = data_lf.get("document_fingerprint")

    # Assert fingerprints are identical despite CRLF vs LF
    assert fp_crlf == fp_lf
    assert doc_id_crlf != doc_id_lf

    # Candidate search excluding doc_id_lf must exclude doc_id_crlf as well
    search_res = client.post(
        "/candidates/search",
        json={
            "query": "Synthetic Drug Alpha",
            "source_filter": "ingested",
            "top_k": 5,
            "exclude_document_id": doc_id_lf,
        },
    )
    assert search_res.status_code == 200
    items = search_res.json().get("items", [])
    returned_doc_ids = [it["document_id"] for it in items]
    assert doc_id_crlf not in returned_doc_ids
    assert doc_id_lf not in returned_doc_ids


def test_same_name_different_content_remains_discoverable():
    """Test C: Same document name but different content produce different fingerprints.

    Assert the different-content document remains a valid candidate.
    """
    store = IngestedDocumentCandidateStore()

    doc_a = _create_sample_doc(
        doc_id="doc_name_A",
        title="Common Drug Label",
        drug_name="Acetaminophen",
        text="Dosage: Take 500 mg orally every 6 hours.",
        sec_id="sec_A",
        chunk_id="chk_A",
    )
    doc_b = _create_sample_doc(
        doc_id="doc_name_B",
        title="Common Drug Label",  # Exact same title
        drug_name="Acetaminophen",
        text="Dosage: Take 650 mg extended-release orally every 8 hours.",  # Different content
        sec_id="sec_B",
        chunk_id="chk_B",
    )
    store.add_document(doc_a)
    store.add_document(doc_b)

    fp_a = store.get_document_fingerprint("doc_name_A")
    fp_b = store.get_document_fingerprint("doc_name_B")
    assert fp_a is not None
    assert fp_b is not None
    assert fp_a != fp_b

    # Searching with exclusion of Doc A excludes Doc A, but Doc B remains discoverable
    results = store.search(query="Acetaminophen", exclude_document_id="doc_name_A")
    doc_ids = [it.document_id for it in results]
    assert "doc_name_A" not in doc_ids
    assert "doc_name_B" in doc_ids


def test_scanned_pdf_different_files_do_not_collide():
    """Test D: Two different binary payloads representing scanned/image-only PDFs.

    Assert fingerprints differ and neither falsely excludes the other.
    """
    from app.models.document import RegulatoryDocument, RegulatoryProvenance, RegulatorySection
    from app.services.ingestion.unified_ingestion import generate_document_fingerprint

    # Simulate two scanned PDFs with identical placeholder text but different binary content
    placeholder_text = "[Scanned image-only PDF: digital text extraction unavailable]"

    doc_scan1 = RegulatoryDocument(
        document_id="doc_scan_1",
        title="Scanned Dossier 1",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        raw_content=placeholder_text,
        sections=[
            RegulatorySection(
                section_id="sec_s1",
                heading_raw="Page 1 (Scanned)",
                raw_text=placeholder_text,
            )
        ],
    )
    doc_scan2 = RegulatoryDocument(
        document_id="doc_scan_2",
        title="Scanned Dossier 2",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        raw_content=placeholder_text,
        sections=[
            RegulatorySection(
                section_id="sec_s2",
                heading_raw="Page 1 (Scanned)",
                raw_text=placeholder_text,
            )
        ],
    )

    # Different raw binary bytes
    binary_bytes_1 = b"%PDF-1.4 simulated binary stream scanned 1 AABBCCDDEE"
    binary_bytes_2 = b"%PDF-1.4 simulated binary stream scanned 2 FFGGHHIIJJ"

    fp_1 = generate_document_fingerprint(binary_bytes_1, doc_scan1)
    fp_2 = generate_document_fingerprint(binary_bytes_2, doc_scan2)

    # Different binaries must produce distinct fingerprints despite identical placeholder text
    assert fp_1 != fp_2

    # Verify store behavior with both
    store = IngestedDocumentCandidateStore()
    doc_scan1.document_fingerprint = fp_1
    doc_scan2.document_fingerprint = fp_2
    store.add_document(doc_scan1, source_bytes=binary_bytes_1)
    store.add_document(doc_scan2, source_bytes=binary_bytes_2)

    assert store.get_document_fingerprint("doc_scan_1") == fp_1
    assert store.get_document_fingerprint("doc_scan_2") == fp_2

    # Excluding doc_scan_1 does not exclude doc_scan_2
    res = store.search(exclude_document_id="doc_scan_1")
    res_doc_ids = [it.document_id for it in res]
    assert "doc_scan_1" not in res_doc_ids
    assert "doc_scan_2" in res_doc_ids


def test_candidate_store_fingerprint_cleanup_on_remove():
    """Test E: Add a document with fingerprint, remove it, and assert indexes are cleaned."""
    store = IngestedDocumentCandidateStore()
    doc = _create_sample_doc(
        doc_id="doc_fp_clean",
        title="Cleanup Test",
        drug_name="Aspirin",
        text="Dosage: 81 mg once daily.",
    )
    store.add_document(doc)
    fp = store.get_document_fingerprint("doc_fp_clean")
    assert fp is not None
    assert "doc_fp_clean" in store._doc_to_fingerprint
    assert fp in store._fingerprint_to_docs
    assert "doc_fp_clean" in store._fingerprint_to_docs[fp]

    # Remove document
    removed = store.remove_document("doc_fp_clean")
    assert removed is True
    assert store.get_document_fingerprint("doc_fp_clean") is None
    assert "doc_fp_clean" not in store._doc_to_fingerprint
    assert fp not in store._fingerprint_to_docs


def test_exact_same_document_uploaded_twice_with_different_document_ids():
    """Verify exact same document content uploaded under different document_ids is excluded by fingerprint."""
    identical_text = (
        "INDICATIONS AND USAGE\n"
        "Indicated for acute moderate pain in adults.\n\n"
        "DOSAGE AND ADMINISTRATION\n"
        "Take 500 mg orally every 6 hours as needed."
    )
    # Upload first instance
    res1 = client.post("/documents/ingest", data={"pasted_text": identical_text, "document_name": "Label Draft A"})
    assert res1.status_code == 200
    doc_id1 = res1.json()["document_id"]
    fp1 = res1.json()["document_fingerprint"]

    # Upload second instance with exact same content but different name
    res2 = client.post("/documents/ingest", data={"pasted_text": identical_text, "document_name": "Label Draft B"})
    assert res2.status_code == 200
    doc_id2 = res2.json()["document_id"]
    fp2 = res2.json()["document_fingerprint"]

    assert doc_id1 != doc_id2
    assert fp1 == fp2  # Identical content yields identical fingerprint

    # Exclude Document 1 by document_id or fingerprint
    search_res = client.post(
        "/candidates/search",
        json={
            "query": "pain",
            "source_filter": "ingested",
            "exclude_document_id": doc_id1,
            "exclude_document_fingerprint": fp1,
        },
    )
    assert search_res.status_code == 200
    items = search_res.json()["items"]
    # Neither instance should appear in results
    found_doc_ids = {item["document_id"] for item in items}
    assert doc_id1 not in found_doc_ids
    assert doc_id2 not in found_doc_ids


def test_direct_comparison_navigation_with_active_source_document():
    """Verify navigating directly to Comparison with active source document excludes source document even with fallback target text."""
    source_text = (
        "DOSAGE AND ADMINISTRATION\n"
        "Adults: Take 250 mg orally twice daily with a full glass of water."
    )
    res_ingest = client.post("/documents/ingest", json={"pasted_text": source_text, "document_name": "Source Dossier"})
    assert res_ingest.status_code == 200
    doc_id = res_ingest.json()["document_id"]
    fp = res_ingest.json()["document_fingerprint"]

    # Ingest a distinct precedent document that should remain discoverable
    precedent_text = (
        "DOSAGE AND ADMINISTRATION\n"
        "Adults: Take 500 mg orally twice daily with a full glass of water."
    )
    res_prec = client.post("/documents/ingest", json={"pasted_text": precedent_text, "document_name": "Precedent Guide"})
    assert res_prec.status_code == 200
    prec_doc_id = res_prec.json()["document_id"]

    # Direct Comparison navigation uses activeSourceDocument section text / fallback, and sends activeSourceDocument identity
    analyze_res = client.post(
        "/content/analyze",
        json={
            "target_text": "Adults: Take 250 mg orally twice daily with a full glass of water.",
            "section_name": "DOSAGE AND ADMINISTRATION",
            "retrieve_live": True,
            "source_filter": "ingested",
            "document_id": doc_id,
            "exclude_document_id": doc_id,
            "exclude_document_fingerprint": fp,
        },
    )
    assert analyze_res.status_code == 200
    candidates = analyze_res.json().get("candidates", [])
    cand_doc_ids = {c["content_item"]["document_id"] for c in candidates}
    assert doc_id not in cand_doc_ids
    assert prec_doc_id in cand_doc_ids


def test_post_documents_upload_lifecycle_parity():
    """Verify POST /documents/upload uses canonical store lifecycle and supports candidate exclusion."""
    store = get_candidate_store()
    raw_text = (
        "INDICATIONS AND USAGE\n"
        "Indicated for rheumatoid arthritis management.\n\n"
        "DOSAGE AND ADMINISTRATION\n"
        "Administer 10 mg weekly subcutaneously."
    )
    res_upload = client.post(
        "/documents/upload",
        json={"document_name": "Arthritis Protocol", "content": raw_text},
    )
    assert res_upload.status_code == 200
    sections = res_upload.json()
    assert len(sections) == 2
    doc_id = sections[0]["document_id"]
    doc_fp = sections[0]["document_fingerprint"]
    assert doc_id is not None
    assert doc_fp is not None

    # Lifecycle parity: registered in canonical store structures
    stored_doc = store.get_document(doc_id)
    assert stored_doc is not None
    assert stored_doc.document_fingerprint == doc_fp
    assert store.get_document_fingerprint(doc_id) == doc_fp
    assert store.has_source_document(doc_id) is True
    assert len(store.list_content_items(doc_id)) == 2

    # Verify exclusion works with upload
    search_res = client.post(
        "/candidates/search",
        json={
            "query": "arthritis",
            "source_filter": "ingested",
            "exclude_document_id": doc_id,
            "exclude_document_fingerprint": doc_fp,
        },
    )
    assert search_res.status_code == 200
    found_doc_ids = {it["document_id"] for it in search_res.json()["items"]}
    assert doc_id not in found_doc_ids


def test_adapter_fingerprint_preservation():
    """Verify regulatory_adapter preserves document_fingerprint when converting RegulatoryChunk to RegulatoryContentItem."""
    from app.services.compatibility.regulatory_adapter import chunk_to_content_item, section_to_content_item
    chunk = RegulatoryChunk(
        chunk_id="chk_test_fp_adapt",
        document_id="doc_test_adapt",
        section_id="sec_test_adapt",
        document_fingerprint="fp_canonical_sample_999",
        document_name="Adapter Test Doc",
        section_title="Dosage",
        content="Take 10 mg daily.",
        source="InternalDraft",
    )
    item = chunk_to_content_item(chunk)
    assert item.document_fingerprint == "fp_canonical_sample_999"
    assert item.document_id == "doc_test_adapt"

    doc = RegulatoryDocument(
        document_id="doc_tree_parent",
        document_fingerprint="fp_doc_tree_888",
        title="Tree Doc",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
    )
    section = RegulatorySection(
        section_id="sec_tree_child",
        heading_raw="Warnings",
        raw_text="Warning statement text.",
    )
    item_sec = section_to_content_item(section, doc)
    assert item_sec.document_fingerprint == "fp_doc_tree_888"


def test_presupplied_candidate_list_containing_source_document():
    """Verify POST /content/analyze removes source document candidates from pre-supplied candidate list."""
    source_fp = "fp_target_dossier_001"
    cand_self = RegulatoryContentItem(
        content_id="cand_self_chunk",
        document_id="doc_target_dossier",
        document_fingerprint=source_fp,
        document_name="Target Dossier",
        source="InternalDraft",
        section="Dosage and Administration",
        text="Adults: Take 100 mg once daily.",
    )
    cand_external = RegulatoryContentItem(
        content_id="cand_ext_dailymed",
        document_id="doc_dailymed_ref",
        document_name="DailyMed Reference Label",
        source="DailyMed",
        section="Dosage and Administration",
        text="Adults: Take 100 mg to 200 mg once daily.",
    )

    res = client.post(
        "/content/analyze",
        json={
            "target_text": "Adults: Take 100 mg once daily with food.",
            "candidates": [cand_self.model_dump(), cand_external.model_dump()],
            "document_id": "doc_target_dossier",
            "exclude_document_id": "doc_target_dossier",
            "exclude_document_fingerprint": source_fp,
        },
    )
    assert res.status_code == 200
    candidates = res.json().get("candidates", [])
    evaluated_ids = [c["content_item"]["content_id"] for c in candidates]
    # Source chunk must be pruned
    assert "cand_self_chunk" not in evaluated_ids
    # External candidate must proceed to 6D evaluation
    assert "cand_ext_dailymed" in evaluated_ids


def test_same_name_different_content_remains_eligible():
    """Verify documents with the exact same title/name but different content remain eligible precedents."""
    text_a = "INDICATIONS AND USAGE\nPediatric formulation for juvenile arthritis: 5 mg daily."
    text_b = "INDICATIONS AND USAGE\nAdult formulation for osteoarthritis: 200 mg twice daily."

    # Both documents share the exact same title "Standard Prescribing Guide"
    res_a = client.post("/documents/ingest", data={"pasted_text": text_a, "document_name": "Standard Prescribing Guide"})
    res_b = client.post("/documents/ingest", data={"pasted_text": text_b, "document_name": "Standard Prescribing Guide"})

    assert res_a.status_code == 200
    assert res_b.status_code == 200

    doc_a_id = res_a.json()["document_id"]
    doc_a_fp = res_a.json()["document_fingerprint"]
    doc_b_id = res_b.json()["document_id"]
    doc_b_fp = res_b.json()["document_fingerprint"]

    assert doc_a_id != doc_b_id
    assert doc_a_fp != doc_b_fp

    # Search excluding Document A
    search_res = client.post(
        "/candidates/search",
        json={
            "query": "arthritis",
            "source_filter": "ingested",
            "exclude_document_id": doc_a_id,
            "exclude_document_fingerprint": doc_a_fp,
        },
    )
    assert search_res.status_code == 200
    found_doc_ids = {it["document_id"] for it in search_res.json()["items"]}
    assert doc_a_id not in found_doc_ids
    assert doc_b_id in found_doc_ids  # Same name, different content: MUST remain eligible!


def test_external_dailymed_openfda_candidates_remain_eligible():
    """Verify exclusion of internal source document never filters external DailyMed or openFDA precedents."""
    source_fp = "fp_internal_strict_777"
    source_item = RegulatoryContentItem(
        content_id="internal_chk_1",
        document_id="doc_internal_strict",
        document_fingerprint=source_fp,
        document_name="Internal Label",
        source="InternalDraft",
        section="Indications",
        text="Internal indication text.",
    )
    dailymed_item = RegulatoryContentItem(
        content_id="dm_chk_1",
        document_id="dailymed_set_123",
        document_name="Approved Drug Label",
        source="DailyMed",
        section="Indications",
        text="FDA approved indication text.",
    )
    openfda_item = RegulatoryContentItem(
        content_id="fda_chk_1",
        document_id="openfda_app_456",
        document_name="Package Insert",
        source="openFDA",
        section="Indications",
        text="openFDA official label text.",
    )

    agent = RegulatoryContentAnalysisAgent()
    result = agent.analyze_and_compare(
        target_text="Internal indication text for acute headache.",
        candidates=[source_item, dailymed_item, openfda_item],
        exclude_document_id="doc_internal_strict",
        exclude_document_fingerprint=source_fp,
    )
    res_cands = [c.content_item.content_id for c in result.candidates]
    assert "internal_chk_1" not in res_cands
    assert "dm_chk_1" in res_cands
    assert "fda_chk_1" in res_cands
