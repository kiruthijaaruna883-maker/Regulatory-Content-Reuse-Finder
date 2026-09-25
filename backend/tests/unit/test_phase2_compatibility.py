"""Unit tests for Phase 2 Step 7: Compatibility Adapters.

Validates:
1. RegulatoryDocument compatibility conversion (with chunks, section mode, and dynamic chunk mode)
2. RegulatoryChunk compatibility conversion
3. Metadata preservation
4. Provenance preservation
5. Document identity preservation
6. Section and structure path preservation
7. Source location preservation
8. Table/row/cell context preservation
9. Parent-child relationship preservation
10. Empty and optional fields handling (no fabricated values)
11. Deterministic output
12. Backward compatibility with existing services (VectorStore, ContentMatchingService, MultiDimensionalComparator)
13. Reverse adapters (content_item_to_chunk and content_items_to_document)
"""

import pytest
from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryChunk,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.compatibility import (
    adapt_for_comparison,
    adapt_for_retrieval,
    chunk_to_content_item,
    chunks_to_content_items,
    content_item_to_chunk,
    content_items_to_document,
    document_to_content_items,
    section_to_content_item,
)
from app.services.content_matching import ContentMatchingService
from app.services.multi_dimensional_comparator import MultiDimensionalComparator
from app.services.vector_store import VectorStore


# ============================================================================
# 1. RegulatoryChunk Compatibility Conversion
# ============================================================================

def test_regulatory_chunk_compatibility_conversion():
    """Verify RegulatoryChunk cleanly converts to RegulatoryContentItem preserving all fields."""
    key_info = KeyInformation(
        drug="Metformin",
        dose="500 mg",
        frequency="twice daily",
        route="oral",
        indication="type 2 diabetes mellitus",
        population="adults",
        purpose="glycemic control",
    )
    chunk = RegulatoryChunk(
        chunk_id="chk_test_101",
        document_id="doc_metformin_01",
        section_id="sec_posology_01",
        parent_chunk_id="chk_parent_stem_01",
        chunk_type="paragraph",
        order_index=1,
        structure_path="Glucophage > Dosage and Administration > Adults",
        content="Adults: The starting dose of metformin hydrochloride tablets is 500 mg orally twice a day.",
        normalized_content="[Document: Glucophage]\nAdults: The starting dose of metformin hydrochloride tablets is 500 mg orally twice a day.",
        document_name="Glucophage Prescribing Information",
        document_type="REGULATORY_LABEL",
        jurisdiction="US_FDA",
        product="Glucophage",
        active_ingredient="Metformin Hydrochloride",
        section_title="Dosage and Administration",
        section_number="2.1",
        normalized_section=CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE,
        key_information=key_info,
        source="DailyMed",
        source_identifier="setid-abc-123",
        source_url="https://dailymed.nlm.nih.gov/setid-abc-123",
        version="3.0",
        publication_date="2025-05-10",
        exact_location="Paragraph 1",
        loinc_code="34068-7",
        page=4,
    )

    item = chunk_to_content_item(chunk)

    assert isinstance(item, RegulatoryContentItem)
    assert item.content_id == "chk_test_101"
    assert item.document_id == "doc_metformin_01"
    assert item.document_name == "Glucophage Prescribing Information"
    assert item.source == "DailyMed"
    assert item.source_url == "https://dailymed.nlm.nih.gov/setid-abc-123"
    assert item.source_identifier == "setid-abc-123"
    assert item.version == "3.0"
    assert item.date == "2025-05-10"
    assert item.section == "Dosage and Administration"
    assert item.subsection == "2.1"
    assert item.page == 4
    assert item.location == "Paragraph 1"
    assert item.loinc_code == "34068-7"
    assert item.content_type == "paragraph"
    assert item.product == "Glucophage"
    assert item.drug == "Metformin Hydrochloride"
    assert item.dose == "500 mg"
    assert item.frequency == "twice daily"
    assert item.route == "oral"
    assert item.indication == "type 2 diabetes mellitus"
    assert item.population == "adults"
    assert item.purpose == "glycemic control"
    assert item.text == chunk.content
    assert item.key_information == key_info


