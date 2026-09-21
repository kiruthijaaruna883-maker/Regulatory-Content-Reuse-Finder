"""Unit tests for DailyMed source parsing logic."""

import pytest
from app.services.regulatory_source import DailyMedSource


SAMPLE_SPL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<document xmlns="urn:hl7-org:v3">
    <title>SAMPLE ASPIRIN LABEL</title>
    <component>
        <structuredBody>
            <component>
                <section ID="sec_dosage">
                    <code code="34068-7" displayName="DOSAGE &amp; ADMINISTRATION SECTION"/>
                    <title>Directions</title>
                    <text>
                        <paragraph>Drink a full glass of water with each dose.</paragraph>
                        <paragraph>Adults: 2 tablets every 4 hours. Do not exceed 8 tablets in 24 hours.</paragraph>
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


def test_dailymed_parse_spl_xml_success():
    """Verify DailyMed SPL XML parser extracts structured sections with LOINC and text."""
    source = DailyMedSource()
    items = source._parse_spl_xml(SAMPLE_SPL_XML, setid="test-set-123")

    assert len(items) == 2

    # Check dosage section
    dosage_sec = next(item for item in items if "DOSAGE" in (item.section or "").upper())
    assert dosage_sec.source == "DailyMed"
    assert dosage_sec.document_id == "test-set-123"
    assert dosage_sec.location == "34068-7"
    assert "Drink a full glass of water" in dosage_sec.text
    assert "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=test-set-123" == dosage_sec.source_url

    # Check indications section
    ind_sec = next(item for item in items if "INDICATIONS" in (item.section or "").upper())
    assert ind_sec.location == "34067-9"
    assert "relieves minor aches and pains" in ind_sec.text


def test_dailymed_parse_spl_xml_malformed():
    """Verify parser degrades safely on malformed XML without throwing unhandled exceptions."""
    source = DailyMedSource()
    items = source._parse_spl_xml("<malformed<xml>>>", setid="bad-xml")
    assert items == []


@pytest.mark.asyncio
async def test_dailymed_search_empty_query():
    """Verify searching with whitespace or empty query returns an empty list without calling API."""
    source = DailyMedSource()
    items = await source.search(query="   ")
    assert items == []
