"""Request and response models for document ingestion and candidate discovery."""

from typing import List, Optional
from pydantic import BaseModel, Field

from app.models.content import RegulatoryContentItem


class DocumentIngestResponse(BaseModel):
    """Response returned upon ingesting a regulatory document or pasted text."""

    document_id: str = Field(..., description="Unique ingested document identifier")
    document_fingerprint: Optional[str] = Field(
        default=None,
        description="Deterministic document content fingerprint",
    )
    document_name: str = Field(..., description="Title of the ingested document")
    document_type: str = Field(..., description="Regulatory document type")
    jurisdiction: str = Field(..., description="Regulatory jurisdiction")
    sections_count: int = Field(..., description="Number of hierarchical sections parsed")
    chunks_count: int = Field(..., description="Number of candidate chunks registered in store")
    sections: List[RegulatoryContentItem] = Field(
        default_factory=list,
        description="Extracted regulatory sections and content items from ingested document",
    )
    source_repository: str = Field(
        default="InternalDraft",
        description="Source repository name",
    )
    message: str = Field(..., description="Human-readable ingestion status message")


class CandidateSearchRequest(BaseModel):
    """Request model for candidate discovery across ingested and live sources."""

    query: str = Field(default="", description="Search query string, drug name, or clinical phrase")
    source_filter: str = Field(
        default="all",
        description="Allowed source filter: 'all', 'ingested', 'internal', 'dailymed', 'openfda'",
    )
    section: Optional[str] = Field(default=None, description="Optional regulatory section filter")
    target_text: Optional[str] = Field(
        default=None,
        description="Optional target content snippet for relevance scoring and ranking",
    )
    top_k: int = Field(default=10, ge=1, le=50, description="Max candidates to return (1-50)")
    exclude_document_id: Optional[str] = Field(
        default=None,
        description="Optional document ID to exclude from candidate search results",
    )
    exclude_document_fingerprint: Optional[str] = Field(
        default=None,
        description="Optional document fingerprint to exclude from candidate search results",
    )
    document_id: Optional[str] = Field(
        default=None,
        description="Optional source document ID alias to exclude from candidate search results",
    )
    target_content_id: Optional[str] = Field(
        default=None,
        description="Optional target content ID to exclude from candidate search results",
    )