def test_chunks_to_content_items_batch():
    """Verify batch chunk adaptation preserves order and cardinalities."""
    chunks = [
        RegulatoryChunk(
            chunk_id=f"chk_batch_{i}",
            document_id="doc_batch",
            section_id="sec_batch",
            chunk_type="paragraph",
            order_index=i,
            content=f"Regulatory statement {i}",
            source="openFDA",
        )
        for i in range(5)
    ]

    items = chunks_to_content_items(chunks)

    assert len(items) == 5
    for i, it in enumerate(items):
        assert it.content_id == f"chk_batch_{i}"
        assert it.text == f"Regulatory statement {i}"
        assert it.source == "openFDA"
        assert it.metadata["order_index"] == i


# ============================================================================
# 2. Metadata Preservation
# ============================================================================

def test_metadata_preservation():
    """Verify full metadata retention inside RegulatoryContentItem.metadata."""
    chunk = RegulatoryChunk(
        chunk_id="chk_meta_01",
        document_id="doc_meta_01",
        section_id="sec_meta_01",
        parent_chunk_id="chk_parent_99",
        chunk_type="bullet",
        order_index=7,
        structure_path="Label > Warnings > Hypersensitivity",
        content="Discontinue immediately if anaphylaxis occurs.",
        normalized_content="[Enriched Context] Discontinue immediately if anaphylaxis occurs.",
        normalized_section=CanonicalSectionConcept.CONCEPT_WARNINGS,
        document_type="CORE_DATA_SHEET",
        jurisdiction="EMA",
        source="InternalDraft",
        exact_location="Bullet 3",
        loinc_code="43685-7",
        page=12,
    )

    item = chunk_to_content_item(chunk)

    meta = item.metadata
    assert meta["chunk_id"] == "chk_meta_01"
    assert meta["section_id"] == "sec_meta_01"
    assert meta["parent_chunk_id"] == "chk_parent_99"
    assert meta["chunk_type"] == "bullet"
    assert meta["structure_path"] == "Label > Warnings > Hypersensitivity"
    assert meta["normalized_content"] == "[Enriched Context] Discontinue immediately if anaphylaxis occurs."
    assert meta["normalized_section"] == CanonicalSectionConcept.CONCEPT_WARNINGS
    assert meta["document_type"] == "CORE_DATA_SHEET"
    assert meta["jurisdiction"] == "EMA"
    assert meta["order_index"] == 7
    assert meta["exact_location"] == "Bullet 3"
    assert meta["loinc_code"] == "43685-7"
    assert meta["page"] == 12


# ============================================================================
# 3. Provenance Preservation
# ============================================================================

def test_provenance_preservation():
    """Verify origin repository, identifiers, URL, and dates remain intact."""
    prov = RegulatoryProvenance(
        source_repository="DailyMed",
        source_identifier="set-987-xyz",
        source_url="https://dailymed.nlm.nih.gov/lookup/set-987-xyz",
        version="4.2",
        publication_date="2026-02-15",
        exact_location="Page 3",
        loinc_code="34068-7",
    )
    doc = RegulatoryDocument(
        document_id="doc_prov_test",
        title="Sample Product Monograph",
        provenance=prov,
        raw_content="Unsegmented raw product monograph text.",
    )

    items = document_to_content_items(doc)

    assert len(items) == 1
    it = items[0]
    assert it.source == "DailyMed"
    assert it.source_identifier == "set-987-xyz"
    assert it.source_url == "https://dailymed.nlm.nih.gov/lookup/set-987-xyz"
    assert it.version == "1.0" or it.version == "4.2"
    assert it.date == "2026-02-15"
    assert it.location == "Page 3"
    assert it.page == 3


# ============================================================================
# 4. Document Identity Preservation
# ============================================================================

def test_document_identity_preservation():
    """Verify document ID, title, product name, active ingredient, and version are preserved."""
    prov = RegulatoryProvenance(source_repository="openFDA", source_identifier="NDA-020999")
    sec = RegulatorySection(
        section_id="sec_id_01",
        heading_raw="1. Indications and Usage",
        raw_text="Indicated for the treatment of essential hypertension.",
    )
    doc = RegulatoryDocument(
        document_id="doc_ident_555",
        title="Cardiopril (Ramipril) Capsules",
        document_type="REGULATORY_LABEL",
        jurisdiction="US_FDA",
        product_name="Cardiopril",
        active_ingredient="Ramipril",
        application_number="NDA 020999",
        manufacturer="Apex Therapeutics",
        version="2.0",
        effective_date="2025-10-01",
        provenance=prov,
        sections=[sec],
    )

    items = document_to_content_items(doc)

    assert len(items) == 1
    it = items[0]
    assert it.document_id == "doc_ident_555"
    assert it.document_name == "Cardiopril (Ramipril) Capsules"
    assert it.product == "Cardiopril"
    assert it.drug == "Ramipril"
    assert it.version == "2.0"
    assert it.date == "2025-10-01"
    assert it.metadata["application_number"] == "NDA 020999"
    assert it.metadata["manufacturer"] == "Apex Therapeutics"


