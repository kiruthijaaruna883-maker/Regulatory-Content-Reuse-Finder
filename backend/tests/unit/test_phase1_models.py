"""Unit tests for Phase 1 Regulatory Foundation Models and Data Contracts.

Validates:
- RegulatoryProvenance
- RegulatoryDocument
- RegulatorySection (hierarchy & recursion)
- RegulatoryChunk (content integrity, chunk types, normalized_content)
- RegulatoryTable & RegulatoryTableRow
- RegulatoryChunk.to_content_item() backward-compatibility adapter
- CanonicalSectionConcept registry
"""

import pytest
from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryChunk,
    RegulatoryChunkType,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
    RegulatoryTable,
    RegulatoryTableRow,
)


def test_provenance_creation_and_utc_timestamp():
    """Verify RegulatoryProvenance creation, optional fields, and UTC timestamp."""
    provenance = RegulatoryProvenance(
        source_repository="DailyMed",
        source_identifier="set-id-12345",
        source_url="https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=set-id-12345",
        version="3",
        publication_date="2026-03-01",
        loinc_code="34068-7",
        exact_location="Section 2, Paragraph 1",
    )

    assert provenance.source_repository == "DailyMed"
    assert provenance.source_identifier == "set-id-12345"
    assert provenance.source_url == "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=set-id-12345"
    assert provenance.version == "3"
    assert provenance.publication_date == "2026-03-01"
    assert provenance.loinc_code == "34068-7"
    assert provenance.exact_location == "Section 2, Paragraph 1"
    assert provenance.retrieval_timestamp is not None
    assert "T" in provenance.retrieval_timestamp  # ISO format


def test_document_creation_administrative_identity():
    """Verify RegulatoryDocument holds administrative metadata and provenance."""
    prov = RegulatoryProvenance(
        source_repository="openFDA",
        source_identifier="nda-021000",
    )
    doc = RegulatoryDocument(
        document_id="doc_test_001",
        title="Cardivex (Carvedilol) Tablets Prescribing Information",
        document_type="REGULATORY_LABEL",
        jurisdiction="US_FDA",
        product_name="Cardivex",
        active_ingredient="Carvedilol",
        application_number="NDA 021000",
        manufacturer="Acme Pharma LLC",
        version="2.1",
        effective_date="2025-11-15",
        provenance=prov,
    )

    assert doc.document_id == "doc_test_001"
    assert doc.title == "Cardivex (Carvedilol) Tablets Prescribing Information"
    assert doc.document_type == "REGULATORY_LABEL"
    assert doc.jurisdiction == "US_FDA"
    assert doc.product_name == "Cardivex"
    assert doc.active_ingredient == "Carvedilol"
    assert doc.application_number == "NDA 021000"
    assert doc.manufacturer == "Acme Pharma LLC"
    assert doc.version == "2.1"
    assert doc.effective_date == "2025-11-15"
    assert doc.provenance.source_repository == "openFDA"
    assert len(doc.sections) == 0


def test_section_hierarchy_and_subsections():
    """Verify hierarchical representation of sections and nested child subsections (e.g. 4 -> 4.2)."""
    child_section = RegulatorySection(
        section_id="sec_4_2",
        parent_section_id="sec_4",
        section_number="4.2",
        heading_raw="4.2 Posology and method of administration",
        heading_normalized=CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE,
        order_index=1,
    )

    parent_section = RegulatorySection(
        section_id="sec_4",
        section_number="4",
        heading_raw="4. Clinical Particulars",
        order_index=0,
        subsections=[child_section],
    )

    doc = RegulatoryDocument(
        title="EU SmPC Carvedilol",
        document_type="CORE_DATA_SHEET",
        jurisdiction="EMA",
        provenance=RegulatoryProvenance(source_repository="EMA_Central"),
        sections=[parent_section],
    )

    assert len(doc.sections) == 1
    assert doc.sections[0].section_id == "sec_4"
    assert doc.sections[0].section_number == "4"
    assert len(doc.sections[0].subsections) == 1

    sub = doc.sections[0].subsections[0]
    assert sub.section_id == "sec_4_2"
    assert sub.parent_section_id == "sec_4"
    assert sub.section_number == "4.2"
    assert sub.heading_raw == "4.2 Posology and method of administration"
    assert sub.heading_normalized == "CONCEPT_POSOLOGY_DOSAGE"


