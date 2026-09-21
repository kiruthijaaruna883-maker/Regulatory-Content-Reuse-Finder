"""Regulatory sources router module.

Exposes live search and retrieval endpoints connecting to DailyMed and openFDA.
Preserves full provenance, source URLs, and metadata.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.models.content import RegulatorySearchResult
from app.services.regulatory_source import DailyMedSource, OpenFDASource, RegulatorySourceService

router = APIRouter(prefix="/regulatory", tags=["Regulatory Sources"])

# Singleton service instance
source_service = RegulatorySourceService()


@router.get(
    "/search",
    response_model=RegulatorySearchResult,
    summary="Live search across regulatory sources (DailyMed, openFDA)",
    description="Query live external regulatory sources on demand. Preserves all available provenance metadata.",
)
async def search_regulatory_sources(
    query: str = Query(..., min_length=1, description="Drug name, active ingredient, or medical query"),
    source: str = Query(
        "all",
        pattern="^(all|dailymed|openfda)$",
        description="Target source: 'all', 'dailymed', or 'openfda'",
    ),
    section: Optional[str] = Query(None, description="Optional regulatory section filter"),
    limit: int = Query(10, ge=1, le=50, description="Max results per source"),
) -> RegulatorySearchResult:
    """Execute live query against configured regulatory sources."""
    try:
        result = await source_service.search(
            query=query,
            source=source,
            section=section,
            limit=limit,
        )
        return result
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Live regulatory service request timed out: {exc}",
        )
    except ConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Live regulatory service is temporarily unavailable: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred executing regulatory search: {exc}",
        )


@router.get(
    "/document/{source}/{identifier}",
    summary="Retrieve detailed regulatory document sections by identifier",
    description="Fetches live SPL XML sections or openFDA document details by Set ID or record ID.",
)
async def get_regulatory_document(
    source: str,
    identifier: str,
) -> Dict[str, Any]:
    """Fetch live document details for a specific external identifier."""
    norm_source = source.lower()
    if norm_source == "dailymed":
        items = await source_service.dailymed.get_document_details(identifier)
        return {
            "source": "DailyMed",
            "identifier": identifier,
            "sections_count": len(items),
            "sections": [item.model_dump() for item in items],
        }
    elif norm_source == "openfda":
        items = await source_service.openfda.get_document_details(identifier)
        return {
            "source": "openFDA",
            "identifier": identifier,
            "sections_count": len(items),
            "sections": [item.model_dump() for item in items],
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown regulatory source '{source}'. Must be 'dailymed' or 'openfda'.",
        )


@router.get(
    "/sources/status",
    summary="Check live connectivity status of DailyMed and openFDA sources",
)
async def check_sources_status() -> Dict[str, Any]:
    """Return health and latency check results for live external sources."""
    return await source_service.check_all_sources_health()