# ============================================================================
# 5. Section & Structure Path Preservation
# ============================================================================

def test_section_and_structure_path_preservation():
    """Verify hierarchical outlines (parent section -> child subsection) preserve structure paths."""
    sub_sec = RegulatorySection(
        section_id="sec_4_2",
        parent_section_id="sec_4",
        section_number="4.2",
        heading_raw="4.2 Posology and method of administration",
        raw_text="The recommended initial dosage is 2.5 mg once daily.",
        order_index=1,
    )
    parent_sec = RegulatorySection(
        section_id="sec_4",
        section_number="4",
        heading_raw="4. Clinical Particulars",
        raw_text="General clinical particulars summary.",
        order_index=0,
        subsections=[sub_sec],
    )
    doc = RegulatoryDocument(
        document_id="doc_path_test",
        title="Ramipril SmPC",
        provenance=RegulatoryProvenance(source_repository="EMA"),
        sections=[parent_sec],
    )

    items = document_to_content_items(doc)

    assert len(items) == 2
    parent_item = next(it for it in items if it.content_id == "sec_4")
    child_item = next(it for it in items if it.content_id == "sec_4_2")

    assert parent_item.section == "4. Clinical Particulars"
    assert parent_item.subsection == "4"
    assert parent_item.metadata["structure_path"] == "Ramipril SmPC > 4. Clinical Particulars"

    assert child_item.section == "4.2 Posology and method of administration"
    assert child_item.subsection == "4.2"
    assert child_item.metadata["parent_section_id"] == "sec_4"
    assert "4. Clinical Particulars > 4.2 Posology and method of administration" in child_item.metadata["structure_path"]


# ============================================================================
# 6. Source Location Preservation
# ============================================================================

def test_source_location_preservation():
    """Verify exact locations such as paragraphs, tables, or page descriptions are preserved."""
    chunk = RegulatoryChunk(
        chunk_id="chk_loc_01",
        document_id="doc_loc",
        section_id="sec_loc",
        content="Store below 25 deg C.",
        exact_location="Paragraph 4, Line 2",
        source="InternalDraft",
    )

    item = chunk_to_content_item(chunk)

    assert item.location == "Paragraph 4, Line 2"
    assert item.metadata["exact_location"] == "Paragraph 4, Line 2"


# ============================================================================
# 7. Table / Row / Cell Context Preservation
# ============================================================================

def test_table_row_cell_context_preservation():
    """Verify structured table row chunks preserve table title, row index, and location context."""
    chunk = RegulatoryChunk(
        chunk_id="chk_tbl_row_01",
        document_id="doc_tbl",
        section_id="sec_dos_adj",
        chunk_type="table_row",
        order_index=3,
        structure_path="Dossier > Section 2 > Table 1: Dosage Adjustments > Row 2",
        content="| CrCl < 30 mL/min | 25 mg once daily | 50 mg max |",
        exact_location="Table 1: Dosage Adjustments, Row 2",
        source="DailyMed",
    )

    item = chunk_to_content_item(chunk)

    assert item.content_type == "table_row"
    assert item.location == "Table 1: Dosage Adjustments, Row 2"
    assert item.metadata["table_title"] == "Table 1: Dosage Adjustments"
    assert item.metadata["row_index"] == 2
    assert "Table 1: Dosage Adjustments > Row 2" in item.metadata["structure_path"]


# ============================================================================
# 8. Parent-Child Relationship Preservation
# ============================================================================

def test_parent_child_relationship_preservation():
    """Verify bullet items maintain their parent stem relationship in metadata."""
    stem_chunk = RegulatoryChunk(
        chunk_id="chk_stem_01",
        document_id="doc_bullet",
        section_id="sec_warn",
        chunk_type="paragraph",
        content="Do not administer in the following patient groups:",
        exact_location="Paragraph (Stem)",
        source="InternalDraft",
    )
    bullet_chunk = RegulatoryChunk(
        chunk_id="chk_bullet_01",
        document_id="doc_bullet",
        section_id="sec_warn",
        parent_chunk_id="chk_stem_01",
        chunk_type="bullet",
        content="Patients with severe hepatic impairment.",
        exact_location="List Item *",
        structure_path="Dossier > Warnings > Item *",
        source="InternalDraft",
    )

    stem_item = chunk_to_content_item(stem_chunk)
    bullet_item = chunk_to_content_item(bullet_chunk)

    assert stem_item.metadata["parent_chunk_id"] is None
    assert bullet_item.metadata["parent_chunk_id"] == "chk_stem_01"
    assert bullet_item.content_type == "bullet"


