"""Unit tests for Phase 2 Step 3: Regulatory Chunker.

Validates:
- Structure-aware chunking vs fixed-size splitting
- Paragraph and section context preservation
- Sentence grouping and sentence-boundary splitting for long paragraphs
- Bullet / list context and introductory stem parent links (parent_chunk_id)
- Table context and row-level chunk preservation (chunk_type="table_row")
- Structured field recognition (chunk_type="structured_field")
- Deterministic, stable chunk IDs
- Document / section / location traceability
- Content integrity: verbatim source text in `content` vs breadcrumbs in `normalized_content`
- Edge cases: empty content, whitespace, very small content
- Backward compatibility adapter to RegulatoryContentItem
"""

import pytest
from app.models.content import RegulatoryContentItem
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
from app.services.chunking import RegulatoryChunker


def test_empty_and_very_small_content():
    """Verify empty, whitespace-only, and sub-threshold content degrades gracefully."""
    chunker = RegulatoryChunker()

    # Empty text
    assert chunker.chunk_text("") == []
    assert chunker.chunk_text("   \n\t  ") == []

    # Section with empty text
    empty_sec = RegulatorySection(
        section_id="sec_empty",
        heading_raw="Empty Section",
        raw_text="",
    )
    assert chunker.chunk_section(empty_sec) == []

    # Sub-threshold fragment (e.g. 5 chars) is safely excluded to prevent noisy chunks
    frag_sec = RegulatorySection(
        section_id="sec_frag",
        heading_raw="Fragment Section",
        raw_text="Hello",
    )
    assert chunker.chunk_section(frag_sec) == []


def test_deterministic_chunk_id_stability():
    """Verify chunk IDs are strictly deterministic and reproducible across multiple runs."""
    chunker = RegulatoryChunker()
    text = """
    INDICATIONS AND USAGE
    Indicated for the relief of mild to moderate headache and musculoskeletal pain.
    """
    chunks_run1 = chunker.chunk_text(text, document_id="doc_aspirin_01", document_name="Aspirin Label")
    chunks_run2 = chunker.chunk_text(text, document_id="doc_aspirin_01", document_name="Aspirin Label")

    assert len(chunks_run1) > 0
    assert len(chunks_run1) == len(chunks_run2)

    for c1, c2 in zip(chunks_run1, chunks_run2):
        assert c1.chunk_id == c2.chunk_id
        assert c1.chunk_id.startswith("chk_")
        assert len(c1.chunk_id) == 16  # "chk_" (4) + 12 hex chars


def test_paragraph_and_section_context_preservation():
    """Verify paragraph chunk preserves exact source text and enriches normalized_content."""
    chunker = RegulatoryChunker()
    verbatim_text = "Adults: Take 1 tablet (500 mg) orally twice daily with a full glass of water."

    sec = RegulatorySection(
        section_id="sec_posology",
        section_number="2",
        heading_raw="DOSAGE AND ADMINISTRATION",
        heading_normalized=CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE,
        raw_text=verbatim_text,
    )

    doc_context = {
        "document_id": "doc_cardivex_10",
        "document_name": "Cardivex Prescribing Information",
        "document_type": "REGULATORY_LABEL",
        "jurisdiction": "US_FDA",
        "active_ingredient": "Carvedilol",
    }

    chunks = chunker.chunk_section(sec, doc_context=doc_context)
    assert len(chunks) == 1
    c = chunks[0]

    # Content integrity: verbatim raw text only
    assert c.content == verbatim_text
    assert "[Document:" not in c.content
    assert "[Section:" not in c.content

    # Traceability attributes
    assert c.document_id == "doc_cardivex_10"
    assert c.document_name == "Cardivex Prescribing Information"
    assert c.section_id == "sec_posology"
    assert c.section_number == "2"
    assert c.section_title == "DOSAGE AND ADMINISTRATION"
    assert c.normalized_section == CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE
    assert c.exact_location == "Paragraph 1"
    assert c.chunk_type == RegulatoryChunkType.PARAGRAPH.value
    assert c.structure_path == "Cardivex Prescribing Information > 2 DOSAGE AND ADMINISTRATION > Paragraph 1"

    # Context enrichment for retrieval
    assert "[Document: Cardivex Prescribing Information | US_FDA | Carvedilol]" in c.normalized_content
    assert "[Section: 2 DOSAGE AND ADMINISTRATION > Paragraph 1]" in c.normalized_content
    assert verbatim_text in c.normalized_content


