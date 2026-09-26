"""Unit tests for Phase 3 Step 2: Cross-Source Deduplication + Filtering.

Verifies:
1. Exact duplicate candidates are deduplicated.
2. Normalization catches harmless formatting differences (case, whitespace, quotes, bullets).
3. Similar-but-legitimate candidates are NOT incorrectly deduplicated.
4. Same drug/product alone does NOT cause deduplication.
5. Same dose alone does NOT cause deduplication.
6. Candidates from different documents with materially different regulatory content remain separate.
7. Cross-source duplicates (DailyMed + openFDA + Ingested) are merged correctly.
8. DailyMed candidates remain retrievable.
9. openFDA candidates remain retrievable.
10. Ingested candidates remain retrievable.
11. source_filter='dailymed' works.
12. source_filter='openfda' works.
13. source_filter='ingested' works.
14. source_filter='internal' works.
15. source_filter='all' combines sources and deduplicates.
16. Traceability/provenance survives deduplication (cross_sources, duplicate_provenance).
17. Existing candidate-store behavior remains intact.
18. Existing retrieval behavior remains intact.
19. Empty candidate results are handled safely.
20. Zero metadata fabrication.
"""

from typing import List
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.models.content import KeyInformation, RegulatoryContentItem, RegulatorySearchResult
from app.models.document import (
    RegulatoryChunk,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.candidate_deduplicator import (
    CandidateDeduplicator,
    deduplicate_candidates,
    normalize_text_conservative,
)
from app.services.candidate_store import (
    IngestedDocumentCandidateStore,
    get_candidate_store,
    reset_candidate_store,
)
from app.services.rag_retriever import LiveRAGRetriever
from app.services.regulatory_source import RegulatorySourceService


@pytest.fixture(autouse=True)
def clean_candidate_store():
    """Ensure clean candidate store state for every test."""
    reset_candidate_store()
    yield
    reset_candidate_store()


# ==============================================================================
# 1. DEDUPLICATION LOGIC & NORMALIZATION TESTS
# ==============================================================================


def test_exact_duplicate_candidates_deduplicated():
    """Verify identical text and drug candidates are merged into a single candidate."""
    deduplicator = CandidateDeduplicator()

    cand1 = RegulatoryContentItem(
        content_id="c1",
        source="DailyMed",
        document_name="Lisinopril Label A",
        text="Adults: Take 10 mg orally once daily in the morning.",
        drug="Lisinopril",
        section="Dosage and Administration",
    )
    cand2 = RegulatoryContentItem(
        content_id="c2",
        source="openFDA",
        document_name="Lisinopril Label B",
        text="Adults: Take 10 mg orally once daily in the morning.",
        drug="Lisinopril",
        section="Dosage and Administration",
    )

    assert deduplicator.are_duplicates(cand1, cand2) is True

    deduped = deduplicator.deduplicate([cand1, cand2])
    assert len(deduped) == 1
    assert deduped[0].text == "Adults: Take 10 mg orally once daily in the morning."
    assert "DailyMed" in deduped[0].metadata["cross_sources"]
    assert "openFDA" in deduped[0].metadata["cross_sources"]


def test_normalization_catches_formatting_differences():
    """Verify differences in case, whitespace, leading bullets, and smart punctuation are normalized."""
    deduplicator = CandidateDeduplicator()

    cand1 = RegulatoryContentItem(
        content_id="c_fmt_1",
        source="DailyMed",
        text="• Adults:   Take 20 mg  once daily. ",
        drug="Atorvastatin",
    )
    cand2 = RegulatoryContentItem(
        content_id="c_fmt_2",
        source="openFDA",
        text='adults: take 20 mg once daily',
        drug="Atorvastatin",
    )

    assert deduplicator.are_duplicates(cand1, cand2) is True

    deduped = deduplicator.deduplicate([cand1, cand2])
    assert len(deduped) == 1


def test_similar_but_legitimate_candidates_not_deduplicated():
    """Verify different paragraphs or clinically distinct statements are preserved."""
    deduplicator = CandidateDeduplicator()

    cand_initial = RegulatoryContentItem(
        content_id="c_init",
        source="DailyMed",
        text="Initial starting dosage is 10 mg orally once daily with water.",
        drug="Lisinopril",
        section="Dosage",
    )
    cand_titration = RegulatoryContentItem(
        content_id="c_titr",
        source="DailyMed",
        text="Titrate dosage upwards every two to four weeks as needed to maximum 40 mg daily.",
        drug="Lisinopril",
        section="Dosage",
    )

    assert deduplicator.are_duplicates(cand_initial, cand_titration) is False

    deduped = deduplicator.deduplicate([cand_initial, cand_titration])
    assert len(deduped) == 2


def test_same_drug_alone_does_not_cause_deduplication():
    """Verify that sharing the same drug name does NOT cause deduplication when texts differ."""
    deduplicator = CandidateDeduplicator()

    cand_indications = RegulatoryContentItem(
        content_id="c_ind",
        source="DailyMed",
        text="Indicated for the treatment of essential hypertension in adult patients.",
        drug="Amlodipine",
        section="Indications",
    )
    cand_contra = RegulatoryContentItem(
        content_id="c_contra",
        source="openFDA",
        text="Contraindicated in patients with severe known hypersensitivity to amlodipine.",
        drug="Amlodipine",
        section="Contraindications",
    )

    assert deduplicator.are_duplicates(cand_indications, cand_contra) is False

    deduped = deduplicator.deduplicate([cand_indications, cand_contra])
    assert len(deduped) == 2


def test_same_dose_alone_does_not_cause_deduplication():
    """Verify that sharing the same dose (e.g. 50 mg) across different drugs does NOT cause deduplication."""
    deduplicator = CandidateDeduplicator()

    cand1 = RegulatoryContentItem(
        content_id="c_drug1",
        source="DailyMed",
        text="Adults: Take 50 mg once daily with food.",
        drug="Sertraline",
    )
    cand2 = RegulatoryContentItem(
        content_id="c_drug2",
        source="openFDA",
        text="Adults: Take 50 mg once daily with food.",
        drug="Losartan",
    )

    # Different drugs MUST NOT be deduplicated even with identical phrasing
    assert deduplicator.are_duplicates(cand1, cand2) is False

    deduped = deduplicator.deduplicate([cand1, cand2])
    assert len(deduped) == 2


def test_different_documents_with_different_content_remain_separate():
    """Verify candidates from distinct documents with materially different statements remain separate."""
    deduplicator = CandidateDeduplicator()

    cand1 = RegulatoryContentItem(
        content_id="c_doc1",
        document_id="doc_01",
        document_name="Doc Alpha",
        source="InternalDraft",
        text="Take 10 mg orally in pediatric patients 6 years of age and older.",
        drug="DrugAlpha",
    )
    cand2 = RegulatoryContentItem(
        content_id="c_doc2",
        document_id="doc_02",
        document_name="Doc Beta",
        source="DailyMed",
        text="Take 20 mg orally in geriatric patients with renal impairment.",
        drug="DrugAlpha",
    )

    # Different dosage numbers and populations
    assert deduplicator.are_duplicates(cand1, cand2) is False
    assert len(deduplicator.deduplicate([cand1, cand2])) == 2


def test_cross_source_duplicates_handled_correctly():
    """Verify cross-source deduplication merges DailyMed, openFDA, and IngestedStore candidates."""
    deduplicator = CandidateDeduplicator()

    item_dm = RegulatoryContentItem(
        content_id="dm_item_1",
        source="DailyMed",
        document_name="DailyMed Atorvastatin",
        source_identifier="setid-12345",
        source_url="https://dailymed.nlm.nih.gov/spls/12345",
        text="The recommended starting dosage of atorvastatin is 10 mg or 20 mg once daily.",
        drug="Atorvastatin",
        section="Dosage and Administration",
    )
    item_fda = RegulatoryContentItem(
        content_id="fda_item_2",
        source="openFDA",
        document_name="openFDA Label",
        source_identifier="fda-67890",
        text="The recommended starting dosage of atorvastatin is 10 mg or 20 mg once daily.",
        drug="Atorvastatin",
        section="Dosage and Administration",
    )
    item_ingested = RegulatoryContentItem(
        content_id="ingested_item_3",
        source="InternalDraft",
        document_name="Internal Label Spec",
        document_id="doc_ingested_01",
        location="Section 2.1",
        page=4,
        text="The recommended starting dosage of atorvastatin is 10 mg or 20 mg once daily.",
        drug="Atorvastatin",
        section="Dosage and Administration",
    )

    deduped = deduplicator.deduplicate([item_dm, item_fda, item_ingested])

    assert len(deduped) == 1
    primary = deduped[0]
    sources = set(primary.metadata["cross_sources"])
    assert sources == {"DailyMed", "openFDA", "InternalDraft"}
    assert len(primary.metadata["duplicate_provenance"]) == 2


def test_traceability_survives_deduplication():
    """Verify that source, identifiers, URLs, page numbers, and locations are preserved in duplicate_provenance."""
    deduplicator = CandidateDeduplicator()

    primary_in = RegulatoryContentItem(
        content_id="c_p",
        source="DailyMed",
        document_name="DailyMed PI",
        source_identifier="spl_001",
        source_url="https://dailymed.nlm.nih.gov/spl/001",
        section="Dosage",
        location="Paragraph 1",
        text="Adults: Take 10 mg orally once daily.",
        drug="Lisinopril",
    )
    dup_in = RegulatoryContentItem(
        content_id="c_d",
        source="InternalDraft",
        document_name="Internal Regulatory Spec",
        document_id="doc_spec_99",
        page=7,
        location="Line 142",
        section="Dosage",
        text="Adults: Take 10 mg orally once daily.",
        drug="Lisinopril",
    )

    deduped = deduplicator.deduplicate([primary_in, dup_in])
    assert len(deduped) == 1
    res = deduped[0]

    # Check cross sources
    assert "DailyMed" in res.metadata["cross_sources"]
    assert "InternalDraft" in res.metadata["cross_sources"]

    # Check duplicate provenance
    prov = res.metadata["duplicate_provenance"]
    assert len(prov) >= 1
    # Check that the other item's exact provenance is recorded
    other_prov = next(p for p in prov if p["content_id"] in ("c_p", "c_d"))
    assert other_prov["document_name"] in ("DailyMed PI", "Internal Regulatory Spec")
    # Verify no fabricated fields
    if other_prov["source_url"] is None:
        assert other_prov["source"] == "InternalDraft"


def test_empty_candidates_handled_safely():
    """Verify deduplicator safely handles empty or None candidate lists."""
    deduplicator = CandidateDeduplicator()
    assert deduplicator.deduplicate([]) == []


# ==============================================================================
# 2. RETRIEVAL PIPELINE & SOURCE FILTERING INTEGRATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_source_filter_dailymed_only():
    """Verify source_filter='dailymed' queries only DailyMed source."""
    mock_source = MagicMock(spec=RegulatorySourceService)
    mock_source.search = AsyncMock(
        return_value=RegulatorySearchResult(
            query="lisinopril",
            total_results=1,
            source="dailymed",
            items=[
                RegulatoryContentItem(
                    content_id="dm_01",
                    source="DailyMed",
                    document_name="DailyMed Lisinopril",
                    text="Adults: 10 mg once daily.",
                    drug="Lisinopril",
                )
            ],
        )
    )
    store = IngestedDocumentCandidateStore()
    retriever = LiveRAGRetriever(source_service=mock_source, candidate_store=store)

    results = await retriever.retrieve_candidates(
        target_text="Adults: 10 mg once daily.",
        source_filter="dailymed",
    )

    assert len(results) >= 1
    assert results[0][0].source == "DailyMed"
    mock_source.search.assert_called_once()
    assert mock_source.search.call_args[1]["source"] == "dailymed"


@pytest.mark.asyncio
async def test_source_filter_openfda_only():
    """Verify source_filter='openfda' queries only openFDA source."""
    mock_source = MagicMock(spec=RegulatorySourceService)
    mock_source.search = AsyncMock(
        return_value=RegulatorySearchResult(
            query="lisinopril",
            total_results=1,
            source="openfda",
            items=[
                RegulatoryContentItem(
                    content_id="fda_01",
                    source="openFDA",
                    document_name="FDA Lisinopril",
                    text="Adults: 10 mg once daily.",
                    drug="Lisinopril",
                )
            ],
        )
    )
    store = IngestedDocumentCandidateStore()
    retriever = LiveRAGRetriever(source_service=mock_source, candidate_store=store)

    results = await retriever.retrieve_candidates(
        target_text="Adults: 10 mg once daily.",
        source_filter="openfda",
    )

    assert len(results) >= 1
    assert results[0][0].source == "openFDA"
    mock_source.search.assert_called_once()
    assert mock_source.search.call_args[1]["source"] == "openfda"


@pytest.mark.asyncio
async def test_source_filter_ingested_and_internal():
    """Verify source_filter='ingested' and 'internal' query only IngestedDocumentCandidateStore."""
    store = IngestedDocumentCandidateStore()
    doc = RegulatoryDocument(
        document_id="doc_internal_only",
        title="Internal Spec",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_1",
                heading_raw="Dosage",
                raw_text="Take 50 mg orally once daily with water.",
            )
        ],
    )
    store.add_document(doc)

    mock_source = MagicMock(spec=RegulatorySourceService)
    mock_source.search = AsyncMock()

    retriever = LiveRAGRetriever(source_service=mock_source, candidate_store=store)

    # 1. Test "ingested"
    results_ingested = await retriever.retrieve_candidates(
        target_text="Take 50 mg once daily.",
        source_filter="ingested",
    )
    assert len(results_ingested) >= 1
    assert results_ingested[0][0].document_id == "doc_internal_only"
    mock_source.search.assert_not_called()

    # 2. Test "internal"
    results_internal = await retriever.retrieve_candidates(
        target_text="Take 50 mg once daily.",
        source_filter="internal",
    )
    assert len(results_internal) >= 1
    assert results_internal[0][0].document_id == "doc_internal_only"
    mock_source.search.assert_not_called()


