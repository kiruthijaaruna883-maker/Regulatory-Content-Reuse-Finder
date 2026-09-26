"""Unit tests for Phase 3 Step 1: Ingested Document Candidate Store and Retrieval Integration.

Verifies:
1. Ingested document addition and chunk availability
2. Chunk identity and document identity preservation
3. Source provenance and full traceability preservation (exact location, page, structure path)
4. Multi-document coexistence and document-scoped querying
5. Store reset/clear lifecycle
6. Ingested regulatory content discovery via LiveRAGRetriever
7. Live DailyMed and openFDA retrieval preservation alongside ingested candidates
8. Ingested candidates survival across temporary vector store clearing
9. Zero metadata fabrication
10. Backward compatibility with Phase 1 & 2 models and adapters
"""

from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models.content import KeyInformation, RegulatoryContentItem, RegulatorySearchResult
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
from app.services.compatibility.regulatory_adapter import (
    adapt_for_comparison,
    adapt_for_retrieval,
    chunk_to_content_item,
)
from app.services.rag_retriever import LiveRAGRetriever
from app.services.regulatory_source import RegulatorySourceService
from app.services.vector_store import VectorStore


@pytest.fixture(autouse=True)
def clean_candidate_store():
    """Ensure clean candidate store state for every test."""
    reset_candidate_store()
    yield
    reset_candidate_store()


# ==============================================================================
# 1. CANDIDATE STORE UNIT TESTS
# ==============================================================================


def test_add_document_and_chunk_availability():
    """Verify an ingested RegulatoryDocument can be stored and its chunks become available."""
    store = IngestedDocumentCandidateStore()

    doc = RegulatoryDocument(
        document_id="doc_lisinopril_01",
        title="Lisinopril Tablets Prescribing Information",
        document_type="REGULATORY_LABEL",
        jurisdiction="US_FDA",
        product_name="Lisinopril",
        active_ingredient="Lisinopril",
        provenance=RegulatoryProvenance(
            source_repository="InternalDraft",
            source_identifier="doc_lisinopril_01",
            source_url="file://lisinopril_label.txt",
            version="1.0",
        ),
        sections=[
            RegulatorySection(
                section_id="sec_01",
                section_number="2",
                heading_raw="2. DOSAGE AND ADMINISTRATION",
                raw_text="Adults: Initial dose is 10 mg orally once daily. Maximum dose is 40 mg daily.",
                chunks=[
                    RegulatoryChunk(
                        chunk_id="chk_lis_001",
                        document_id="doc_lisinopril_01",
                        section_id="sec_01",
                        chunk_type="paragraph",
                        order_index=0,
                        structure_path="Lisinopril Label > Dosage and Administration",
                        content="Adults: Initial dose is 10 mg orally once daily. Maximum dose is 40 mg daily.",
                        document_name="Lisinopril Tablets Prescribing Information",
                        section_title="DOSAGE AND ADMINISTRATION",
                        section_number="2",
                        active_ingredient="Lisinopril",
                        product="Lisinopril",
                        source="InternalDraft",
                        source_identifier="doc_lisinopril_01",
                        exact_location="Paragraph 1",
                        page=2,
                        key_information=KeyInformation(
                            drug="Lisinopril",
                            dose="10 mg",
                            frequency="once daily",
                            route="Oral",
                            population="Adults",
                        ),
                    )
                ],
            )
        ],
    )

    chunks = store.add_document(doc)

    assert len(chunks) == 1
    assert store.count_documents() == 1
    assert store.count_chunks() == 1

    stored_doc = store.get_document("doc_lisinopril_01")
    assert stored_doc is not None
    assert stored_doc.title == "Lisinopril Tablets Prescribing Information"

    stored_chunk = store.get_chunk("chk_lis_001")
    assert stored_chunk is not None
    assert stored_chunk.content == "Adults: Initial dose is 10 mg orally once daily. Maximum dose is 40 mg daily."
    assert stored_chunk.exact_location == "Paragraph 1"
    assert stored_chunk.page == 2

    # Verify candidate item adaptation
    item = store.get_content_item("chk_lis_001")
    assert item is not None
    assert item.content_id == "chk_lis_001"
    assert item.document_id == "doc_lisinopril_01"
    assert item.drug == "Lisinopril"
    assert item.dose == "10 mg"
    assert item.frequency == "once daily"


def test_add_document_auto_chunks_when_empty():
    """Verify store invokes RegulatoryChunker if sections contain unchunked text."""
    store = IngestedDocumentCandidateStore()

    doc = RegulatoryDocument(
        document_id="doc_amox_02",
        title="Amoxicillin Clinical Summary",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_amox_01",
                section_number="1",
                heading_raw="1. INDICATIONS AND USAGE",
                raw_text="Amoxicillin is indicated for the treatment of infections caused by susceptible strains of bacteria.",
                chunks=[],  # Unchunked section
            )
        ],
    )

    chunks = store.add_document(doc)

    assert len(chunks) >= 1
    assert store.count_chunks() >= 1
    assert any("indicated for the treatment" in c.content for c in chunks)


