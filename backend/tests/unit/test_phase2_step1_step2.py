"""Unit tests for Phase 2 Steps 1 & 2: Regulatory Sentence Tokenizer, Outline Engine, Table & Bullet Extractor.

Validates the 18 specific Phase 2 requirements:
1. Normal sentence splitting
2. Pharmaceutical units such as mg.
3. e.g. / i.e.
4. Decimal section numbers such as 4.2
5. Numbered sections
6. Nested section numbering
7. Lettered items
8. Roman numeral items
9. US-style headings
10. EU-style headings
11. Unknown headings
12. Markdown table extraction
13. HTML table extraction
14. Table headers and rows
15. Bullet extraction
16. Bullet ordering
17. Source text preservation
18. Malformed/edge cases
"""

import pytest
from app.models.document import CanonicalSectionConcept, RegulatoryTable, RegulatoryTableRow
from app.services.chunking import (
    RegulatoryBulletExtractor,
    RegulatoryOutlineEngine,
    RegulatorySentenceTokenizer,
    RegulatoryTableExtractor,
)


# =========================================================================
# STEP 1: SENTENCE TOKENIZER TESTS (Requirements 1 - 4, 17, 18)
# =========================================================================

def test_normal_sentence_splitting():
    """1. Verify standard sentences with periods, question marks, and exclamation marks split cleanly."""
    tokenizer = RegulatorySentenceTokenizer()
    text = "Take 1 tablet orally with water. Do you have hepatic impairment? Stop immediately if rash occurs!"
    sentences = tokenizer.tokenize(text)

    assert len(sentences) == 3
    assert sentences[0] == "Take 1 tablet orally with water."
    assert sentences[1] == "Do you have hepatic impairment?"
    assert sentences[2] == "Stop immediately if rash occurs!"


def test_pharmaceutical_units_abbreviations():
    """2. Verify pharmaceutical dosage abbreviations (mg., mL., mcg., kg., tab.) do not trigger false sentence breaks."""
    tokenizer = RegulatorySentenceTokenizer()
    text = "Initial dose is 25 mg. Once daily in the morning. Titrate by 10 mg. Every two weeks if needed. Administer 5 mL. With a full glass of water. Each tab. Contains 250 mcg. Active substance."
    sentences = tokenizer.tokenize(text)

    # Must not split inside "25 mg. Once", "10 mg. Every", "5 mL. With", "tab. Contains", "250 mcg. Active"
    assert len(sentences) == 4
    assert sentences[0] == "Initial dose is 25 mg. Once daily in the morning."
    assert sentences[1] == "Titrate by 10 mg. Every two weeks if needed."
    assert sentences[2] == "Administer 5 mL. With a full glass of water."
    assert sentences[3] == "Each tab. Contains 250 mcg. Active substance."


def test_latin_abbreviations_eg_ie_vs():
    """3. Verify Latin and clinical abbreviations (e.g., i.e., vs., approx., Dr., No.) do not cause false breaks."""
    tokenizer = RegulatorySentenceTokenizer()
    text = "Administer with liquids (e.g. water or juice). Avoid concomitant intake (i.e. within 14 days of MAOIs). In trial A vs. Trial B, efficacy was approx. 95%. Contact Dr. Smith at Ref. No. 102."
    sentences = tokenizer.tokenize(text)

    assert len(sentences) == 4
    assert sentences[0] == "Administer with liquids (e.g. water or juice)."
    assert sentences[1] == "Avoid concomitant intake (i.e. within 14 days of MAOIs)."
    assert sentences[2] == "In trial A vs. Trial B, efficacy was approx. 95%."
    assert sentences[3] == "Contact Dr. Smith at Ref. No. 102."


def test_decimal_section_numbers_and_values():
    """4. Verify decimal outline citations (4.2) and numeric decimals (12.5 mg) do not split."""
    tokenizer = RegulatorySentenceTokenizer()
    text = "Refer to Section 4.2 for posology guidelines. The starting dose is 12.5 mg once daily. Renal clearance was 0.05 L/hr in study 1.2."
    sentences = tokenizer.tokenize(text)

    assert len(sentences) == 3
    assert sentences[0] == "Refer to Section 4.2 for posology guidelines."
    assert sentences[1] == "The starting dose is 12.5 mg once daily."
    assert sentences[2] == "Renal clearance was 0.05 L/hr in study 1.2."


