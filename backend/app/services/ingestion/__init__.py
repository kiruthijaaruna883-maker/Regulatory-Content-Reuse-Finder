"""Unified regulatory document ingestion package.

Exports:
- UnifiedIngestionService
- ingest_document
- ingest_and_chunk_document
"""

from app.services.ingestion.unified_ingestion import (
    UnifiedIngestionService,
    ingest_and_chunk_document,
    ingest_document,
)

__all__ = [
    "UnifiedIngestionService",
    "ingest_document",
    "ingest_and_chunk_document",
]
