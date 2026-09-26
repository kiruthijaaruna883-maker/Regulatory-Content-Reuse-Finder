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
)
from app.services.chunking.regulatory_chunker import RegulatoryChunker
from app.services.compatibility.regulatory_adapter import (
    _collect_chunks_recursive,
    chunk_to_content_item,
)

logger = logging.getLogger("candidate_store")


class IngestedDocumentCandidateStore:
    """Session candidate repository for ingested regulatory documents and chunks.

    Decoupled from ephemeral vector store query indexes to prevent ingested candidates
    from being erased when the temporary query vector index is cleared.
    """

    def __init__(self, default_chunker: Optional[RegulatoryChunker] = None):
        self._documents: Dict[str, RegulatoryDocument] = {}
        self._chunks: Dict[str, RegulatoryChunk] = {}
        self._content_items: Dict[str, RegulatoryContentItem] = {}
        self._doc_to_chunks: Dict[str, List[str]] = {}
        self._lock = threading.RLock()
        self._chunker = default_chunker or RegulatoryChunker()

    def add_document(
        self,
        document: RegulatoryDocument,
        chunks: Optional[Sequence[RegulatoryChunk]] = None,
    ) -> List[RegulatoryChunk]:
        """Store an ingested RegulatoryDocument and register its RegulatoryChunks as candidates.

        If chunks are not provided, checks if document.sections already contain chunks.
        If sections have no chunks, invokes RegulatoryChunker to populate structure-aware chunks.

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
        """
        from app.services.ingestion.unified_ingestion import ingest_and_chunk_document

        doc, chunks = ingest_and_chunk_document(
            content=content,
            filename=filename,
            mime_type=mime_type,
            document_id=document_id,
            document_name=document_name,
            provenance=provenance,
            metadata=metadata,
            chunker=self._chunker,
        )
        self.add_document(doc, chunks)
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
