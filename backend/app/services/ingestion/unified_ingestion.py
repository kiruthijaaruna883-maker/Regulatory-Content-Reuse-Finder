"""Unified regulatory document ingestion service.

Provides a single consistent entry point for ingesting multi-format regulatory documents
(TXT, Markdown, JSON, XML, HTML, PDF, DOCX) and normalizing them into Phase 1
RegulatoryDocument models compatible with downstream RegulatoryChunker.
"""

import hashlib
import io
from pathlib import Path
import re
from typing import Any, BinaryIO, Dict, List, Optional, TextIO, Tuple, Union
from uuid import uuid4

from app.models.document import (
    RegulatoryChunk,
    RegulatoryDocument,
    RegulatoryProvenance,
)
from app.services.chunking.regulatory_chunker import RegulatoryChunker
from app.services.parsers import BaseDocumentParser, get_parser

SCANNED_PLACEHOLDER_MARKERS = [
    "[scanned image-only pdf",
    "no digital text layer detected. image-only pdf",
]


def generate_document_fingerprint(
    raw_data: Union[str, bytes, io.IOBase, BinaryIO, TextIO, Any],
    parsed_doc: Optional[RegulatoryDocument] = None,
) -> str:
    """Generate a deterministic, stable content fingerprint for a regulatory document.

    Rules:
    1. For text-bearing documents: normalizes complete parsed document text (Unicode
       punctuation, stripping PDF page breadcrumbs '--- [Page X] ---', normalizing line
       endings, collapsing whitespace) and hashes the normalized text.
    2. For scanned / image-only documents without a digital text layer: hashes the verbatim
       raw file bytes instead of the static scanned-PDF placeholder text to avoid collisions.
    3. Never incorporates volatile metadata (filename, title, timestamps, product, ingredient).
    """
    # 1. Extract raw bytes from raw_data if available
    raw_bytes = b""
    if isinstance(raw_data, (bytes, bytearray)):
        raw_bytes = bytes(raw_data)
    elif isinstance(raw_data, str):
        raw_bytes = raw_data.encode("utf-8")
    elif hasattr(raw_data, "read"):
        try:
            curr_pos = raw_data.tell() if hasattr(raw_data, "tell") else None
            data = raw_data.read()
            if curr_pos is not None and hasattr(raw_data, "seek"):
                raw_data.seek(curr_pos)
            raw_bytes = data if isinstance(data, bytes) else str(data).encode("utf-8")
        except Exception:
            raw_bytes = b""

    # 2. Extract parsed document text
    extracted_text = ""
    if parsed_doc is not None:
        if parsed_doc.raw_content and parsed_doc.raw_content.strip():
            extracted_text = parsed_doc.raw_content
        elif parsed_doc.sections:
            extracted_text = "\n".join(s.raw_text for s in parsed_doc.sections if s.raw_text)
    elif isinstance(raw_data, str):
        extracted_text = raw_data

    # 3. Check for scanned / image-only / zero-digital-text
    is_scanned_or_empty = False
    if not extracted_text or not extracted_text.strip():
        is_scanned_or_empty = True
    else:
        lower_extracted = extracted_text.lower().strip()
        for marker in SCANNED_PLACEHOLDER_MARKERS:
            if marker in lower_extracted:
                is_scanned_or_empty = True
                break

    # If scanned/image-only or empty parsed text, hash raw binary bytes
    if is_scanned_or_empty:
        if raw_bytes:
            digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
            return f"fp_{digest}"
        return f"fp_{hashlib.sha256(b'').hexdigest()[:16]}"

    # 4. Text-bearing document normalization
    # Unicode punctuation replacements
    normalized = (
        extracted_text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u00a0", " ")
        .replace("\ufeff", "")
    )
    # Remove parser-specific PDF page markers e.g. "--- [Page 1] ---" or "[Page 1]"
    normalized = re.sub(r"---\s*\[Page\s+\d+\]\s*---", "", normalized)
    normalized = re.sub(r"\[Page\s+\d+\]", "", normalized)
    # Normalize line endings
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse repeated whitespace to single space and strip
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Re-verify that removing markers didn't reduce text to empty or scanned placeholder
    if not normalized or any(m in normalized.lower() for m in SCANNED_PLACEHOLDER_MARKERS):
        if raw_bytes:
            digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
            return f"fp_{digest}"

    payload = normalized.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"fp_{digest}"


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

        # 6. Generate and assign stable document fingerprint
        document.document_fingerprint = generate_document_fingerprint(
            raw_data=raw_data,
            parsed_doc=document,
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
