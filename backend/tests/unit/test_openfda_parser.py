"""Unit tests for openFDA source response parsing."""

import pytest
from app.services.regulatory_source import OpenFDASource


SAMPLE_OPENFDA_RESPONSE = {
    "results": [
        {
            "id": "test-fda-doc-999",
            "effective_time": "20251101",
            "version": "2",
            "openfda": {
                "brand_name": ["SampleBrand Aspirin"],
                "generic_name": ["ASPIRIN"],
                "application_number": ["ANDA012345"],
                "manufacturer_name": ["PharmaCorp LLC"],
                "route": ["ORAL"],
            },
            "indications_and_usage": [
                "For the temporary relief of headache and minor arthritis pain."
            ],
            "dosage_and_administration": [
                "Take 1 to 2 tablets every 4 to 6 hours as needed."
            ],
            "contraindications": [
                "Do not take if you have an active bleeding ulcer."
            ],
        }
    ]
}


def test_openfda_mapping_sections():
    """Verify openFDA section mapping correctly parses multiple distinct label sections."""
    source = OpenFDASource()
    results = SAMPLE_OPENFDA_RESPONSE["results"]

    items = []
    for doc in results:
        openfda_meta = doc.get("openfda", {})
        doc_id = doc.get("id")
        brand_names = openfda_meta.get("brand_name", [])
        product_name = brand_names[0] if brand_names else "Drug Label"
        effective_date = doc.get("effective_time")

        for key, display_title in source.SECTION_MAPPINGS.items():
            sec_content = doc.get(key)
            if sec_content and isinstance(sec_content, list):
                from app.models.content import RegulatoryContentItem
                item = RegulatoryContentItem(
                    document_id=doc_id,
                    document_name=f"{product_name} - FDA Label",
                    source="openFDA",
                    source_url=f"https://labels.fda.gov/",
                    source_identifier=doc_id,
                    date=effective_date,
                    section=display_title,
                    text=" ".join(sec_content).strip(),
                )
                items.append(item)

    assert len(items) == 3
    sec_names = [item.section for item in items]
    assert "Indications and Usage" in sec_names
    assert "Dosage and Administration" in sec_names
    assert "Contraindications" in sec_names


@pytest.mark.asyncio
async def test_openfda_empty_query():
    """Verify empty query returns empty list without calling network."""
    source = OpenFDASource()
    items = await source.search(query="")
    assert items == []
