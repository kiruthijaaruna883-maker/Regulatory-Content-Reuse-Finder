"""Ingested regulatory document candidate store module.

Maintains in-memory/session storage of parsed and chunked regulatory documents
produced by Phase 2 UnifiedIngestionService and RegulatoryChunker.
Exposes chunks as candidate items for Phase 3 retrieval and multi-dimensional comparison,
while remaining logically decoupled from ephemeral vector-store query indexes.
Preserves full Phase 1 & 2 hierarchy, structure paths, and source provenance
without fabricating missing metadata.
"""

import io
import logging
import re
import threading
from typing import Any, BinaryIO, Dict, List, Optional, Sequence, TextIO, Tuple, Union

from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document import (
    RegulatoryChunk,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
    RetainedSourceDocument,
)
from app.services.chunking.regulatory_chunker import RegulatoryChunker
from app.services.compatibility.regulatory_adapter import (
    _collect_chunks_recursive,
    chunk_to_content_item,
)

logger = logging.getLogger("candidate_store")


def resolve_file_format(
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    content: Optional[Union[bytes, str]] = None,
    specified_format: Optional[str] = None,
) -> str:
    """Deterministically resolve file format / extension string (e.g. 'docx', 'pdf', 'txt', 'doc')."""
    # 1. Specified format override if valid
    if specified_format and specified_format.strip():
        clean = specified_format.strip().lower().lstrip(".")
        if clean:
            return clean

    # 2. Extract from filename extension
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].strip().lower()
        if ext:
            if ext == "markdown":
                return "md"
            if ext == "htm":
                return "html"
            return ext

    # 3. Derive from MIME type
    if mime_type and mime_type.strip():
        mt = mime_type.strip().lower()
        if "pdf" in mt:
            return "pdf"
        if "wordprocessingml" in mt or "docx" in mt:
            return "docx"
        if "msword" in mt or "application/doc" in mt:
            return "doc"
        if "markdown" in mt:
            return "md"
        if "json" in mt:
            return "json"
        if "xml" in mt:
            return "xml"
        if "html" in mt:
            return "html"
        if "plain" in mt or "text/" in mt:
            return "txt"

    # 4. Content signature magic bytes inspection
    if content:
        raw_b = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        if raw_b.startswith(b"%PDF-"):
            return "pdf"
        if raw_b.startswith(b"PK\x03\x04") and b"word/document.xml" in raw_b[:4096]:
            return "docx"
        if raw_b.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return "doc"
        if raw_b.strip().startswith((b"{", b"[")):
            try:
                import json
                json.loads(raw_b.decode("utf-8"))
                return "json"
            except Exception:
                pass
        if raw_b.strip().startswith(b"<") and b">" in raw_b[:100]:
            if b"<html" in raw_b.lower() or b"<!doctype html" in raw_b.lower():
                return "html"
            return "xml"

    # 5. Default fallback
    return "txt"