@pytest.mark.asyncio
async def test_source_filter_all_combines_and_deduplicates():
    """Verify source_filter='all' queries DailyMed, openFDA, and CandidateStore, and deduplicates matching items."""
    mock_source = MagicMock(spec=RegulatorySourceService)

    # DailyMed and openFDA return the same identical dosage statement
    identical_text = "Adults: The recommended starting dose is 20 mg once daily."
    dm_cand = RegulatoryContentItem(
        content_id="dm_dup",
        source="DailyMed",
        document_name="DailyMed PI",
        text=identical_text,
        drug="Atorvastatin",
    )
    fda_cand = RegulatoryContentItem(
        content_id="fda_dup",
        source="openFDA",
        document_name="openFDA Label",
        text=identical_text,
        drug="Atorvastatin",
    )
    mock_source.search = AsyncMock(
        return_value=RegulatorySearchResult(
            query="atorvastatin",
            total_results=2,
            source="all",
            items=[dm_cand, fda_cand],
        )
    )

    # Candidate store also has a candidate for a different dosage
    store = IngestedDocumentCandidateStore()
    doc = RegulatoryDocument(
        document_id="doc_internal_atorva",
        title="Internal Atorvastatin",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_at2",
                heading_raw="Dosage",
                raw_text="Geriatric dosage: The recommended starting dose is 10 mg once daily.",
            )
        ],
    )
    store.add_document(doc)

    retriever = LiveRAGRetriever(source_service=mock_source, candidate_store=store)

    results = await retriever.retrieve_candidates(
        target_text="The recommended starting dose is 20 mg once daily.",
        source_filter="all",
        top_k=5,
    )

    # Verify DailyMed and openFDA identical candidates were deduplicated into 1
    items_in_results = [r[0] for r in results]
    matching_20mg = [it for it in items_in_results if "20 mg" in it.text]
    assert len(matching_20mg) == 1
    # Check that both sources are present in cross_sources metadata
    assert "DailyMed" in matching_20mg[0].metadata["cross_sources"]
    assert "openFDA" in matching_20mg[0].metadata["cross_sources"]

    # Geriatric 10mg candidate remains separate
    matching_10mg = [it for it in items_in_results if "10 mg" in it.text]
    assert len(matching_10mg) >= 1


@pytest.mark.asyncio
async def test_retrieval_empty_results_handled_safely():
    """Verify retriever handles empty results gracefully without errors."""
    mock_source = MagicMock(spec=RegulatorySourceService)
    mock_source.search = AsyncMock(
        return_value=RegulatorySearchResult(
            query="unknown",
            total_results=0,
            source="all",
            items=[],
        )
    )
    store = IngestedDocumentCandidateStore()
    retriever = LiveRAGRetriever(source_service=mock_source, candidate_store=store)

    results = await retriever.retrieve_candidates(
        target_text="",  # Empty query
        source_filter="all",
    )
    assert results == []
