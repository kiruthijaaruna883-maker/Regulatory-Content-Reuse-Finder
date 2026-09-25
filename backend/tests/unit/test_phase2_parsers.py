"""Unit tests for Phase 2 Step 4: Multi-format regulatory text parsers.

Validates deterministic parsing for:
1. Plain TXT (TextDocumentParser)
2. Markdown (MarkdownDocumentParser)
3. JSON (JsonDocumentParser)
4. XML (XmlDocumentParser)
5. HTML (HtmlDocumentParser)

Also validates factory dispatch, empty/malformed error handling, repeated deterministic runs,
and end-to-end compatibility with Phase 1 models and the RegulatoryChunker.
"""

import pytest

from app.models.document import RegulatoryDocument, RegulatoryProvenance
from app.services.chunking.regulatory_chunker import RegulatoryChunker
from app.services.chunking.table_extractor import RegulatoryBulletExtractor, RegulatoryTableExtractor
from app.services.parsers import (
    BaseDocumentParser,
    HtmlDocumentParser,
    JsonDocumentParser,
    MarkdownDocumentParser,
    TextDocumentParser,
    XmlDocumentParser,
    get_parser,
    parse_regulatory_document,
)


# ============================================================================
# 1. TXT PARSER TESTS
# ============================================================================

def test_txt_parser_with_outline_headings():
    """Verify TXT parser detects standard regulatory outline headings."""
    content = (
        "1. INDICATIONS AND USAGE\n"
        "Drug X is indicated for the treatment of hypertension.\n"
        "It should be taken under medical supervision.\n\n"
        "2. DOSAGE AND ADMINISTRATION\n"
        "The recommended starting dose is 10 mg once daily.\n"
        "Dosage may be increased to 20 mg after 2 weeks.\n"
    )

    parser = TextDocumentParser()
    assert parser.can_parse(content, filename="label.txt") is True

    doc = parser.parse(
        content,
        document_id="doc_txt_001",
        document_name="Drug X Label",
        metadata={"product_name": "Drug X", "jurisdiction": "US_FDA"},
    )

    assert isinstance(doc, RegulatoryDocument)
    assert doc.document_id == "doc_txt_001"
    assert doc.title == "Drug X Label"
    assert doc.product_name == "Drug X"
    assert len(doc.sections) == 2

    sec1 = doc.sections[0]
    assert sec1.section_number == "1"
    assert "INDICATIONS" in sec1.heading_raw.upper()
    assert "hypertension" in (sec1.raw_text or "")
    assert sec1.order_index == 0

    sec2 = doc.sections[1]
    assert sec2.section_number == "2"
    assert "DOSAGE" in sec2.heading_raw.upper()
    assert "10 mg once daily" in (sec2.raw_text or "")
    assert sec2.order_index == 1


def test_txt_parser_empty_and_plain_unheaded():
    """Verify TXT parser handles empty content and text without formal headings."""
    parser = TextDocumentParser()

    empty_doc = parser.parse("", document_id="doc_empty")
    assert len(empty_doc.sections) == 0
    assert empty_doc.raw_content == ""

    plain_text = "This is a brief advisory note regarding storage conditions.\nStore below 25 deg C."
    unheaded_doc = parser.parse(plain_text, document_id="doc_unheaded")
    assert len(unheaded_doc.sections) == 1
    assert unheaded_doc.sections[0].heading_raw == "General Content"
    assert "Store below 25 deg C" in (unheaded_doc.sections[0].raw_text or "")


# ============================================================================
# 2. MARKDOWN PARSER TESTS
# ============================================================================

def test_markdown_parser_headings_and_hierarchy():
    """Verify Markdown parser extracts hierarchical levels (# to ###) into subsections."""
    md_content = (
        "# Product Information\n"
        "General introduction to the medicinal product.\n\n"
        "## 4. CLINICAL PARTICULARS\n"
        "Overview of clinical data.\n\n"
        "### 4.1 Therapeutic indications\n"
        "Indicated for acute pain relief in adults.\n\n"
        "### 4.2 Posology and method of administration\n"
        "Administer 500 mg orally every 6 hours.\n"
    )

    parser = MarkdownDocumentParser()
    assert parser.can_parse(md_content, filename="dossier.md") is True

    doc = parser.parse(md_content, document_id="doc_md_001")
    assert len(doc.sections) == 1

    root = doc.sections[0]
    assert root.heading_raw == "# Product Information"
    assert "General introduction" in (root.raw_text or "")
    assert len(root.subsections) == 1

    sec4 = root.subsections[0]
    assert sec4.heading_raw == "## 4. CLINICAL PARTICULARS"
    assert sec4.parent_section_id == root.section_id
    assert len(sec4.subsections) == 2

    sub41 = sec4.subsections[0]
    assert "4.1" in (sub41.section_number or sub41.heading_raw)
    assert "acute pain relief" in (sub41.raw_text or "")
    assert sub41.parent_section_id == sec4.section_id

    sub42 = sec4.subsections[1]
    assert "4.2" in (sub42.section_number or sub42.heading_raw)
    assert "500 mg orally" in (sub42.raw_text or "")