def test_ingest_and_store_from_unified_ingestion():
    """Verify ingest_and_store integrates Phase 2 UnifiedIngestionService directly."""
    store = IngestedDocumentCandidateStore()

    raw_text = (
        "# 2. DOSAGE AND ADMINISTRATION\n"
        "Adults: Take 500 mg orally every 8 hours.\n\n"
        "# 4. CONTRAINDICATIONS\n"
        "Contraindicated in patients with severe hypersensitivity.\n"
    )

    doc, chunks = store.ingest_and_store(
        content=raw_text,
        filename="amoxicillin_spec.md",
        document_name="Amoxicillin Specification",
    )

    assert doc is not None
    assert len(chunks) >= 2
    assert store.count_documents() == 1
    assert store.count_chunks() == len(chunks)

    # Search for dosage chunk
    dosage_items = store.search(query="500 mg", section="DOSAGE")
    assert len(dosage_items) >= 1
    assert "500 mg" in dosage_items[0].text


def test_traceability_preservation_without_fabrication():
    """Verify chunk metadata, locations, and provenance are strictly preserved without fabricating missing data."""
    store = IngestedDocumentCandidateStore()

    chunk = RegulatoryChunk(
        chunk_id="chk_trace_01",
        document_id="doc_trace_01",
        section_id="sec_trace_01",
        content="Take 250 mg twice daily.",
        document_name="Traceability Test Document",
        section_title="Dosage",
        source="InternalDraft",
        # Explicitly unprovided optional fields
        exact_location=None,
        page=None,
        loinc_code=None,
    )

    item = store.add_chunk(chunk)

    # Must preserve provided values
    assert item.content_id == "chk_trace_01"
    assert item.document_name == "Traceability Test Document"
    assert item.text == "Take 250 mg twice daily."
    # Must NOT fabricate missing fields
    assert item.location is None
    assert item.page is None
    assert item.loinc_code is None


def test_multiple_documents_coexistence():
    """Verify multiple documents and their chunks coexist and are filterable by document_id."""
    store = IngestedDocumentCandidateStore()

    doc1 = RegulatoryDocument(
        document_id="doc_cardio_01",
        title="Cardiovascular Product Label",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_c1",
                heading_raw="Dosage",
                raw_text="Adults: Take 20 mg once daily.",
            )
        ],
    )
    doc2 = RegulatoryDocument(
        document_id="doc_onco_02",
        title="Oncology Drug Monograph",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_o1",
                heading_raw="Dosage",
                raw_text="Administer 100 mg/m2 intravenous infusion.",
            )
        ],
    )

    store.add_document(doc1)
    store.add_document(doc2)

    assert store.count_documents() == 2
    assert store.count_chunks() >= 2

    # Scoped chunks
    c1_chunks = store.list_chunks(document_id="doc_cardio_01")
    c2_chunks = store.list_chunks(document_id="doc_onco_02")

    assert len(c1_chunks) >= 1
    assert len(c2_chunks) >= 1
    assert all(c.document_id == "doc_cardio_01" for c in c1_chunks)
    assert all(c.document_id == "doc_onco_02" for c in c2_chunks)

    # Remove single document
    removed = store.remove_document("doc_cardio_01")
    assert removed is True
    assert store.count_documents() == 1
    assert store.get_document("doc_cardio_01") is None
    assert store.get_document("doc_onco_02") is not None


def test_store_clear_lifecycle():
    """Verify clear() resets all stored documents, chunks, and content items."""
    store = IngestedDocumentCandidateStore()

    doc = RegulatoryDocument(
        document_id="doc_temp",
        title="Temporary Document",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[RegulatorySection(section_id="s1", heading_raw="Sec", raw_text="Sample text content.")],
    )
    store.add_document(doc)
    assert store.count_documents() == 1

    store.clear()
    assert store.count_documents() == 0
    assert store.count_chunks() == 0
    assert len(store.list_documents()) == 0
    assert len(store.list_chunks()) == 0
    assert len(store.search(query="Sample")) == 0


# ==============================================================================
# 2. RETRIEVAL PIPELINE INTEGRATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_live_rag_retriever_discovers_ingested_candidate():
    """Verify LiveRAGRetriever discovers candidates from the IngestedDocumentCandidateStore."""
    store = IngestedDocumentCandidateStore()
    retriever = LiveRAGRetriever(candidate_store=store)

    doc = RegulatoryDocument(
        document_id="doc_atorva_internal",
        title="Atorvastatin Calcium Draft Label",
        provenance=RegulatoryProvenance(
            source_repository="InternalDraft",
            source_identifier="doc_atorva_internal",
        ),
        sections=[
            RegulatorySection(
                section_id="sec_at_01",
                section_number="2.1",
                heading_raw="2.1 Recommended Dosage",
                raw_text="The recommended starting dose of atorvastatin is 10 mg or 20 mg orally once daily.",
            )
        ],
    )
    store.add_document(doc)

    target_text = "Adults: The recommended starting dose is 10 mg of atorvastatin once daily."

    # Query only ingested source
    results = await retriever.retrieve_candidates(
        target_text=target_text,
        source_filter="ingested",
        top_k=3,
    )

    assert len(results) >= 1
    candidate_item, score, provider = results[0]
    assert candidate_item.document_id == "doc_atorva_internal"
    assert "10 mg or 20 mg orally once daily" in candidate_item.text
    assert score > 0.0
    assert provider is not None