# ============================================================================
# 9. Empty and Optional Fields (No Fabricated Values)
# ============================================================================

def test_empty_and_optional_fields_handling():
    """Verify adapter does NOT fabricate missing values when optional fields are None."""
    minimal_chunk = RegulatoryChunk(
        chunk_id="chk_min_01",
        document_id="doc_min",
        section_id="sec_min",
        content="A concise regulatory statement.",
        source="InternalDraft",
    )

    item = chunk_to_content_item(minimal_chunk)

    # Core non-empty attributes
    assert item.content_id == "chk_min_01"
    assert item.document_id == "doc_min"
    assert item.text == "A concise regulatory statement."
    assert item.source == "InternalDraft"

    # All optional fields must be None, NOT fabricated defaults
    assert item.document_name is None
    assert item.source_url is None
    assert item.source_identifier is None
    assert item.version is None
    assert item.date is None
    assert item.section is None
    assert item.subsection is None
    assert item.location is None
    assert item.loinc_code is None
    assert item.page is None
    assert item.product is None
    assert item.drug is None
    assert item.dose is None
    assert item.frequency is None
    assert item.route is None
    assert item.indication is None
    assert item.population is None
    assert item.purpose is None
    assert item.key_information is None


# ============================================================================
# 10. Deterministic Output
# ============================================================================

def test_deterministic_output():
    """Verify repeated adaptation of the same chunk produces identical outputs."""
    chunk = RegulatoryChunk(
        chunk_id="chk_det_01",
        document_id="doc_det",
        section_id="sec_det",
        order_index=4,
        structure_path="Path > To > Content",
        content="Stable regulatory text.",
        source="DailyMed",
        version="1.0",
        publication_date="2026-01-01",
    )

    item1 = chunk_to_content_item(chunk)
    item2 = chunk_to_content_item(chunk)

    assert item1.model_dump() == item2.model_dump()


# ============================================================================
# 11. RegulatoryDocument Conversion Modes
# ============================================================================

def test_regulatory_document_conversion_with_prechunked_sections():
    """Verify document_to_content_items extracts pre-existing chunks across sections."""
    c1 = RegulatoryChunk(
        chunk_id="chk_pre_1",
        document_id="doc_pre",
        section_id="sec_pre_1",
        content="Paragraph 1 text.",
        source="DailyMed",
    )
    c2 = RegulatoryChunk(
        chunk_id="chk_pre_2",
        document_id="doc_pre",
        section_id="sec_pre_2",
        content="Paragraph 2 text.",
        source="DailyMed",
    )
    sec1 = RegulatorySection(
        section_id="sec_pre_1",
        heading_raw="Section 1",
        order_index=0,
        chunks=[c1],
    )
    sec2 = RegulatorySection(
        section_id="sec_pre_2",
        heading_raw="Section 2",
        order_index=1,
        chunks=[c2],
    )
    doc = RegulatoryDocument(
        document_id="doc_pre",
        title="Pre-chunked Document",
        provenance=RegulatoryProvenance(source_repository="DailyMed"),
        sections=[sec1, sec2],
    )

    items = document_to_content_items(doc)

    assert len(items) == 2
    assert items[0].content_id == "chk_pre_1"
    assert items[1].content_id == "chk_pre_2"


def test_regulatory_document_conversion_chunk_if_empty_true():
    """Verify document_to_content_items dynamically chunks when chunk_if_empty=True."""
    sec = RegulatorySection(
        section_id="sec_raw_01",
        heading_raw="DOSAGE AND ADMINISTRATION",
        raw_text="Adults: Take 100 mg orally once daily in the morning.\n\nPediatric patients: Safety and efficacy have not been established.",
    )
    doc = RegulatoryDocument(
        document_id="doc_dyn_01",
        title="Dynamic Chunking Monograph",
        provenance=RegulatoryProvenance(source_repository="openFDA"),
        sections=[sec],
    )

    items = document_to_content_items(doc, chunk_if_empty=True)

    assert len(items) >= 2
    assert any("100 mg orally" in it.text for it in items)
    assert any("Pediatric patients" in it.text for it in items)