def test_markdown_parser_tables_and_lists():
    """Verify Markdown parser preserves tables, bullet lists, and numbered lists in raw_text."""
    md_content = (
        "# Dosing Guidelines\n\n"
        "| Age Group | Recommended Dose | Frequency |\n"
        "|---|---|---|\n"
        "| Adults | 500 mg | Every 6 hours |\n"
        "| Children 6-12 | 250 mg | Every 8 hours |\n\n"
        "Special instructions:\n"
        "* Take with a full glass of water.\n"
        "* Do not chew or crush tablets.\n\n"
        "Precautions:\n"
        "1. Consult physician if pregnant.\n"
        "2. Do not exceed 4000 mg in 24 hours.\n"
    )

    parser = MarkdownDocumentParser()
    doc = parser.parse(md_content, document_id="doc_md_table")
    assert len(doc.sections) == 1

    sec = doc.sections[0]
    # Check that TableExtractor detects table in raw_text
    extractor = RegulatoryTableExtractor()
    tables = extractor.extract_markdown_tables(sec.raw_text or "", section_id=sec.section_id)
    assert len(tables) == 1
    assert tables[0].headers == ["Age Group", "Recommended Dose", "Frequency"]
    assert len(tables[0].rows) == 2

    # Check that BulletExtractor detects bullet items
    bullet_ext = RegulatoryBulletExtractor()
    groups = bullet_ext.extract_bullets_and_lists(sec.raw_text or "")
    assert len(groups) >= 1
    all_items = [item for stem, items in groups for item in items]
    assert len(all_items) >= 2
    assert any("Take with a full glass of water" in b.content for b in all_items)


# ============================================================================
# 3. JSON PARSER TESTS
# ============================================================================

def test_json_parser_openfda_format():
    """Verify JSON parser supports openFDA format results extracting drug names and sections."""
    openfda_payload = {
        "results": [
            {
                "id": "openfda-mock-set-001",
                "openfda": {
                    "brand_name": ["SampleBrand"],
                    "generic_name": ["samplemab"],
                },
                "indications_and_usage": [
                    "SampleBrand is indicated for the treatment of moderate to severe conditions."
                ],
                "dosage_and_administration": [
                    "Administer 100 mg via subcutaneous injection every 4 weeks."
                ],
                "warnings_and_cautions": [
                    "Risk of serious infections has been reported."
                ],
            }
        ]
    }

    import json
    json_str = json.dumps(openfda_payload)

    parser = JsonDocumentParser()
    assert parser.can_parse(json_str, filename="label.json") is True

    doc = parser.parse(json_str)
    assert doc.document_id == "openfda-mock-set-001"
    assert doc.product_name == "SampleBrand"
    assert doc.active_ingredient == "samplemab"
    assert len(doc.sections) >= 3

    headings = [s.heading_raw.lower() for s in doc.sections]
    assert any("indications" in h for h in headings)
    assert any("dosage" in h for h in headings)
    assert any("warnings" in h for h in headings)


def test_json_parser_nested_structures_and_json_paths():
    """Verify JSON parser handles arbitrary nested objects preserving JSON path traceability."""
    import json
    payload = {
        "document_id": "REG-JSON-NESTED",
        "title": "Clinical Summary Payload",
        "administrative_info": {
            "sponsor": "Pharma Corp",
            "submission_type": "NDA",
        },
        "study_results": {
            "primary_endpoint": "Statistically significant improvement at Week 12.",
            "sample_size": 450,
        },
    }
    json_str = json.dumps(payload)

    parser = JsonDocumentParser()
    doc = parser.parse(json_str)

    assert doc.document_id == "REG-JSON-NESTED"
    assert doc.title == "Clinical Summary Payload"
    assert len(doc.sections) == 2

    sec_study = next(s for s in doc.sections if "Study Results" in s.heading_raw)
    assert "[JSON Path: $.study_results]" in (sec_study.raw_text or "")
    assert "primary_endpoint" in (sec_study.raw_text or "")