def test_long_paragraph_sentence_grouping_and_boundary_splitting():
    """Verify long paragraphs (>max_chunk_chars) split cleanly on sentence boundaries with overlap."""
    chunker = RegulatoryChunker(max_chunk_chars=300, sentence_overlap=1)

    s1 = "Initial dose is 12.5 mg once daily with morning meal."
    s2 = "Titrate by 12.5 mg every two weeks based on clinical tolerability."
    s3 = "Maximum recommended dose is 50 mg daily for hypertension."
    s4 = "In elderly patients, dosage titration should proceed cautiously."
    s5 = "Do not discontinue therapy abruptly to avoid rebound hypertension."

    long_paragraph = f"{s1} {s2} {s3} {s4} {s5}"
    sec = RegulatorySection(
        section_id="sec_long",
        section_number="4.2",
        heading_raw="Posology",
        raw_text=long_paragraph,
    )

    chunks = chunker.chunk_section(sec)
    assert len(chunks) >= 2

    for c in chunks:
        # Crucial: each chunk must end with a period (no mid-sentence slicing!)
        assert c.content.strip().endswith(".")
        assert c.chunk_type == RegulatoryChunkType.PARAGRAPH.value
        # Structure path tags part numbers
        assert "Part " in c.structure_path

    # Verify sentence overlap: last sentence of chunk 0 appears in chunk 1
    assert s3 in chunks[0].content or s2 in chunks[0].content
    # Sentence 5 is in the final chunk
    assert s5 in chunks[-1].content


def test_bullet_and_list_context_preservation():
    """Verify bullet lists preserve stem sentence context and link parent_chunk_id."""
    chunker = RegulatoryChunker()
    raw_text = """
The following adverse reactions were reported in clinical trials:
- Headache
- Nausea
- Dizziness
"""
    sec = RegulatorySection(
        section_id="sec_adv",
        section_number="4.8",
        heading_raw="Undesirable effects",
        raw_text=raw_text,
    )

    chunks = chunker.chunk_section(sec)

    # 1 stem chunk (paragraph) + 3 bullet chunks
    assert len(chunks) == 4

    stem_chunk = chunks[0]
    assert stem_chunk.chunk_type == RegulatoryChunkType.PARAGRAPH.value
    assert "The following adverse reactions were reported in clinical trials:" in stem_chunk.content

    bullet_chunks = chunks[1:]
    expected_bullets = ["Headache", "Nausea", "Dizziness"]

    for idx, (bc, expected_text) in enumerate(zip(bullet_chunks, expected_bullets)):
        assert bc.chunk_type == RegulatoryChunkType.BULLET.value
        # Verbatim content
        assert bc.content == expected_text
        # Parent chunk link
        assert bc.parent_chunk_id == stem_chunk.chunk_id
        # Sequential ordering
        assert bc.order_index == idx + 1
        # Normalized content includes the introductory stem context for search
        assert "The following adverse reactions were reported in clinical trials:" in bc.normalized_content
        assert expected_text in bc.normalized_content


