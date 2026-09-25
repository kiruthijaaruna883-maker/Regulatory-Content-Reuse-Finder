"""Unified regulatory document ingestion service.

Provides a single consistent entry point for ingesting multi-format regulatory documents
(TXT, Markdown, JSON, XML, HTML, PDF, DOCX) and normalizing them into Phase 1
RegulatoryDocument models compatible with downstream RegulatoryChunker.
"""

import io
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, TextIO, Tuple, Union
from uuid import uuid4

from app.models.document import (
    RegulatoryChunk,
    RegulatoryDocument,
    RegulatoryProvenance,
)
from app.services.chunking.regulatory_chunker import RegulatoryChunker
from app.services.parsers import BaseDocumentParser, get_parser


class UnifiedIngestionService:
    """Unified ingestion service routing multi-format documents to their respective parsers."""

    def __init__(self, default_chunker: Optional[RegulatoryChunker] = None):
        self.chunker = default_chunker or RegulatoryChunker()

    def ingest_document(
        self,
        content: Union[str, bytes, io.IOBase, BinaryIO, TextIO],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        provenance: Optional[RegulatoryProvenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegulatoryDocument:
        """Ingest any supported regulatory document and normalize to a RegulatoryDocument container.

        Args:
            content: Raw string, bytes, or file-like object containing document data.
            filename: Optional source filename (used for extension-based format resolution).
            mime_type: Optional MIME content-type string.
            document_id: Optional caller-specified document identifier.
            document_name: Optional formal document title.
            provenance: Optional authoritative provenance object.
            metadata: Optional dictionary of domain or administrative metadata.

        Returns:
            Structured RegulatoryDocument with section hierarchy and provenance.

        Raises:
            ValueError: If the document format is unsupported or the content is malformed.
        """
        # 1. Unpack file-like objects if provided
        raw_data, extracted_filename = self._extract_content(content)
        effective_filename = filename or extracted_filename

        # Clean/sanitize filename path if full path was provided
        if effective_filename:
            effective_filename = Path(effective_filename).name

        # 2. Derive document identity and title if not specified
        meta = dict(metadata or {})
        doc_id = document_id or meta.get("document_id") or f"doc_{uuid4().hex[:10]}"
        doc_title = document_name or meta.get("document_name") or meta.get("title")

        if not doc_title and effective_filename:
            # Use base filename without extension as sensible document title
            doc_title = Path(effective_filename).stem.replace("_", " ").title()

        # 3. Resolve provenance
        prov = provenance or RegulatoryProvenance(
            source_repository=meta.get("source", "InternalDraft"),
            source_identifier=meta.get("source_identifier", doc_id),
            source_url=meta.get("source_url") or (f"file://{effective_filename}" if effective_filename else None),
            version=meta.get("version", "1.0"),
            publication_date=meta.get("effective_date"),
        )

        # 4. Identify parser using existing parser registry (single source of truth)
        parser = get_parser(
            content=raw_data,
            filename=effective_filename,
            mime_type=mime_type,
            raise_on_unsupported=True,
        )

        # 5. Delegate format-specific parsing to the resolved parser
        document = parser.parse(
            content=raw_data,
            document_id=doc_id,
            document_name=doc_title,
            provenance=prov,
            metadata=meta,
        )

        return document

    def ingest_and_chunk_document(
        self,
        content: Union[str, bytes, io.IOBase, BinaryIO, TextIO],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        provenance: Optional[RegulatoryProvenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
        chunker: Optional[RegulatoryChunker] = None,
    ) -> Tuple[RegulatoryDocument, List[RegulatoryChunk]]:
        """Convenience method executing unified ingestion followed by regulatory chunking.

        Returns:
            Tuple of (RegulatoryDocument, List[RegulatoryChunk]).
        """
        doc = self.ingest_document(
            content=content,
            filename=filename,
            mime_type=mime_type,
            document_id=document_id,
            document_name=document_name,
            provenance=provenance,
            metadata=metadata,
        )

        active_chunker = chunker or self.chunker
        chunks = active_chunker.chunk_document(doc)
        return doc, chunks

    @staticmethod
    def _extract_content(
        content: Union[str, bytes, io.IOBase, BinaryIO, TextIO],
    ) -> Tuple[Union[str, bytes], Optional[str]]:
        """Extract raw bytes or string from file-like objects or direct buffers."""
        filename = None
        if hasattr(content, "read"):
            if hasattr(content, "name") and isinstance(content.name, str):
                filename = content.name
            raw = content.read()
            return raw, filename
        return content, None


# Global singleton instance for functional module-level entry points
_default_ingestion_service = UnifiedIngestionService()


def ingest_document(
    content: Union[str, bytes, io.IOBase, BinaryIO, TextIO],
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    document_id: Optional[str] = None,
    document_name: Optional[str] = None,
    provenance: Optional[RegulatoryProvenance] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> RegulatoryDocument:
    """Module-level convenience entry point for unified document ingestion."""
    return _default_ingestion_service.ingest_document(
        content=content,
        filename=filename,
        mime_type=mime_type,
        document_id=document_id,
        document_name=document_name,
        provenance=provenance,
        metadata=metadata,
    )


def ingest_and_chunk_document(
    content: Union[str, bytes, io.IOBase, BinaryIO, TextIO],
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    document_id: Optional[str] = None,
    document_name: Optional[str] = None,
    provenance: Optional[RegulatoryProvenance] = None,
    metadata: Optional[Dict[str, Any]] = None,
    chunker: Optional[RegulatoryChunker] = None,
) -> Tuple[RegulatoryDocument, List[RegulatoryChunk]]:
    """Module-level convenience entry point for ingestion followed by regulatory chunking."""
    return _default_ingestion_service.ingest_and_chunk_document(
        content=content,
        filename=filename,
        mime_type=mime_type,
        document_id=document_id,
        document_name=document_name,
        provenance=provenance,
        metadata=metadata,
        chunker=chunker,
    )