def test_json_parser_malformed_and_empty():
    """Verify JSON parser raises ValueError on invalid JSON and handles empty string."""
    parser = JsonDocumentParser()

    empty_doc = parser.parse("", document_id="empty_json")
    assert len(empty_doc.sections) == 0

    with pytest.raises(ValueError, match="Invalid JSON content"):
        parser.parse("{ invalid_json: true, ")


# ============================================================================
# 4. XML PARSER TESTS
# ============================================================================

def test_xml_parser_spl_format():
    """Verify XML parser correctly parses HL7 SPL format with LOINC codes and sections."""
    spl_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <document xmlns="urn:hl7-org:v3">
        <title>SAMPLE ASPIRIN LABEL</title>
        <component>
            <structuredBody>
                <component>
                    <section ID="sec_dosage">
                        <code code="34068-7" displayName="DOSAGE &amp; ADMINISTRATION SECTION"/>
                        <title>Directions</title>
                        <text>
                            <paragraph>Adults: 2 tablets every 4 hours.</paragraph>
                            <paragraph>Do not exceed 8 tablets in 24 hours.</paragraph>
                        </text>
                    </section>
                </component>
                <component>
                    <section ID="sec_indications">
                        <code code="34067-9" displayName="INDICATIONS &amp; USAGE SECTION"/>
                        <title>Indications and Usage</title>
                        <text>
                            <paragraph>Temporarily relieves minor aches and pains.</paragraph>
                        </text>
                    </section>
                </component>
            </structuredBody>
        </component>
    </document>
    """

    parser = XmlDocumentParser()
    assert parser.can_parse(spl_xml, filename="label.xml") is True

    doc = parser.parse(spl_xml, document_id="doc_spl_123")
    assert doc.document_id == "doc_spl_123"
    assert "ASPIRIN" in doc.title.upper()
    assert len(doc.sections) == 2

    dosage_sec = next(s for s in doc.sections if "DOSAGE" in s.heading_raw.upper())
    assert dosage_sec.loinc_code == "34068-7"
    assert "Adults: 2 tablets every 4 hours" in (dosage_sec.raw_text or "")

    ind_sec = next(s for s in doc.sections if "INDICATIONS" in s.heading_raw.upper())
    assert ind_sec.loinc_code == "34067-9"
    assert "relieves minor aches and pains" in (ind_sec.raw_text or "")


def test_xml_parser_generic_hierarchy_and_tables():
    """Verify XML parser extracts arbitrary XML hierarchy, attributes, and formats embedded tables."""
    generic_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <regulatory_submission id="REG-SUB-456" version="2.1">
        <title>Pediatric Study Report</title>
        <product>Pediatric Formulation X</product>
        <drug>Substance A</drug>
        <pharmacokinetics number="1.0">
            <paragraph>Clearance is weight-dependent in pediatric populations.</paragraph>
            <table>
                <tr>
                    <th>Age Bracket</th>
                    <th>Mean Clearance (mL/min)</th>
                </tr>
                <tr>
                    <td>2-6 years</td>
                    <td>14.2</td>
                </tr>
                <tr>
                    <td>7-12 years</td>
                    <td>22.5</td>
                </tr>
            </table>
        </pharmacokinetics>
        <safety_summary number="2.0">
            <paragraph>No unexpected adverse reactions observed.</paragraph>
            <list>
                <item>Mild headache in 3% of patients.</item>
                <item>Transient nausea in 1% of patients.</item>
            </list>
        </safety_summary>
    </regulatory_submission>
    """

    parser = XmlDocumentParser()
    doc = parser.parse(generic_xml)

    assert doc.document_id == "REG-SUB-456"
    assert doc.version == "2.1"
    assert doc.product_name == "Pediatric Formulation X"
    assert doc.active_ingredient == "Substance A"
    assert len(doc.sections) == 2

    pk_sec = doc.sections[0]
    assert pk_sec.section_number == "1.0"
    assert "Clearance is weight-dependent" in (pk_sec.raw_text or "")
    # Check that table was converted to markdown table
    assert "| Age Bracket | Mean Clearance (mL/min) |" in (pk_sec.raw_text or "")
    assert "| 2-6 years | 14.2 |" in (pk_sec.raw_text or "")

    safety_sec = doc.sections[1]
    assert safety_sec.section_number == "2.0"
    assert "* Mild headache in 3% of patients." in (safety_sec.raw_text or "")