class IngestedDocumentCandidateStore:
    """Session candidate repository for ingested regulatory documents and chunks.

    Decoupled from ephemeral vector store query indexes to prevent ingested candidates
    from being erased when the temporary query vector index is cleared.
    Retains immutable raw source document bytes for future server-side corrected-document generation.
    """

    def __init__(self, default_chunker: Optional[RegulatoryChunker] = None):
        self._documents: Dict[str, RegulatoryDocument] = {}
        self._chunks: Dict[str, RegulatoryChunk] = {}
        self._content_items: Dict[str, RegulatoryContentItem] = {}
        self._doc_to_chunks: Dict[str, List[str]] = {}
        self._source_documents: Dict[str, RetainedSourceDocument] = {}
        self._lock = threading.RLock()
        self._chunker = default_chunker or RegulatoryChunker()

    def store_source_document(
        self,
        document_id: str,
        source_bytes: Union[bytes, str],
        filename: Optional[str] = None,
        file_format: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> RetainedSourceDocument:
        """Store original uploaded document bytes immutably for a document_id."""
        with self._lock:
            if isinstance(source_bytes, str):
                raw_b = source_bytes.encode("utf-8")
            else:
                raw_b = bytes(source_bytes)

            eff_filename = filename or f"{document_id}.txt"
            eff_format = resolve_file_format(
                filename=eff_filename,
                mime_type=mime_type,
                content=raw_b,
                specified_format=file_format,
            )

            record = RetainedSourceDocument(
                document_id=document_id,
                filename=eff_filename,
                file_format=eff_format,
                source_bytes=raw_b,
            )
            self._source_documents[document_id] = record
            return record

    def get_source_document(self, document_id: str) -> Optional[RetainedSourceDocument]:
        """Retrieve the retained source document record for a document_id."""
        with self._lock:
            return self._source_documents.get(document_id)

    def has_source_document(self, document_id: str) -> bool:
        """Check whether source document bytes are retained for a document_id."""
        with self._lock:
            return document_id in self._source_documents

    def add_document(
        self,
        document: RegulatoryDocument,
        chunks: Optional[Sequence[RegulatoryChunk]] = None,
        source_bytes: Optional[Union[bytes, str]] = None,
        filename: Optional[str] = None,
        file_format: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> List[RegulatoryChunk]:
        """Store an ingested RegulatoryDocument and register its RegulatoryChunks as candidates.

        If source_bytes is provided, preserves the exact original document bytes and format
        metadata for future server-side corrected document generation.

        Returns:
            List of stored RegulatoryChunk objects.
        """
        with self._lock:
            # 1. Resolve chunks
            effective_chunks: List[RegulatoryChunk] = []
            if chunks is not None and len(chunks) > 0:
                effective_chunks = list(chunks)
            else:
                existing_chunks = _collect_chunks_recursive(document.sections)
                if existing_chunks:
                    effective_chunks = existing_chunks
                elif document.sections or (document.raw_content and document.raw_content.strip()):
                    effective_chunks = self._chunker.chunk_document(document)

            # 2. Store document container
            self._documents[document.document_id] = document
            self._doc_to_chunks[document.document_id] = []

            # 3. Store chunks and adapt to RegulatoryContentItem for retrieval
            for chunk in effective_chunks:
                self._chunks[chunk.chunk_id] = chunk
                self._doc_to_chunks[document.document_id].append(chunk.chunk_id)
                self._content_items[chunk.chunk_id] = chunk_to_content_item(chunk)

            # 4. Retain original source bytes if provided
            if source_bytes is not None:
                self.store_source_document(
                    document_id=document.document_id,
                    source_bytes=source_bytes,
                    filename=filename,
                    file_format=file_format,
                    mime_type=mime_type,
                )

            logger.info(
                "Ingested document '%s' (ID: %s) registered with %d chunk(s) in candidate store.",
                document.title,
                document.document_id,
                len(effective_chunks),
            )
            return effective_chunks

    def add_chunk(self, chunk: RegulatoryChunk) -> RegulatoryContentItem:
        """Store a single RegulatoryChunk as a candidate."""
        with self._lock:
            self._chunks[chunk.chunk_id] = chunk
            if chunk.document_id:
                self._doc_to_chunks.setdefault(chunk.document_id, []).append(chunk.chunk_id)
            item = chunk_to_content_item(chunk)
            self._content_items[chunk.chunk_id] = item
            return item

    def add_chunks(self, chunks: Sequence[RegulatoryChunk]) -> List[RegulatoryContentItem]:
        """Store a sequence of RegulatoryChunks as candidates."""
        with self._lock:
            return [self.add_chunk(c) for c in chunks]

    def ingest_and_store(
        self,
        content: Union[str, bytes, io.IOBase, BinaryIO, TextIO],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        provenance: Optional[RegulatoryProvenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[RegulatoryDocument, List[RegulatoryChunk]]:
        """Ingest a multi-format document via Phase 2 UnifiedIngestionService and store it.

        Supports TXT, Markdown, JSON, XML, HTML, PDF, and DOCX.
        Preserves original source bytes in candidate store for future document correction.
        """
        from app.services.ingestion.unified_ingestion import (
            UnifiedIngestionService,
            ingest_and_chunk_document,
        )

        raw_data, extracted_fn = UnifiedIngestionService._extract_content(content)
        effective_fn = filename or extracted_fn

        doc, chunks = ingest_and_chunk_document(
            content=raw_data,
            filename=effective_fn,
            mime_type=mime_type,
            document_id=document_id,
            document_name=document_name,
            provenance=provenance,
            metadata=metadata,
            chunker=self._chunker,
        )
        self.add_document(
            doc,
            chunks,
            source_bytes=raw_data if isinstance(raw_data, (bytes, str)) else None,
            filename=effective_fn,
            mime_type=mime_type,
        )
        return doc, chunks

    def get_document(self, document_id: str) -> Optional[RegulatoryDocument]:
        """Retrieve stored RegulatoryDocument by document_id."""
        with self._lock:
            return self._documents.get(document_id)

    def get_chunk(self, chunk_id: str) -> Optional[RegulatoryChunk]:
        """Retrieve stored RegulatoryChunk by chunk_id."""
        with self._lock:
            return self._chunks.get(chunk_id)

    def get_content_item(self, chunk_id: str) -> Optional[RegulatoryContentItem]:
        """Retrieve adapted RegulatoryContentItem candidate by chunk_id."""
        with self._lock:
            return self._content_items.get(chunk_id)

    def list_documents(self) -> List[RegulatoryDocument]:
        """List all stored regulatory documents."""
        with self._lock:
            return list(self._documents.values())

    def list_chunks(self, document_id: Optional[str] = None) -> List[RegulatoryChunk]:
        """List stored RegulatoryChunks, optionally filtered by document_id."""
        with self._lock:
            if document_id:
                chunk_ids = self._doc_to_chunks.get(document_id, [])
                return [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]
            return list(self._chunks.values())

    def list_content_items(self, document_id: Optional[str] = None) -> List[RegulatoryContentItem]:
        """List stored candidate items as RegulatoryContentItems, optionally filtered by document_id."""
        with self._lock:
            if document_id:
                chunk_ids = self._doc_to_chunks.get(document_id, [])
                return [self._content_items[cid] for cid in chunk_ids if cid in self._content_items]
            return list(self._content_items.values())

    def remove_document(self, document_id: str) -> bool:
        """Remove a document and its associated chunks from the candidate store."""
        with self._lock:
            if document_id not in self._documents:
                return False
            del self._documents[document_id]
            self._source_documents.pop(document_id, None)
            chunk_ids = self._doc_to_chunks.pop(document_id, [])
            for cid in chunk_ids:
                self._chunks.pop(cid, None)
                self._content_items.pop(cid, None)
            return True

    def clear(self) -> None:
        """Clear all stored documents, chunks, and candidate items from the store."""
        with self._lock:
            self._documents.clear()
            self._chunks.clear()
            self._content_items.clear()
            self._doc_to_chunks.clear()
            self._source_documents.clear()
            logger.info("Ingested document candidate store cleared.")

    def count_documents(self) -> int:
        """Return total count of stored regulatory documents."""
        with self._lock:
            return len(self._documents)

    def count_chunks(self) -> int:
        """Return total count of stored regulatory candidate chunks."""
        with self._lock:
            return len(self._chunks)

    def search(
        self,
        query: Optional[str] = None,
        section: Optional[str] = None,
        limit: int = 10,
        target_text: Optional[str] = None,
        exclude_document_id: Optional[str] = None,
        exclude_content_id: Optional[str] = None,
    ) -> List[RegulatoryContentItem]:
        """Query stored candidates against query string, target text, and optional section filter.

        Preserves all Phase 2 traceability attributes (document identity, exact location,
        page numbers, structure paths, LOINC codes, clinical entities) without fabricating data.

        Returns:
            List of matching RegulatoryContentItem candidates ordered by relevance.
        """
        with self._lock:
            if not self._content_items:
                return []

            clean_query = (query or "").strip().lower()
            clean_section = (section or "").strip().lower()
            clean_target = (target_text or "").strip().lower()

            q_tokens = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", clean_query)) if clean_query else set()
            t_tokens = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", clean_target)) if clean_target else set()

            scored_items: List[Tuple[RegulatoryContentItem, float]] = []

            for item in self._content_items.values():
                if exclude_document_id and item.document_id == exclude_document_id:
                    continue

                if exclude_content_id and item.content_id == exclude_content_id:
                    continue

                item_text_lower = item.text.lower()
                item_tokens = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", item_text_lower))
                score = 0.0

                # 1. Query matching
                if clean_query:
                    # Direct substring match
                    if clean_query in item_text_lower:
                        score += 4.0
                    if item.drug and clean_query in item.drug.lower():
                        score += 5.0
                    if item.product and clean_query in item.product.lower():
                        score += 3.0
                    if item.indication and clean_query in item.indication.lower():
                        score += 3.0
                    # Token overlap
                    if q_tokens:
                        overlap = q_tokens.intersection(item_tokens)
                        score += len(overlap) * 1.5

                # 2. Target text token overlap (Jaccard similarity)
                if t_tokens:
                    inter = t_tokens.intersection(item_tokens)
                    union = t_tokens.union(item_tokens)
                    if union:
                        jaccard = len(inter) / len(union)
                        score += jaccard * 3.0

                # 3. Section alignment
                if clean_section:
                    item_sec = (item.section or "").lower()
                    item_subsec = (item.subsection or "").lower()
                    if clean_section in item_sec or item_sec in clean_section or clean_section in item_subsec:
                        score += 2.5

                # 4. Default score if no query/target/section criteria specified
                if not clean_query and not clean_target and not clean_section:
                    score = 1.0

                if score > 0.0:
                    scored_items.append((item, score))

            if not scored_items:
                return []

            # Sort descending by relevance score
            scored_items.sort(key=lambda x: x[1], reverse=True)
            return [it for it, _ in scored_items[:limit]]


# Module-level shared session singleton
_default_candidate_store = IngestedDocumentCandidateStore()


def get_candidate_store() -> IngestedDocumentCandidateStore:
    """Return the shared session IngestedDocumentCandidateStore singleton."""
    return _default_candidate_store


def reset_candidate_store() -> IngestedDocumentCandidateStore:
    """Reset the shared session IngestedDocumentCandidateStore singleton."""
    _default_candidate_store.clear()
    return _default_candidate_store