def test_section_to_content_item_standalone():
    """Verify standalone section_to_content_item with and without document context."""
    sec = RegulatorySection(
        section_id="sec_stand_01",
        section_number="2.1",
        heading_raw="2.1 Adult Patients",
        heading_normalized=CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE,
        order_index=0,
        loinc_code="34068-7",
        raw_text="The recommended dose is 10 mg daily.",
    )

    item = section_to_content_item(sec)

    assert item.content_id == "sec_stand_01"
    assert item.section == "2.1 Adult Patients"
    assert item.subsection == "2.1"
    assert item.text == "The recommended dose is 10 mg daily."
    assert item.loinc_code == "34068-7"
    assert item.content_type == "regulatory_section"
    assert item.metadata["heading_normalized"] == CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE


# ============================================================================
# 12. Reverse Adapters
# ============================================================================

def test_reverse_adapter_content_item_to_chunk():
    """Verify content_item_to_chunk maps RegulatoryContentItem back to RegulatoryChunk."""
    key_info = KeyInformation(dose="20 mg", route="oral")
    item = RegulatoryContentItem(
        content_id="rc_rev_01",
        document_id="doc_rev_01",
        document_name="Lisinopril Tablets",
        source="DailyMed",
        source_url="https://dailymed.nlm.nih.gov/lisinopril",
        source_identifier="set-lis-01",
        version="1.5",
        date="2025-08-20",
        section="Dosage and Administration",
        subsection="2.2",
        page=3,
        location="Paragraph 2",
        loinc_code="34068-7",
        content_type="paragraph",
        product="Prinivil",
        drug="Lisinopril",
        dose="20 mg",
        route="oral",
        text="Adults: Initial dose is 10 mg once daily, titrating to 20 mg once daily.",
        key_information=key_info,
        metadata={
            "section_id": "sec_lis_02",
            "parent_chunk_id": "chk_parent_1",
            "structure_path": "Lisinopril Tablets > Dosage and Administration > Paragraph 2",
            "jurisdiction": "US_FDA",
            "document_type": "REGULATORY_LABEL",
            "order_index": 2,
        },
    )

    chunk = content_item_to_chunk(item)

    assert isinstance(chunk, RegulatoryChunk)
    assert chunk.chunk_id == "rc_rev_01"
    assert chunk.document_id == "doc_rev_01"
    assert chunk.section_id == "sec_lis_02"
    assert chunk.parent_chunk_id == "chk_parent_1"
    assert chunk.document_name == "Lisinopril Tablets"
    assert chunk.section_title == "Dosage and Administration"
    assert chunk.section_number == "2.2"
    assert chunk.exact_location == "Paragraph 2"
    assert chunk.loinc_code == "34068-7"
    assert chunk.page == 3
    assert chunk.content == item.text
    assert chunk.key_information == key_info
    assert chunk.product == "Prinivil"
    assert chunk.active_ingredient == "Lisinopril"
    assert chunk.source == "DailyMed"
    assert chunk.source_identifier == "set-lis-01"
    assert chunk.source_url == "https://dailymed.nlm.nih.gov/lisinopril"
    assert chunk.version == "1.5"
    assert chunk.publication_date == "2025-08-20"


def test_reverse_adapter_content_items_to_document():
    """Verify content_items_to_document groups items into sections and builds RegulatoryDocument."""
    items = [
        RegulatoryContentItem(
            content_id="rc_d1",
            document_id="doc_grp_01",
            document_name="Amlodipine Tablets",
            source="openFDA",
            section="Indications and Usage",
            subsection="1.1",
            text="Hypertension: indicated for the treatment of hypertension.",
        ),
        RegulatoryContentItem(
            content_id="rc_d2",
            document_id="doc_grp_01",
            document_name="Amlodipine Tablets",
            source="openFDA",
            section="Indications and Usage",
            subsection="1.2",
            text="Coronary Artery Disease: indicated for chronic stable angina.",
        ),
        RegulatoryContentItem(
            content_id="rc_d3",
            document_id="doc_grp_01",
            document_name="Amlodipine Tablets",
            source="openFDA",
            section="Dosage and Administration",
            subsection="2.1",
            text="Usual starting dose is 5 mg once daily.",
        ),
    ]

    doc = content_items_to_document(items, document_id="doc_grp_01", title="Amlodipine Label")

    assert isinstance(doc, RegulatoryDocument)
    assert doc.document_id == "doc_grp_01"
    assert doc.title == "Amlodipine Label"
    assert doc.provenance.source_repository == "openFDA"
    assert len(doc.sections) == 2

    sec1 = doc.sections[0]
    assert sec1.heading_raw == "Indications and Usage"
    assert len(sec1.chunks) == 2
    assert sec1.chunks[0].chunk_id == "rc_d1"
    assert sec1.chunks[1].chunk_id == "rc_d2"

    sec2 = doc.sections[1]
    assert sec2.heading_raw == "Dosage and Administration"
    assert len(sec2.chunks) == 1
    assert sec2.chunks[0].chunk_id == "rc_d3"