def test_xml_parser_malformed_and_empty():
    """Verify XML parser raises ValueError on unparseable XML and handles empty string."""
    parser = XmlDocumentParser()

    empty_doc = parser.parse("", document_id="empty_xml")
    assert len(empty_doc.sections) == 0

    with pytest.raises(ValueError, match="Invalid XML content"):
        parser.parse("<root><unclosed_tag></root>")


# ============================================================================
# 5. HTML PARSER TESTS
# ============================================================================

def test_html_parser_headings_lists_and_tables():
    """Verify HTML parser extracts headings hierarchy, paragraphs, lists, and tables."""
    html_content = """<!DOCTYPE html>
    <html>
    <head>
        <title>Mock Product Monograph</title>
    </head>
    <body>
        <h1>1. INDICATIONS AND CLINICAL USE</h1>
        <p>Drug Y is indicated for the management of chronic pain in adults.</p>

        <h2>1.1 Pediatrics</h2>
        <p>Safety and efficacy in pediatric patients have not been established.</p>
        <ul>
            <li>Under 12 years: Not recommended.</li>
            <li>12 to 18 years: Consult specialist.</li>
        </ul>

        <h1>2. DOSAGE AND ADMINISTRATION</h1>
        <p>Recommended starting dosage table:</p>
        <table>
            <thead>
                <tr>
                    <th>Severity</th>
                    <th>Initial Dose</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Mild</td>
                    <td>25 mg daily</td>
                </tr>
                <tr>
                    <td>Moderate</td>
                    <td>50 mg daily</td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """

    parser = HtmlDocumentParser()
    assert parser.can_parse(html_content, filename="monograph.html") is True

    doc = parser.parse(html_content, document_id="doc_html_001")
    assert doc.title == "Mock Product Monograph"
    assert len(doc.sections) == 2

    sec1 = doc.sections[0]
    assert "1. INDICATIONS" in sec1.heading_raw
    assert "chronic pain in adults" in (sec1.raw_text or "")
    assert len(sec1.subsections) == 1

    sub11 = sec1.subsections[0]
    assert "1.1 Pediatrics" in sub11.heading_raw
    assert sub11.parent_section_id == sec1.section_id
    assert "* Under 12 years: Not recommended." in (sub11.raw_text or "")

    sec2 = doc.sections[1]
    assert "2. DOSAGE" in sec2.heading_raw
    assert "| Severity | Initial Dose |" in (sec2.raw_text or "")
    assert "| Moderate | 50 mg daily |" in (sec2.raw_text or "")


def test_html_parser_strips_page_chrome():
    """Verify HTML parser excludes scripts, styles, navigation, and footers."""
    html_with_chrome = """
    <html>
    <head>
        <style>body { color: red; } .nav { display: flex; }</style>
        <script>console.log("analytics tracking code");</script>
    </head>
    <body>
        <nav>
            <a href="/home">Home</a>
            <a href="/products">Products</a>
        </nav>
        <header>
            <div>Portal Banner</div>
        </header>

        <h1>Warning and Precautions</h1>
        <p>Preserve vigilance for hypersensitivity reactions.</p>

        <footer>
            <p>Copyright 2026 Regulatory Agency. All rights reserved.</p>
        </footer>
    </body>
    </html>
    """

    parser = HtmlDocumentParser()
    doc = parser.parse(html_with_chrome)

    assert len(doc.sections) == 1
    sec = doc.sections[0]
    assert sec.heading_raw == "Warning and Precautions"
    assert "Preserve vigilance for hypersensitivity" in (sec.raw_text or "")

    # Ensure none of the chrome text exists in the parsed section text
    full_text = sec.raw_text or ""
    assert "analytics tracking code" not in full_text
    assert "color: red" not in full_text
    assert "Portal Banner" not in full_text
    assert "Copyright 2026" not in full_text


def test_html_parser_empty_and_graceful():
    """Verify HTML parser handles empty text and malformed unclosed tags safely."""
    parser = HtmlDocumentParser()

    empty_doc = parser.parse("", document_id="empty_html")
    assert len(empty_doc.sections) == 0

    unclosed_html = "<p>Paragraph without closing tag.<br>Next line.<div>Block text"
    doc = parser.parse(unclosed_html, document_id="unclosed_html")
    assert len(doc.sections) == 1
    assert "Paragraph without closing tag" in (doc.sections[0].raw_text or "")


