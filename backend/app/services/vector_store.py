"""Lightweight, portable local vector store for regulatory candidate indexing and retrieval.

Supports cosine similarity search and metadata filtering.
Uses OpenAI text-embedding-3-small when configured, with a deterministic
character-ngram token-hash fallback for offline/development testing.
Explicitly identifies the embedding provider used.
"""

import hashlib
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from app.config import settings
from app.models.content import RegulatoryContentItem

logger = logging.getLogger("vector_store")


class VectorStore:
    """Lightweight in-memory vector index for candidate retrieval with metadata filtering.

    CRITICAL NOTE:
    Similarity threshold is strictly for retrieval filtering.
    Similarity score NEVER autonomously determines Reuse, Adapt, or Reject.
    """

    def __init__(
        self,
        embedding_model: Optional[str] = None,
        vector_dim: int = 256,
        api_key: Optional[str] = None,
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.embedding_model = embedding_model or settings.OPENAI_EMBEDDING_MODEL
        self.vector_dim = vector_dim
        self.has_openai = bool(self.api_key and len(self.api_key.strip()) > 5)

        # In-memory index: list of tuples (content_item, vector, provider_name)
        self._index: List[Tuple[RegulatoryContentItem, List[float], str]] = []

    def get_embedding_provider_name(self) -> str:
        """Return identifier of active embedding provider."""
        return "openai" if self.has_openai else "fallback_deterministic"

    def generate_embedding(self, text: str) -> Tuple[List[float], str]:
        """Generate a normalized embedding vector for text.

        Returns (vector, provider_name).
        """
        clean_text = text.strip()
        if not clean_text:
            return ([0.0] * self.vector_dim, self.get_embedding_provider_name())

        if self.has_openai:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key)
                response = client.embeddings.create(
                    model=self.embedding_model,
                    input=[clean_text[:8000]],
                )
                vec = response.data[0].embedding
                return (self._normalize(vec), "openai")
            except Exception as exc:
                logger.warning(
                    "OpenAI embedding call failed (%s). Degrading safely to deterministic fallback.",
                    exc,
                )

        # Limited development/test fallback generator
        # Uses token hashing to produce a stable pseudo-vector
        return (self._generate_fallback_embedding(clean_text), "fallback_deterministic")

    def _generate_fallback_embedding(self, text: str) -> List[float]:
        """Generate a stable deterministic unit vector using token character hashes.

        LIMITATION NOTICE:
        This fallback embedding is strictly for development and offline testing.
        It is NOT production semantic similarity and NEVER independently determines reuse decisions.
        """
        vector = [0.0] * self.vector_dim
        words = text.lower().split()
        if not words:
            return vector

        for word in words:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.vector_dim
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            vector[idx] += sign

        return self._normalize(vector)

    @staticmethod
    def _normalize(vector: List[float]) -> List[float]:
        """Normalize vector to unit length."""
        norm = math.sqrt(sum(v * v for v in vector))
        if norm <= 1e-9:
            return vector
        return [v / norm for v in vector]

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """Calculate cosine similarity between two normalized vectors."""
        min_len = min(len(v1), len(v2))
        dot_product = sum(v1[i] * v2[i] for i in range(min_len))
        return max(0.0, min(1.0, dot_product))

    def add_items(self, items: Any) -> None:
        """Index a batch of regulatory content items (or adapted RegulatoryChunks/RegulatoryDocuments)."""
        from app.services.compatibility.regulatory_adapter import adapt_for_retrieval

        normalized_items = adapt_for_retrieval(items)
        for item in normalized_items:
            vector, provider = self.generate_embedding(item.text)
            self._index.append((item, vector, provider))

    def clear(self) -> None:
        """Clear all indexed records."""
        self._index.clear()

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        min_threshold: Optional[float] = None,
    ) -> List[Tuple[RegulatoryContentItem, float, str]]:
        """Search indexed candidates by cosine similarity with optional metadata filtering.

        Returns list of tuples: (item, similarity_score, embedding_provider).
        """
        if not self._index:
            return []

        query_vec, query_provider = self.generate_embedding(query)
        threshold = min_threshold if min_threshold is not None else settings.SIMILARITY_THRESHOLD
        results: List[Tuple[RegulatoryContentItem, float, str]] = []

        for item, item_vec, item_provider in self._index:
            # Apply metadata filters
            if filters:
                match = True
                if "source" in filters and item.source.lower() != filters["source"].lower():
                    match = False
                if "section" in filters and filters["section"]:
                    filter_sec = filters["section"].lower()
                    item_sec = (item.section or "").lower()
                    if filter_sec not in item_sec and item_sec not in filter_sec:
                        match = False
                if "drug" in filters and filters["drug"]:
                    filter_drug = filters["drug"].lower()
                    item_drug = (item.drug or "").lower()
                    if filter_drug != item_drug:
                        match = False
                if "content_type" in filters and filters["content_type"]:
                    if item.content_type != filters["content_type"]:
                        match = False

                if not match:
                    continue

            # Calculate cosine similarity
            sim = self.cosine_similarity(query_vec, item_vec)
            if sim >= threshold:
                results.append((item, round(sim, 4), item_provider))

        # Sort descending by similarity score
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