def test_source_text_preservation():
    """17. Verify exact source text and character offsets are preserved without modification."""
    tokenizer = RegulatorySentenceTokenizer()
    text = "Adults: Take 1 tablet orally.   Drink plenty of fluids.   "
    spans = tokenizer.tokenize_with_spans(text)

    assert len(spans) == 2
    s1, start1, end1 = spans[0]
    s2, start2, end2 = spans[1]

    assert s1 == "Adults: Take 1 tablet orally."
    assert text[start1:end1] == s1
    assert s2 == "Drink plenty of fluids."
    assert text[start2:end2] == s2


def test_malformed_and_edge_cases():
    """18. Verify safe degradation on empty input, whitespace, ellipses, and unpunctuated text."""
    tokenizer = RegulatorySentenceTokenizer()
    assert tokenizer.tokenize("") == []
    assert tokenizer.tokenize("   \n\t  ") == []

    # Ellipsis handling
    ellipsis_text = "Dose titration is ongoing... Efficacy results will follow."
    sentences = tokenizer.tokenize(ellipsis_text)
    assert len(sentences) == 2
    assert "ongoing..." in sentences[0]

    # Outline engine edge cases
    engine = RegulatoryOutlineEngine()
    assert engine.parse_heading("") is None
    assert engine.parse_heading("   ") is None
    assert engine.parse_list_item("") is None

    # Table extractor edge cases
    table_extractor = RegulatoryTableExtractor()
    assert table_extractor.extract_markdown_tables("") == []
    assert table_extractor.extract_html_tables("<div>No tables here</div>") == []
    assert table_extractor.extract_tsv_tables("Single line with no tabs") == []


# =========================================================================
# STEP 1: OUTLINE ENGINE TESTS (Requirements 5 - 11)
# =========================================================================

def test_numbered_sections():
    """5. Verify outline engine detects numbered sections and parses outline numbers."""
    engine = RegulatoryOutlineEngine()

    h1 = engine.parse_heading("1. Name of the medicinal product")
    assert h1 is not None
    assert h1.section_number == "1"
    assert h1.title == "Name of the medicinal product"

    h4 = engine.parse_heading("4. Clinical Particulars")
    assert h4 is not None
    assert h4.section_number == "4"

    h42 = engine.parse_heading("4.2 Posology and method of administration")
    assert h42 is not None
    assert h42.section_number == "4.2"
    assert h42.title == "Posology and method of administration"
    assert h42.level == 2


def test_nested_section_numbering_hierarchy():
    """6. Verify hierarchy calculation across nested sections (e.g. 4 -> 4.2 -> 4.2.1)."""
    engine = RegulatoryOutlineEngine()

    h4 = engine.parse_heading("4. Clinical Particulars")
    h42 = engine.parse_heading("4.2 Posology and method of administration")
    h421 = engine.parse_heading("4.2.1 Adult Patients")

    headings = engine.build_hierarchy([h4, h42, h421])
    assert headings[0].level == 1
    assert headings[0].parent_section_number is None

    assert headings[1].level == 2
    assert headings[1].parent_section_number == "4"

    assert headings[2].level == 3
    assert headings[2].parent_section_number == "4.2"


def test_lettered_items():
    """7. Verify lettered list items are recognized with their markers."""
    engine = RegulatoryOutlineEngine()

    item1 = engine.parse_list_item("(a) Adults: Take 1 tablet daily.")
    assert item1 is not None
    assert item1.marker == "(a)"
    assert item1.content == "Adults: Take 1 tablet daily."
    assert item1.item_type == "lettered_item"

    item2 = engine.parse_list_item("b. Pediatric patients: Not recommended.")
    assert item2 is not None
    assert item2.marker == "b."
    assert item2.item_type == "lettered_item"