# ============================================================================
# 6. PARSER FACTORY & DISPATCHER TESTS
# ============================================================================

def test_parser_factory_resolution():
    """Verify get_parser selects the appropriate parser based on file extension and signatures."""
    assert isinstance(get_parser(filename="label.txt"), TextDocumentParser)
    assert isinstance(get_parser(filename="guide.md"), MarkdownDocumentParser)
    assert isinstance(get_parser(filename="payload.json"), JsonDocumentParser)
    assert isinstance(get_parser(filename="report.xml"), XmlDocumentParser)
    assert isinstance(get_parser(filename="index.html"), HtmlDocumentParser)

    # Content signature dispatch without filename
    assert isinstance(get_parser(content='{"key": "value"}'), JsonDocumentParser)
    assert isinstance(get_parser(content='<?xml version="1.0"?><doc></doc>'), XmlDocumentParser)
    assert isinstance(get_parser(content='<!DOCTYPE html><html><body></body></html>'), HtmlDocumentParser)
    assert isinstance(get_parser(content='# Markdown Header\nSome text'), MarkdownDocumentParser)
    assert isinstance(get_parser(content='Simple plain text notes'), TextDocumentParser)


# ============================================================================
# 7. DETERMINISTIC REPEATED PARSING TESTS
# ============================================================================

@pytest.mark.parametrize("fmt,content,parser_cls", [
    ("txt", "1. WARNINGS\nDo not use with alcohol.", TextDocumentParser),
    ("md", "# 1. WARNINGS\nDo not use with alcohol.", MarkdownDocumentParser),
    ("json", '{"warnings": "Do not use with alcohol."}', JsonDocumentParser),
    ("xml", "<warnings>Do not use with alcohol.</warnings>", XmlDocumentParser),
    ("html", "<h1>Warnings</h1><p>Do not use with alcohol.</p>", HtmlDocumentParser),
])
def test_deterministic_repeated_parsing(fmt, content, parser_cls):
    """Verify that repeatedly parsing identical content yields identical section structures."""
    parser = parser_cls()
    doc1 = parser.parse(content, document_id="det_doc")
    doc2 = parser.parse(content, document_id="det_doc")

    assert len(doc1.sections) == len(doc2.sections)
    for s1, s2 in zip(doc1.sections, doc2.sections):
        assert s1.section_id == s2.section_id
        assert s1.heading_raw == s2.heading_raw
        assert s1.heading_normalized == s2.heading_normalized
        assert s1.raw_text == s2.raw_text
        assert s1.order_index == s2.order_index


# ============================================================================
# 8. REGULATORY CHUNKER COMPATIBILITY TESTS
# ============================================================================

@pytest.mark.parametrize("fmt,content,filename", [
    (
        "txt",
        "1. INDICATIONS AND USAGE\nDrug Alpha is indicated for hypertension.\nIt should be taken daily.\n",
        "label.txt",
    ),
    (
        "md",
        "# 1. INDICATIONS\nDrug Alpha is indicated for hypertension.\n\n| Param | Value |\n|---|---|\n| Dose | 10 mg |\n",
        "label.md",
    ),
    (
        "json",
        '{"indications": "Drug Alpha is indicated for hypertension.", "dosage": "Take 10 mg daily."}',
        "label.json",
    ),
    (
        "xml",
        "<label><indications><paragraph>Drug Alpha is indicated for hypertension.</paragraph></indications></label>",
        "label.xml",
    ),
    (
        "html",
        "<h1>Indications</h1><p>Drug Alpha is indicated for hypertension.</p><ul><li>Adults only</li></ul>",
        "label.html",
    ),
])
def test_parser_regulatory_chunker_compatibility(fmt, content, filename):
    """Verify that documents generated by all 5 parsers are cleanly processed by RegulatoryChunker."""
    doc = parse_regulatory_document(
        content=content,
        filename=filename,
        document_id=f"compat_{fmt}",
        document_name=f"Compatibility Test {fmt.upper()}",
    )

    chunker = RegulatoryChunker()
    chunks = chunker.chunk_document(doc)

    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.document_id == f"compat_{fmt}"
        assert chunk.section_id is not None
        assert chunk.chunk_id.startswith("chk_")
        assert len(chunk.content.strip()) > 0

        # Verify backward compatibility to_content_item conversion
        item = chunk.to_content_item()
        assert item.document_id == f"compat_{fmt}"
        assert item.text == chunk.content
