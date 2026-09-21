"""Live external integration tests for DailyMed and openFDA APIs.

Verifies that the live external regulatory services respond with valid schemas and metadata.
"""

import pytest
from app.services.regulatory_source import DailyMedSource, OpenFDASource, RegulatorySourceService


@pytest.mark.asyncio
async def test_live_dailymed_search():
    """Verify live search against National Library of Medicine (NLM) DailyMed web service."""
    source = DailyMedSource()
    items = await source.search(query="aspirin", limit=2)

    assert len(items) > 0
    item = items[0]
    assert item.source == "DailyMed"
    assert item.source_identifier is not None
    assert item.source_url is not None
    assert "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=" in item.source_url
    assert item.document_name is not None
    assert len(item.text) > 0


@pytest.mark.asyncio
async def test_live_dailymed_health_check():
    """Verify live health check against DailyMed API."""
    source = DailyMedSource()
    status_res = await source.health_check()

    assert status_res["source"] == "DailyMed"
    assert status_res["status"] in ("healthy", "degraded")
    assert status_res.get("status_code") == 200


@pytest.mark.asyncio
async def test_live_openfda_search():
    """Verify live search against official FDA / openFDA drug label API."""
    source = OpenFDASource()
    items = await source.search(query="aspirin", limit=2)

    assert len(items) > 0
    item = items[0]
    assert item.source == "openFDA"
    assert item.source_identifier is not None
    assert item.section is not None
    assert len(item.text) > 0


@pytest.mark.asyncio
async def test_live_openfda_health_check():
    """Verify live health check against openFDA API."""
    source = OpenFDASource()
    status_res = await source.health_check()

    assert status_res["source"] == "openFDA"
    assert status_res["status"] in ("healthy", "degraded")
    assert status_res.get("status_code") == 200


@pytest.mark.asyncio
async def test_live_regulatory_service_unified_search():
    """Verify unified search querying both DailyMed and openFDA live."""
    service = RegulatorySourceService()
    result = await service.search(query="aspirin", source="all", limit=2)

    assert result.query == "aspirin"
    assert result.total_results > 0
    sources_represented = {item.source for item in result.items}
    # Both or at least one live source must be returned
    assert "DailyMed" in sources_represented or "openFDA" in sources_represented