def test_roman_numeral_items():
    """8. Verify roman numeral list items are classified accurately."""
    engine = RegulatoryOutlineEngine()

    item1 = engine.parse_list_item("(i) Severe renal impairment (CrCl < 30 mL/min)")
    assert item1 is not None
    assert item1.marker == "(i)"
    assert item1.item_type == "roman_item"
    assert "Severe renal impairment" in item1.content

    item2 = engine.parse_list_item("(ii) Moderate renal impairment")
    assert item2 is not None
    assert item2.marker == "(ii)"
    assert item2.item_type == "roman_item"


def test_us_style_headings():
    """9. Verify US PLR standard headings are recognized and mapped to canonical concepts."""
    engine = RegulatoryOutlineEngine()

    headings = [
        ("INDICATIONS AND USAGE", CanonicalSectionConcept.CONCEPT_INDICATIONS),
        ("DOSAGE AND ADMINISTRATION", CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE),
        ("CONTRAINDICATIONS", CanonicalSectionConcept.CONCEPT_CONTRAINDICATIONS),
        ("WARNINGS AND PRECAUTIONS", CanonicalSectionConcept.CONCEPT_WARNINGS),
        ("ADVERSE REACTIONS", CanonicalSectionConcept.CONCEPT_ADVERSE_REACTIONS),
        ("DRUG INTERACTIONS", CanonicalSectionConcept.CONCEPT_DRUG_INTERACTIONS),
        ("USE IN SPECIFIC POPULATIONS", CanonicalSectionConcept.CONCEPT_POPULATIONS),
        ("OVERDOSAGE", CanonicalSectionConcept.CONCEPT_OVERDOSAGE),
    ]

    for raw, expected_concept in headings:
        h = engine.parse_heading(raw)
        assert h is not None, f"Failed to parse heading: {raw}"
        assert h.heading_normalized == expected_concept
        assert h.heading_raw == raw


def test_eu_style_headings():
    """10. Verify EU SmPC standard headings are recognized and mapped without forcing into US names."""
    engine = RegulatoryOutlineEngine()

    headings = [
        ("4.1 Therapeutic indications", CanonicalSectionConcept.CONCEPT_INDICATIONS),
        ("4.2 Posology and method of administration", CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE),
        ("4.3 Contraindications", CanonicalSectionConcept.CONCEPT_CONTRAINDICATIONS),
        ("4.4 Special warnings and precautions for use", CanonicalSectionConcept.CONCEPT_WARNINGS),
        ("4.8 Undesirable effects", CanonicalSectionConcept.CONCEPT_ADVERSE_REACTIONS),
        ("4.9 Overdose", CanonicalSectionConcept.CONCEPT_OVERDOSAGE),
        ("5.1 Pharmacodynamic properties", CanonicalSectionConcept.CONCEPT_CLINICAL_PHARM),
    ]

    for raw, expected_concept in headings:
        h = engine.parse_heading(raw)
        assert h is not None, f"Failed to parse EU heading: {raw}"
        assert h.heading_normalized == expected_concept
        # Crucial requirement: raw heading is preserved
        assert h.heading_raw == raw


def test_unknown_headings():
    """11. Verify unknown headings are not destroyed and remain accessible via heading_raw."""
    engine = RegulatoryOutlineEngine()

    raw = "4.7 Effects on ability to drive and use machines"
    h = engine.parse_heading(raw)

    assert h is not None
    assert h.heading_raw == raw
    assert h.section_number == "4.7"
    assert h.title == "Effects on ability to drive and use machines"
    assert h.level == 2
    # Not mapped to an existing concept, but preserved
    assert h.heading_normalized is None


# =========================================================================
# STEP 2: TABLE & BULLET EXTRACTION TESTS (Requirements 12 - 16)
# =========================================================================