def test_chunk_types_supported():
    """Verify that all required chunk types are supported and validate correctly."""
    valid_types = [
        RegulatoryChunkType.PARAGRAPH,
        RegulatoryChunkType.BULLET,
        RegulatoryChunkType.NUMBERED_ITEM,
        RegulatoryChunkType.TABLE_ROW,
        RegulatoryChunkType.STRUCTURED_FIELD,
        RegulatoryChunkType.HEADING,
    ]

    for chunk_type in valid_types:
        chunk = RegulatoryChunk(
            document_id="doc_1",
            section_id="sec_1",
            chunk_type=chunk_type.value,
            content=f"Content for {chunk_type.value}",
        )
        assert chunk.chunk_type == chunk_type.value
        assert chunk.content == f"Content for {chunk_type.value}"


def test_content_integrity():
    """Verify content integrity: raw source content is never polluted with prefix markers or modified."""
    exact_source_text = "Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours as needed for pain."

    chunk = RegulatoryChunk(
        document_id="doc_123",
        section_id="sec_456",
        chunk_type=RegulatoryChunkType.PARAGRAPH.value,
        content=exact_source_text,
    )

    assert chunk.content == exact_source_text
    assert "[Document:" not in chunk.content
    assert "[Section:" not in chunk.content
    assert chunk.normalized_content is None


def test_normalized_content_independent_enrichment():
    """Verify normalized_content contains contextual breadcrumbs independently from content."""
    exact_source_text = "Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours."
    context_prefix = "[Document: Cardivex | US_PLR | Carvedilol]\n[Section: Dosage and Administration > 2.1 Adult Patients]\n"
    enriched_text = f"{context_prefix}{exact_source_text}"

    chunk = RegulatoryChunk(
        document_id="doc_123",
        section_id="sec_456",
        chunk_type=RegulatoryChunkType.PARAGRAPH.value,
        content=exact_source_text,
        normalized_content=enriched_text,
    )

    # Content integrity preserved
    assert chunk.content == exact_source_text
    assert "[Document:" not in chunk.content

    # Normalized content contains the enriched search representation
    assert chunk.normalized_content == enriched_text
    assert "[Document: Cardivex | US_PLR | Carvedilol]" in chunk.normalized_content


def test_table_and_table_row_model():
    """Verify RegulatoryTable and RegulatoryTableRow preserve headers, order, and column-value relationships."""
    headers = ["Creatinine Clearance", "Recommended Starting Dose", "Maximum Dose"]
    cells = ["< 30 mL/min", "25 mg once daily", "50 mg daily"]
    row_dict = dict(zip(headers, cells))

    row = RegulatoryTableRow(
        row_index=0,
        cells=cells,
        row_dict=row_dict,
    )

    table = RegulatoryTable(
        table_id="tbl_dosage_adjustments",
        section_id="sec_dos_adj",
        table_title="Table 1: Renal Impairment Dosage Adjustments",
        headers=headers,
        raw_markdown="| Creatinine Clearance | Recommended Starting Dose | Maximum Dose |\n| < 30 mL/min | 25 mg once daily | 50 mg daily |",
        rows=[row],
    )

    assert table.table_id == "tbl_dosage_adjustments"
    assert table.section_id == "sec_dos_adj"
    assert table.table_title == "Table 1: Renal Impairment Dosage Adjustments"
    assert table.headers == headers
    assert len(table.rows) == 1
    assert table.rows[0].row_index == 0
    assert table.rows[0].cells == cells
    assert table.rows[0].row_dict["Creatinine Clearance"] == "< 30 mL/min"
    assert table.rows[0].row_dict["Recommended Starting Dose"] == "25 mg once daily"
    assert table.rows[0].row_dict["Maximum Dose"] == "50 mg daily"