def test_table_context_preservation():
    """Verify tabular content extracts as row-level chunks preserving column-value relationships."""
    chunker = RegulatoryChunker()
    table_text = """
| Creatinine Clearance | Recommended Dose | Maximum Dose |
| --- | --- | --- |
| < 30 mL/min | 25 mg once daily | 50 mg daily |
| 30 to 60 mL/min | 50 mg once daily | 100 mg daily |
"""
    sec = RegulatorySection(
        section_id="sec_renal",
        section_number="2.2",
        heading_raw="Renal Impairment Dosage",
        raw_text=table_text,
    )

    chunks = chunker.chunk_section(sec)
    assert len(chunks) == 2

    for row_idx, c in enumerate(chunks):
        assert c.chunk_type == RegulatoryChunkType.TABLE_ROW.value
        assert "Creatinine Clearance:" in c.content
        assert "Recommended Dose:" in c.content
        assert "Maximum Dose:" in c.content
        assert c.exact_location == f"Table, Row {row_idx + 1}"
        assert c.structure_path.endswith(f"Row {row_idx + 1}")

    assert "< 30 mL/min" in chunks[0].content
    assert "25 mg once daily" in chunks[0].content
    assert "30 to 60 mL/min" in chunks[1].content


def test_structured_field_chunking():
    """Verify single-line structured regulatory key-value fields are classified as structured_field."""
    chunker = RegulatoryChunker()
    text = "NDC: 0093-1025-01"
    sec = RegulatorySection(
        section_id="sec_desc",
        heading_raw="How Supplied",
        raw_text=text,
    )

    chunks = chunker.chunk_section(sec)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == RegulatoryChunkType.STRUCTURED_FIELD.value
    assert chunks[0].content == text
    assert chunks[0].exact_location == "Field (NDC)"


def test_multi_section_document_tree_chunking():
    """Verify hierarchical RegulatoryDocument tree is traversed and populated recursively."""
    chunker = RegulatoryChunker()

    sub_section = RegulatorySection(
        section_id="sec_4_2",
        section_number="4.2",
        heading_raw="Posology and method of administration",
        raw_text="Adults: Take 100 mg once daily.",
    )

    parent_section = RegulatorySection(
        section_id="sec_4",
        section_number="4",
        heading_raw="Clinical particulars",
        raw_text="This section contains clinical particulars for the product.",
        subsections=[sub_section],
    )

    prov = RegulatoryProvenance(
        source_repository="DailyMed",
        source_identifier="spl-test-999",
    )

    doc = RegulatoryDocument(
        document_id="doc_spl_999",
        title="Sample Drug SmPC",
        document_type="CORE_DATA_SHEET",
        jurisdiction="EMA",
        provenance=prov,
        sections=[parent_section],
    )

    all_chunks = chunker.chunk_document(doc)
    assert len(all_chunks) == 2

    # Section chunks are populated on the section objects
    assert len(parent_section.chunks) == 1
    assert len(sub_section.chunks) == 1

    # Subsection chunk inherits ancestor path
    sub_chunk = sub_section.chunks[0]
    assert sub_chunk.section_number == "4.2"
    assert "Clinical particulars" in sub_chunk.structure_path
    assert "Posology" in sub_chunk.structure_path


def test_backward_compatibility_adapter_conversion():
    """Verify every RegulatoryChunk converts seamlessly to RegulatoryContentItem."""
    chunker = RegulatoryChunker()
    text = """
    INDICATIONS AND USAGE
    Indicated for treatment of hypertension.
    """
    chunks = chunker.chunk_text(
        text=text,
        document_id="doc_htn_01",
        document_name="Hypertension Label",
        product="Cardioguard",
        active_ingredient="Amlodipine",
    )

    assert len(chunks) == 1
    c = chunks[0]

    # Convert via Phase 1 adapter
    item: RegulatoryContentItem = c.to_content_item()
    assert item.content_id == c.chunk_id
    assert item.document_id == "doc_htn_01"
    assert item.document_name == "Hypertension Label"
    assert item.product == "Cardioguard"
    assert item.drug == "Amlodipine"
    assert item.text == c.content
    assert item.content_type == "paragraph"
    assert item.metadata["structure_path"] == c.structure_path
    assert item.metadata["chunk_id"] == c.chunk_id
