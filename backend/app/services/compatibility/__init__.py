"""Compatibility adapter layer for Regulatory Content Reuse Finder (GPR).

Bridges Phase 2 regulatory models (RegulatoryDocument, RegulatorySection, RegulatoryChunk)
with existing GPR services expecting RegulatoryContentItem.
"""

from app.services.compatibility.regulatory_adapter import (
    adapt_for_comparison,
    adapt_for_retrieval,
    chunk_to_content_item,
    chunks_to_content_items,
    content_item_to_chunk,
    content_items_to_document,
    document_to_content_items,
    section_to_content_item,
)

__all__ = [
    "adapt_for_comparison",
    "adapt_for_retrieval",
    "chunk_to_content_item",
    "chunks_to_content_items",
    "content_item_to_chunk",
    "content_items_to_document",
    "document_to_content_items",
    "section_to_content_item",
]