def test_markdown_table_extraction():
    """12. Verify Markdown table extraction into RegulatoryTable and RegulatoryTableRow."""
    extractor = RegulatoryTableExtractor()
    markdown_text = """
### Dosage Recommendations
| Renal Clearance | Initial Dose | Maximum Dose |
| :--- | :--- | :--- |
| < 30 mL/min | 25 mg once daily | 50 mg daily |
| 30 to 60 mL/min | 50 mg once daily | 100 mg daily |
"""
    tables = extractor.extract_markdown_tables(markdown_text, section_id="sec_posology")

    assert len(tables) == 1
    t = tables[0]
    assert t.section_id == "sec_posology"
    assert t.headers == ["Renal Clearance", "Initial Dose", "Maximum Dose"]
    assert len(t.rows) == 2
    assert t.rows[0].row_dict["Renal Clearance"] == "< 30 mL/min"
    assert t.rows[0].row_dict["Initial Dose"] == "25 mg once daily"
    assert t.rows[0].row_dict["Maximum Dose"] == "50 mg daily"
    assert t.rows[1].row_dict["Renal Clearance"] == "30 to 60 mL/min"


def test_html_table_extraction():
    """13. Verify HTML table extraction with caption, TH headers, and TD rows."""
    extractor = RegulatoryTableExtractor()
    html_text = """
    <table>
        <caption>Table 2: Clinical Trial Adverse Reactions</caption>
        <thead>
            <tr>
                <th>Adverse Reaction</th>
                <th>Drug (%)</th>
                <th>Placebo (%)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Headache</td>
                <td>12.5</td>
                <td>5.0</td>
            </tr>
            <tr>
                <td>Dizziness</td>
                <td>8.2</td>
                <td>2.1</td>
            </tr>
        </tbody>
    </table>
    """
    tables = extractor.extract_html_tables(html_text, section_id="sec_adverse")

    assert len(tables) == 1
    t = tables[0]
    assert t.section_id == "sec_adverse"
    assert t.table_title == "Table 2: Clinical Trial Adverse Reactions"
    assert t.headers == ["Adverse Reaction", "Drug (%)", "Placebo (%)"]
    assert len(t.rows) == 2
    assert t.rows[0].row_dict["Adverse Reaction"] == "Headache"
    assert t.rows[0].row_dict["Drug (%)"] == "12.5"
    assert t.rows[1].row_dict["Adverse Reaction"] == "Dizziness"


def test_table_headers_and_rows_content_formatting():
    """14. Verify row formatting preserves header-to-value pairs for future chunking."""
    extractor = RegulatoryTableExtractor()
    md_text = """
| Population | Recommended Starting Dose |
| --- | --- |
| Adults | 100 mg once daily |
| Geriatric | 50 mg once daily |
"""
    tables = extractor.extract_markdown_tables(md_text)
    assert len(tables) == 1
    t = tables[0]

    row_content = extractor.format_row_as_content(t, t.rows[0])
    assert row_content == "Population: Adults | Recommended Starting Dose: 100 mg once daily"


def test_bullet_extraction():
    """15. Verify bullet list extraction and stem sentence detection."""
    extractor = RegulatoryBulletExtractor()
    text = """
The following severe adverse reactions are discussed elsewhere in labeling:
- Hypersensitivity reactions
- Severe cutaneous adverse reactions
• Anaphylaxis
* Angioedema
"""
    groups = extractor.extract_bullets_and_lists(text)

    assert len(groups) == 1
    stem, items = groups[0]
    assert stem == "The following severe adverse reactions are discussed elsewhere in labeling:"
    assert len(items) == 4
    assert items[0].content == "Hypersensitivity reactions"
    assert items[0].marker == "-"
    assert items[2].content == "Anaphylaxis"
    assert items[2].marker == "•"
    assert items[3].content == "Angioedema"
    assert items[3].marker == "*"


def test_bullet_ordering():
    """16. Verify bullet order index is strictly preserved."""
    extractor = RegulatoryBulletExtractor()
    text = """
- First bullet item
- Second bullet item
- Third bullet item
"""
    groups = extractor.extract_bullets_and_lists(text)
    assert len(groups) == 1
    _, items = groups[0]

    assert items[0].order_index == 0
    assert items[1].order_index == 1
    assert items[2].order_index == 2