# ============================================================================
# 13. Backward Compatibility with Existing Services
# ============================================================================

def test_backward_compatibility_with_vector_store():
    """Verify VectorStore.add_items directly indexes RegulatoryChunks and RegulatoryDocuments."""
    store = VectorStore()
    chunk1 = RegulatoryChunk(
        chunk_id="chk_vec_01",
        document_id="doc_vec",
        section_id="sec_vec",
        content="Adults: Take 500 mg orally once daily with meals.",
        source="DailyMed",
    )
    chunk2 = RegulatoryChunk(
        chunk_id="chk_vec_02",
        document_id="doc_vec",
        section_id="sec_vec",
        content="Contraindicated in patients with severe renal impairment.",
        source="DailyMed",
    )

    # 1. Add chunks directly to VectorStore
    store.add_items([chunk1, chunk2])

    assert len(store._index) == 2

    # 2. Search index
    results = store.search(query="500 mg daily meals", top_k=2)
    assert len(results) >= 1
    matched_item, score, provider = results[0]
    assert isinstance(matched_item, RegulatoryContentItem)
    assert matched_item.content_id == "chk_vec_01"
    assert score > 0.0

    # 3. Add RegulatoryDocument directly
    doc = RegulatoryDocument(
        document_id="doc_vec_add",
        title="Added Document",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_added",
                heading_raw="Clinical Pharmacology",
                raw_text="The absolute bioavailability of the tablet is approximately 70 percent.",
            )
        ],
    )
    store.add_items(doc)
    assert len(store._index) == 3


def test_backward_compatibility_with_content_matching():
    """Verify ContentMatchingService.rank_candidates directly accepts RegulatoryChunks."""
    matcher = ContentMatchingService()
    target_text = "Adults: 50 mg orally once daily for hypertension."

    chunks = [
        RegulatoryChunk(
            chunk_id="chk_cand_01",
            document_id="doc_m1",
            section_id="sec_m1",
            document_name="Losartan Prescribing Info",
            section_title="Dosage and Administration",
            content="Adults: Initial dose is 50 mg orally once daily for hypertension.",
            source="DailyMed",
        ),
        RegulatoryChunk(
            chunk_id="chk_cand_02",
            document_id="doc_m2",
            section_id="sec_m2",
            document_name="Other Medication",
            section_title="Storage and Handling",
            content="Store at room temperature 20 to 25 degrees Celsius.",
            source="openFDA",
        ),
    ]

    candidates = matcher.rank_candidates(target_text=target_text, candidates=chunks, min_threshold=0.01)

    assert len(candidates) >= 1
    top = candidates[0]
    assert top.content_item.content_id == "chk_cand_01"
    assert top.similarity_score > 0.5
    assert top.evidence[0].source == "DailyMed"
    assert top.evidence[0].document_name == "Losartan Prescribing Info"


def test_backward_compatibility_with_multi_dimensional_comparator():
    """Verify MultiDimensionalComparator.compare directly accepts a RegulatoryChunk candidate."""
    comparator = MultiDimensionalComparator()
    target_text = "Adults: The starting dose is 10 mg orally once daily."

    candidate_chunk = RegulatoryChunk(
        chunk_id="chk_comp_01",
        document_id="doc_c1",
        section_id="sec_c1",
        document_name="Ramipril Label",
        section_title="Dosage and Administration",
        content="Adults: The starting dose is 10 mg orally once daily.",
        source="DailyMed",
        key_information=KeyInformation(
            dose="10 mg",
            frequency="once daily",
            route="oral",
            population="Adults",
        ),
    )

    match, diffs, evidence, false_match = comparator.compare(
        target_text=target_text,
        candidate=candidate_chunk,
    )

    assert match is not None
    assert evidence.observed_from_source.source == "DailyMed"
    assert evidence.observed_from_source.document_name == "Ramipril Label"
    assert evidence.observed_from_source.extracted_dose == "10 mg"
