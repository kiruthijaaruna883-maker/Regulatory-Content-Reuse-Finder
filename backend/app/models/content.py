"""Pydantic data models for regulatory content, search requests, and results.

Preserves full source metadata and traceability without fabricating unavailable values.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class RegulatoryContentType(str, Enum):
    """Standardized regulatory content classification types."""

    DOSAGE_STATEMENT = "dosage_statement"
    INDICATION_STATEMENT = "indication_statement"
    POPULATION_STATEMENT = "population_statement"
    SAFETY_STATEMENT = "safety_statement"
    CLINICAL_STATEMENT = "clinical_statement"
    REGULATORY_STATEMENT = "regulatory_statement"
    STRUCTURED_FIELD = "structured_field"
    TABLE_CONTENT = "table_content"
    GENERAL_REGULATORY_CONTENT = "general_regulatory_content"


class KeyInformation(BaseModel):
    """Structured regulatory attributes extracted from regulatory text."""

    drug: Optional[str] = Field(default=None, description="Active drug or generic name")
    product: Optional[str] = Field(default=None, description="Commercial product or brand name")
    active_ingredient: Optional[str] = Field(default=None, description="Active chemical ingredient")
    population: Optional[str] = Field(default=None, description="Target patient population (e.g. Adults, Pediatric)")
    indication: Optional[str] = Field(default=None, description="Target clinical condition or usage")
    dose: Optional[str] = Field(default=None, description="Numerical dose quantity (e.g. 50 mg, 1 tablet)")
    dose_unit: Optional[str] = Field(default=None, description="Unit of measurement (e.g. mg, g, ml)")
    frequency: Optional[str] = Field(default=None, description="Dosing frequency or interval (e.g. once daily, every 4 hours)")
    route: Optional[str] = Field(default=None, description="Route of administration (e.g. Oral, Intravenous)")
    duration: Optional[str] = Field(default=None, description="Treatment duration (e.g. 7 days, up to 10 days)")
    age_group: Optional[str] = Field(default=None, description="Age subgroup specification (e.g. 18 years and older)")
    safety_information: Optional[str] = Field(default=None, description="Critical warning, caution, or contraindication")
    clinical_outcome: Optional[str] = Field(default=None, description="Expected clinical result or therapy goal")
    regulatory_terminology: Optional[str] = Field(default=None, description="Recognized regulatory phrase or heading")
    purpose: Optional[str] = Field(default=None, description="Clinical or regulatory purpose of statement")


class RegulatoryContentItem(BaseModel):
    """Normalized structured regulatory content item.

    Preserves full source provenance, clinical categorization, and metadata.
    Fields without known values default to None rather than fabricated data.
    """

    content_id: str = Field(
        default_factory=lambda: f"rc_{uuid4().hex[:12]}",
        description="Unique identifier for the content item",
    )
    document_id: Optional[str] = Field(
        default=None,
        description="Identifier of the containing document or package insert",
    )
    document_name: Optional[str] = Field(
        default=None,
        description="Title or label name of the regulatory document",
    )
    source: str = Field(
        ...,
        description="Live source origin (e.g., 'DailyMed', 'openFDA')",
    )
    source_url: Optional[str] = Field(
        default=None,
        description="Direct URL to the external regulatory record for traceability",
    )
    source_identifier: Optional[str] = Field(
        default=None,
        description="External source identifier (e.g. DailyMed Set ID, SPL ID, NDC)",
    )
    version: Optional[str] = Field(
        default=None,
        description="Document version or SPL version number",
    )
    date: Optional[str] = Field(
        default=None,
        description="Publication, approval, or effective date",
    )
    section: Optional[str] = Field(
        default=None,
        description="Standard regulatory section name (e.g. 'Indications and Usage', 'Dosage and Administration')",
    )
    subsection: Optional[str] = Field(
        default=None,
        description="Subsection or paragraph title within the section",
    )
    page: Optional[int] = Field(
        default=None,
        description="Page number if applicable and available",
    )
    location: Optional[str] = Field(
        default=None,
        description="Document location such as paragraph, table, or section identifier (NOT LOINC code)",
    )
    loinc_code: Optional[str] = Field(
        default=None,
        description="Standard LOINC section code when provided by regulatory source (kept separate from document location)",
    )
    content_type: Optional[str] = Field(
        default=None,
        description="Regulatory content classification (e.g. 'dosage_statement', 'indication_statement')",
    )
    product: Optional[str] = Field(
        default=None,
        description="Commercial product or brand name",
    )
    drug: Optional[str] = Field(
        default=None,
        description="Active substance or generic drug name",
    )
    population: Optional[str] = Field(
        default=None,
        description="Patient population (e.g., 'Adults', 'Pediatric', 'Geriatric') if specified",
    )
    indication: Optional[str] = Field(
        default=None,
        description="Therapeutic indication or usage condition",
    )
    dose: Optional[str] = Field(
        default=None,
        description="Recommended dose quantity",
    )
    frequency: Optional[str] = Field(
        default=None,
        description="Dosing interval or frequency",
    )
    route: Optional[str] = Field(
        default=None,
        description="Route of administration (e.g., 'Oral', 'Intravenous', 'Subcutaneous')",
    )
    purpose: Optional[str] = Field(
        default=None,
        description="Clinical purpose or therapeutic category",
    )
    text: str = Field(
        ...,
        description="Exact raw or extracted text content from the regulatory document",
    )
    key_information: Optional[KeyInformation] = Field(
        default=None,
        description="Structured key information entities extracted from text",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional non-standardized metadata preserved from source",
    )


class RegulatorySearchRequest(BaseModel):
    """Request model for searching live regulatory sources."""

    query: str = Field(..., min_length=1, max_length=500, description="Search term, drug name, or condition")
    source: str = Field(
        default="all",
        description="Source filter: 'all', 'dailymed', or 'openfda'",
    )
    section: Optional[str] = Field(
        default=None,
        description="Filter by regulatory section (e.g., 'dosage', 'indications', 'warnings')",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of results to retrieve per source",
    )


class RegulatorySearchResult(BaseModel):
    """Structured response container for regulatory search results."""

    query: str = Field(..., description="Original search query executed")
    total_results: int = Field(..., description="Total candidate items retrieved")
    source: str = Field(..., description="Source(s) queried ('all', 'DailyMed', 'openFDA')")
    items: List[RegulatoryContentItem] = Field(
        default_factory=list,
        description="Retrieved regulatory content items with provenance",
    )
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp of retrieval from live source",
    )
    errors: Optional[List[str]] = Field(
        default=None,
        description="Warnings or non-fatal source errors encountered during query",
    )