def test_chunk_to_content_item_adapter():
    """Verify RegulatoryChunk.to_content_item() maps all required fields to RegulatoryContentItem."""
    key_info = KeyInformation(
        dose="500 mg",
        frequency="every 4 to 6 hours",
        route="oral",
        indication="pain",
    )

    chunk = RegulatoryChunk(
        chunk_id="chk_test_999",
        document_id="doc_abc",
        section_id="sec_def",
        parent_chunk_id="chk_parent_888",
        chunk_type="paragraph",
        order_index=2,
        structure_path="Cardivex > Dosage and Administration > 2.1 Adult Patients",
        content="Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours as needed.",
        normalized_content="[Document: Cardivex]\nAdults: Take 1 tablet (500 mg) orally every 4 to 6 hours as needed.",
        document_name="Cardivex Prescribing Information",
        document_type="REGULATORY_LABEL",
        jurisdiction="US_FDA",
        product="Cardivex",
        active_ingredient="Carvedilol",
        section_title="Dosage and Administration",
        section_number="2.1",
        normalized_section="CONCEPT_POSOLOGY_DOSAGE",
        key_information=key_info,
        source="DailyMed",
        source_identifier="set-12345",
        source_url="https://dailymed.nlm.nih.gov/set/12345",
        version="4.0",
        publication_date="2026-01-10",
        exact_location="Section 2.1, Paragraph 1",
        loinc_code="34068-7",
    )

    item: RegulatoryContentItem = chunk.to_content_item()

    # Exact field mappings required by Section 9
    assert item.content_id == "chk_test_999"
    assert item.document_id == "doc_abc"
    assert item.document_name == "Cardivex Prescribing Information"
    assert item.source == "DailyMed"
    assert item.source_url == "https://dailymed.nlm.nih.gov/set/12345"
    assert item.source_identifier == "set-12345"
    assert item.version == "4.0"
    assert item.date == "2026-01-10"
    assert item.section == "Dosage and Administration"
    assert item.subsection == "2.1"
    assert item.location == "Section 2.1, Paragraph 1"
    assert item.loinc_code == "34068-7"
    assert item.content_type == "paragraph"
    assert item.product == "Cardivex"
    assert item.drug == "Carvedilol"
    assert item.text == "Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours as needed."
    assert item.key_information == key_info
    assert item.dose == "500 mg"
    assert item.route == "oral"
    assert item.indication == "pain"

    # Metadata dictionary preservation
    assert item.metadata["chunk_id"] == "chk_test_999"
    assert item.metadata["section_id"] == "sec_def"
    assert item.metadata["parent_chunk_id"] == "chk_parent_888"
    assert item.metadata["structure_path"] == "Cardivex > Dosage and Administration > 2.1 Adult Patients"
    assert item.metadata["normalized_section"] == "CONCEPT_POSOLOGY_DOSAGE"
    assert item.metadata["jurisdiction"] == "US_FDA"
    assert item.metadata["document_type"] == "REGULATORY_LABEL"
    assert item.metadata["order_index"] == 2


def test_canonical_section_concept_extensibility():
    """Verify CanonicalSectionConcept initial concepts and runtime extensibility."""
    initial_concepts = CanonicalSectionConcept.list_concepts()
    assert CanonicalSectionConcept.CONCEPT_INDICATIONS in initial_concepts
    assert CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE in initial_concepts
    assert CanonicalSectionConcept.CONCEPT_WARNINGS in initial_concepts
    assert CanonicalSectionConcept.is_valid_concept("CONCEPT_POSOLOGY_DOSAGE")

    # Verify extensible registration
    custom_concept = CanonicalSectionConcept.register_concept("CONCEPT_POST_MARKETING_SURVEILLANCE")
    assert custom_concept == "CONCEPT_POST_MARKETING_SURVEILLANCE"
    assert CanonicalSectionConcept.is_valid_concept("CONCEPT_POST_MARKETING_SURVEILLANCE")
    assert "CONCEPT_POST_MARKETING_SURVEILLANCE" in CanonicalSectionConcept.list_concepts()