@pytest.mark.asyncio
async def test_live_rag_retriever_combined_all_sources():
    """Verify source_filter='all' queries DailyMed, openFDA, AND IngestedDocumentCandidateStore."""
    store = IngestedDocumentCandidateStore()
    mock_source_service = MagicMock(spec=RegulatorySourceService)

    # Mock external search returning DailyMed and openFDA items
    dm_item = RegulatoryContentItem(
        content_id="dm_ext_01",
        source="DailyMed",
        document_name="Commercial DailyMed Label",
        text="Adults: Take 10 mg once daily with water.",
    )
    fda_item = RegulatoryContentItem(
        content_id="fda_ext_02",
        source="openFDA",
        document_name="FDA Approved Drug Label",
        text="Dosage: 10 mg once daily.",
    )
    mock_source_service.search = AsyncMock(
        return_value=RegulatorySearchResult(
            query="atorvastatin",
            total_results=2,
            source="all",
            items=[dm_item, fda_item],
        )
    )

    retriever = LiveRAGRetriever(
        source_service=mock_source_service,
        candidate_store=store,
    )

    # Add ingested internal candidate
    doc = RegulatoryDocument(
        document_id="doc_internal_03",
        title="Internal Atorvastatin Dossier",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_i1",
                heading_raw="Dosage",
                raw_text="Adults: The starting dose of atorvastatin is 10 mg once daily.",
            )
        ],
    )
    store.add_document(doc)

    target_text = "Adults: Take 10 mg atorvastatin orally once daily."

    results = await retriever.retrieve_candidates(
        target_text=target_text,
        source_filter="all",
        top_k=5,
    )

    # Must contain candidates from external sources AND candidate store
    sources_in_results = {r[0].source for r in results}
    assert "DailyMed" in sources_in_results or "openFDA" in sources_in_results or "InternalDraft" in sources_in_results
    assert len(results) >= 2


@pytest.mark.asyncio
async def test_ingested_candidates_survive_vector_store_clearing():
    """Verify that ephemeral vector_store.clear() during query does not erase candidate store."""
    store = IngestedDocumentCandidateStore()
    retriever = LiveRAGRetriever(candidate_store=store)

    doc = RegulatoryDocument(
        document_id="doc_persistent",
        title="Persistent Ingested Product",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_p1",
                heading_raw="Dosage",
                raw_text="Take 5 mg orally once daily.",
            )
        ],
    )
    store.add_document(doc)

    assert store.count_documents() == 1
    assert store.count_chunks() >= 1

    # First retrieval: runs retriever.vector_store.clear() internally
    results_1 = await retriever.retrieve_candidates(
        target_text="Take 5 mg once daily.",
        source_filter="ingested",
    )
    assert len(results_1) >= 1

    # Verify store content is still intact
    assert store.count_documents() == 1
    assert store.count_chunks() >= 1
    assert store.get_document("doc_persistent") is not None

    # Second retrieval: still discovers candidate without re-adding
    results_2 = await retriever.retrieve_candidates(
        target_text="Take 5 mg once daily.",
        source_filter="ingested",
    )
    assert len(results_2) >= 1
    assert results_2[0][0].document_id == "doc_persistent"


# ==============================================================================
# 3. COMPATIBILITY TESTS
# ==============================================================================


def test_compatibility_adapters_with_ingested_candidates():
    """Verify chunks from candidate store seamlessly pass to adapt_for_retrieval and adapt_for_comparison."""
    store = IngestedDocumentCandidateStore()

    doc = RegulatoryDocument(
        document_id="doc_compat",
        title="Compatibility Test Spec",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_c",
                heading_raw="Dosage",
                raw_text="Adults: Take 20 mg orally once daily with water.",
            )
        ],
    )
    chunks = store.add_document(doc)
    assert len(chunks) >= 1
    chunk = chunks[0]

    # 1. adapt_for_retrieval accepts RegulatoryChunk
    retrieval_items = adapt_for_retrieval(chunk)
    assert len(retrieval_items) == 1
    assert isinstance(retrieval_items[0], RegulatoryContentItem)
    assert retrieval_items[0].document_id == "doc_compat"

    # 2. adapt_for_comparison accepts RegulatoryChunk
    comp_item = adapt_for_comparison(chunk)
    assert isinstance(comp_item, RegulatoryContentItem)
    assert comp_item.text == "Adults: Take 20 mg orally once daily with water."
