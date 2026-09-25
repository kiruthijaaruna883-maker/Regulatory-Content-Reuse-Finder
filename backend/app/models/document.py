"""Pydantic foundation data models for regulatory document hierarchy and chunking.

Defines the normalized regulatory document hierarchy:
RegulatoryDocument -> RegulatorySection (recursive) -> RegulatoryChunk
Preserves complete source provenance, context paths, and 100% backward compatibility
with existing RegulatoryContentItem via the to_content_item() adapter.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field
from app.models.content import KeyInformation, RegulatoryContentItem


class RegulatoryChunkType(str, Enum):
    """Standardized atomic chunk types."""

    PARAGRAPH = "paragraph"
    BULLET = "bullet"
    NUMBERED_ITEM = "numbered_item"
    TABLE_ROW = "table_row"
    STRUCTURED_FIELD = "structured_field"
    HEADING = "heading"


class CanonicalSectionConcept:
    """Extensible registry of canonical regulatory section concepts.

    Normalization is an internal engineering retrieval aid to correlate related
    sections across jurisdictions (e.g. US PLR Section 2 vs EU SmPC Section 4.2).
    It is NOT a regulatory or legal determination of statutory equivalence.
    """

    CONCEPT_INDICATIONS = "CONCEPT_INDICATIONS"
    CONCEPT_POSOLOGY_DOSAGE = "CONCEPT_POSOLOGY_DOSAGE"
    CONCEPT_DOSAGE_FORMS = "CONCEPT_DOSAGE_FORMS"
    CONCEPT_CONTRAINDICATIONS = "CONCEPT_CONTRAINDICATIONS"
    CONCEPT_WARNINGS = "CONCEPT_WARNINGS"
    CONCEPT_ADVERSE_REACTIONS = "CONCEPT_ADVERSE_REACTIONS"
    CONCEPT_DRUG_INTERACTIONS = "CONCEPT_DRUG_INTERACTIONS"
    CONCEPT_POPULATIONS = "CONCEPT_POPULATIONS"
    CONCEPT_OVERDOSAGE = "CONCEPT_OVERDOSAGE"
    CONCEPT_CLINICAL_PHARM = "CONCEPT_CLINICAL_PHARM"
    CONCEPT_STORAGE_HANDLING = "CONCEPT_STORAGE_HANDLING"

    # Extensible set of all registered concepts
    _ALL_CONCEPTS = {
        CONCEPT_INDICATIONS,
        CONCEPT_POSOLOGY_DOSAGE,
        CONCEPT_DOSAGE_FORMS,
        CONCEPT_CONTRAINDICATIONS,
        CONCEPT_WARNINGS,
        CONCEPT_ADVERSE_REACTIONS,
        CONCEPT_DRUG_INTERACTIONS,
        CONCEPT_POPULATIONS,
        CONCEPT_OVERDOSAGE,
        CONCEPT_CLINICAL_PHARM,
        CONCEPT_STORAGE_HANDLING,
    }

    @classmethod
    def register_concept(cls, concept_name: str) -> str:
        """Register a new custom or future canonical concept."""
        normalized = concept_name.strip().upper()
        cls._ALL_CONCEPTS.add(normalized)
        return normalized

    @classmethod
    def is_valid_concept(cls, concept_name: str) -> bool:
        """Check whether a concept is registered in the taxonomy."""
        return concept_name.strip().upper() in cls._ALL_CONCEPTS

    @classmethod
    def list_concepts(cls) -> List[str]:
        """List all currently registered canonical concepts."""
        return sorted(list(cls._ALL_CONCEPTS))


class RegulatoryProvenance(BaseModel):
    """Authoritative source provenance tracking origin, identity, and retrieval metadata.

    Preserves audit-ready traceability without fabricating unavailable values.
    """

    source_repository: str = Field(
        ...,
        description="Origin repository: 'DailyMed', 'openFDA', 'InternalDraft'",
    )
    source_identifier: Optional[str] = Field(
        default=None,
        description="External source identifier (e.g. Set ID, SPL ID, NDC, or internal document ID)",
    )
    source_url: Optional[str] = Field(
        default=None,
        description="Official direct URL to authoritative external record",
    )
    version: Optional[str] = Field(
        default=None,
        description="Source document version or SPL revision number",
    )
    publication_date: Optional[str] = Field(
        default=None,
        description="Publication, approval, or effective date string",
    )
    loinc_code: Optional[str] = Field(
        default=None,
        description="Standard LOINC section code when provided by regulatory source",
    )
    exact_location: Optional[str] = Field(
        default=None,
        description="Document location description (e.g. 'Section 2, Paragraph 1', 'Table 1, Row 3')",
    )
    retrieval_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timezone-aware UTC timestamp of retrieval",
    )


class RegulatoryTableRow(BaseModel):
    """Structured clinical table row preserving column header to cell value mapping."""

    row_index: int = Field(default=0, description="0-indexed position within the table")
    cells: List[str] = Field(
        default_factory=list,
        description="Raw cell values in column order",
    )
    row_dict: Dict[str, str] = Field(
        default_factory=dict,
        description="Explicit mapping of column header -> cell value",
    )


class RegulatoryTable(BaseModel):
    """Structured clinical table container holding headers and key-value rows."""

    table_id: str = Field(
        default_factory=lambda: f"tbl_{uuid4().hex[:8]}",
        description="Unique identifier for the table",
    )
    section_id: str = Field(..., description="ID of containing section")
    table_title: Optional[str] = Field(
        default=None,
        description="Clinical table caption or title",
    )
    headers: List[str] = Field(
        default_factory=list,
        description="Column header names in order",
    )
    raw_markdown: Optional[str] = Field(
        default=None,
        description="Full markdown representation of the table",
    )
    rows: List[RegulatoryTableRow] = Field(
        default_factory=list,
        description="Structured table rows preserving column-value relationships",
    )


class RegulatoryChunk(BaseModel):
    """Atomic retrievable regulatory content unit with complete context preservation.

    Maintains content integrity (raw source text is never mutated for embeddings).
    Provides an adapter to_content_item() for 100% backward compatibility with
    existing GPR services, routes, and agents.
    """

    chunk_id: str = Field(
        default_factory=lambda: f"chk_{uuid4().hex[:10]}",
        description="Unique atomic chunk identifier",
    )
    document_id: str = Field(..., description="Foreign key to containing RegulatoryDocument")
    section_id: str = Field(..., description="Foreign key to immediate RegulatorySection")
    parent_chunk_id: Optional[str] = Field(
        default=None,
        description="Parent chunk ID (e.g. introductory stem sentence for child bullets)",
    )
    chunk_type: str = Field(
        default="paragraph",
        description="Chunk granularity: 'paragraph', 'bullet', 'numbered_item', 'table_row', 'structured_field', 'heading'",
    )
    order_index: int = Field(default=0, description="Sequential outline order within section")
    structure_path: str = Field(
        default="",
        description="Full structural breadcrumb path (e.g. 'Document > Section > Subsection > Table 1 > Row 2')",
    )

    # Content Integrity Fields
    content: str = Field(
        ...,
        description="Verbatim exact source text. NEVER mutated by context injection or truncated.",
    )
    normalized_content: Optional[str] = Field(
        default=None,
        description="Context-enriched text representation intended for vector embeddings and search.",
    )

    # Inherited Document Metadata (Lightweight for retrieval and filtering)
    document_name: Optional[str] = Field(default=None, description="Title of parent document")
    document_type: Optional[str] = Field(
        default=None,
        description="Regulatory document category (e.g. 'REGULATORY_LABEL', 'CORE_DATA_SHEET', 'INVESTIGATOR_BROCHURE')",
    )
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Regulatory authority domain (e.g. 'US_FDA', 'EMA', 'MHRA', 'PMDA', 'ICH', 'GLOBAL')",
    )
    product: Optional[str] = Field(default=None, description="Commercial product or brand name")
    active_ingredient: Optional[str] = Field(default=None, description="Active chemical substance or generic name")

    # Inherited Section Metadata
    section_title: Optional[str] = Field(default=None, description="Raw authored section title")
    section_number: Optional[str] = Field(default=None, description="Outline section number (e.g. '4.2', '2.1')")
    normalized_section: Optional[str] = Field(
        default=None,
        description="Canonical concept tag (e.g. 'CONCEPT_POSOLOGY_DOSAGE')",
    )

    # Clinical Entities
    key_information: Optional[KeyInformation] = Field(
        default=None,
        description="Clinical entities extracted for this specific atomic chunk",
    )

    # Provenance Attributes
    source: str = Field(
        default="Internal",
        description="Origin repository: 'DailyMed', 'openFDA', 'InternalDraft'",
    )
    source_identifier: Optional[str] = Field(
        default=None,
        description="External source identifier (e.g. Set ID, SPL ID, or document ID)",
    )
    source_url: Optional[str] = Field(
        default=None,
        description="Direct URL to external regulatory record for audit traceability",
    )
    version: Optional[str] = Field(default=None, description="Document revision string")
    publication_date: Optional[str] = Field(default=None, description="Approval or publication date")
    exact_location: Optional[str] = Field(
        default=None,
        description="Exact physical location (e.g. 'Paragraph 2', 'Table 1, Row 3')",
    )
    loinc_code: Optional[str] = Field(
        default=None,
        description="Standard LOINC section code",
    )

    def to_content_item(self) -> RegulatoryContentItem:
        """Backward-compatibility adapter converting RegulatoryChunk to RegulatoryContentItem.

        Ensures zero breaking changes for existing routes, vector store, matcher, and agents.
        """
        # Preserves all extra chunk metadata inside the existing metadata dict
        meta: Dict[str, Any] = {
            "chunk_id": self.chunk_id,
            "section_id": self.section_id,
            "parent_chunk_id": self.parent_chunk_id,
            "structure_path": self.structure_path,
            "normalized_content": self.normalized_content,
            "normalized_section": self.normalized_section,
            "jurisdiction": self.jurisdiction,
            "document_type": self.document_type,
            "order_index": self.order_index,
        }

        # Extract top-level clinical entity fields from key_information if present
        population = self.key_information.population if self.key_information else None
        indication = self.key_information.indication if self.key_information else None
        dose = self.key_information.dose if self.key_information else None
        frequency = self.key_information.frequency if self.key_information else None
        route = self.key_information.route if self.key_information else None
        purpose = self.key_information.purpose if self.key_information else None

        return RegulatoryContentItem(
            content_id=self.chunk_id,
            document_id=self.document_id,
            document_name=self.document_name,
            source=self.source,
            source_url=self.source_url,
            source_identifier=self.source_identifier,
            version=self.version,
            date=self.publication_date,
            section=self.section_title,
            subsection=self.section_number,
            location=self.exact_location,
            loinc_code=self.loinc_code,
            content_type=self.chunk_type,
            product=self.product,
            drug=self.active_ingredient,
            population=population,
            indication=indication,
            dose=dose,
            frequency=frequency,
            route=route,
            purpose=purpose,
            text=self.content,
            key_information=self.key_information,
            metadata=meta,
        )


class RegulatorySection(BaseModel):
    """Hierarchical section container supporting multi-jurisdictional outlines.

    Supports recursive section nesting (subsections) and contains atomic RegulatoryChunks.
    """

    section_id: str = Field(
        default_factory=lambda: f"sec_{uuid4().hex[:8]}",
        description="Unique identifier for the section",
    )
    parent_section_id: Optional[str] = Field(
        default=None,
        description="ID of parent section if this is a subsection",
    )
    section_number: Optional[str] = Field(
        default=None,
        description="Source outline number (e.g. '4.2', '2.1', 'Section 1')",
    )
    heading_raw: str = Field(
        ...,
        description="Exact authored heading from the source document (e.g. '4.2 Posology and method of administration')",
    )
    heading_normalized: Optional[str] = Field(
        default=None,
        description="Internal canonical concept used for search and alignment (e.g. 'CONCEPT_POSOLOGY_DOSAGE')",
    )
    order_index: int = Field(default=0, description="Sequential order within parent")
    loinc_code: Optional[str] = Field(
        default=None,
        description="Official LOINC section code when provided by regulatory source",
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Full unsegmented body text of this section",
    )
    chunks: List[RegulatoryChunk] = Field(
        default_factory=list,
        description="Atomic retrievable chunks contained directly in this section",
    )
    subsections: List["RegulatorySection"] = Field(
        default_factory=list,
        description="Nested child subsections",
    )


class RegulatoryDocument(BaseModel):
    """Top-level document container holding dossier identity, administrative metadata,
    provenance, and the hierarchical section tree.
    """

    document_id: str = Field(
        default_factory=lambda: f"doc_{uuid4().hex[:10]}",
        description="Unique document identifier",
    )
    title: str = Field(..., description="Formal document title")
    document_type: str = Field(
        default="REGULATORY_LABEL",
        description="Extensible document category: 'REGULATORY_LABEL', 'CORE_DATA_SHEET', 'INVESTIGATOR_BROCHURE', 'CLINICAL_SUMMARY', 'GENERAL_NARRATIVE'",
    )
    jurisdiction: str = Field(
        default="US_FDA",
        description="Regulatory jurisdiction domain: 'US_FDA', 'EMA', 'MHRA', 'PMDA', 'ICH', 'GLOBAL'",
    )
    product_name: Optional[str] = Field(default=None, description="Commercial product or brand name")
    active_ingredient: Optional[str] = Field(default=None, description="Active chemical ingredient or generic substance")
    application_number: Optional[str] = Field(default=None, description="Regulatory submission number (e.g. NDA, BLA, MAA)")
    manufacturer: Optional[str] = Field(default=None, description="Sponsoring authorization holder or company name")
    version: Optional[str] = Field(default="1.0", description="Dossier or label revision string")
    effective_date: Optional[str] = Field(default=None, description="Approval or publication date string")
    provenance: RegulatoryProvenance = Field(..., description="Authoritative origin provenance")
    sections: List[RegulatorySection] = Field(
        default_factory=list,
        description="Hierarchical sections belonging to this document",
    )
    raw_content: Optional[str] = Field(
        default=None,
        description="Optional complete raw text of the entire document prior to segmentation",
    )


# Rebuild recursive models for Pydantic v2
RegulatorySection.model_rebuild()
RegulatoryDocument.model_rebuild()
