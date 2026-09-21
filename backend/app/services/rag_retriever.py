"""On-demand live Retrieval-Augmented Generation (RAG) retriever module.

Coordinates on-demand queries to live external sources (DailyMed, openFDA),
indexes candidates for the current session in the local VectorStore,
and retrieves candidates with attribute filtering and full traceability.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from app.config import settings
from app.models.content import KeyInformation, RegulatoryContentItem
from app.services.content_classifier import ContentClassifier
from app.services.key_information_extractor import KeyInformationExtractor
from app.services.regulatory_source import RegulatorySourceService
from app.services.vector_store import VectorStore

logger = logging.getLogger("rag_retriever")


class LiveRAGRetriever:
    """Retrieves candidates on-demand from live regulatory services and performs vector filtering."""

    def __init__(
        self,
        source_service: Optional[RegulatorySourceService] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        self.sources = source_service or RegulatorySourceService()
        self.vector_store = vector_store or VectorStore()
        self.extractor = KeyInformationExtractor()
        self.classifier = ContentClassifier()

    async def retrieve_candidates(
        self,
        target_text: str,
        section_hint: Optional[str] = None,
        target_key_info: Optional[KeyInformation] = None,
        top_k: Optional[int] = None,
        source_filter: str = "all",
    ) -> List[Tuple[RegulatoryContentItem, float, str]]:
        """Execute on-demand RAG pipeline for the given target text.

        Returns list of tuples: (candidate_item, similarity_score, embedding_provider).
        """
        k = top_k or settings.TOP_K_CANDIDATES
        key_info = target_key_info or self.extractor.extract(target_text)

        # 1. Determine search query from extracted key information or text snippet
        query = key_info.drug or key_info.active_ingredient or key_info.indication
        if not query:
            # Extract first 3-5 alphanumeric words as fallback query
            words = [w for w in target_text.split() if len(w) > 3 and w.isalpha()]
            query = " ".join(words[:3]) if words else target_text[:40].strip()

        if not query:
            return []

        # 2. Query live trusted sources on demand (NO massive dataset download)
        try:
            search_result = await self.sources.search(
                query=query,
                source=source_filter,
                section=section_hint,
                limit=k * 2,
            )
            raw_candidates = search_result.items
        except Exception as exc:
            logger.warning("Live regulatory query failed: %s", exc)
            return []

        if not raw_candidates:
            return []

        # 3. Enrich candidates with key information and classification
        enriched_candidates: List[RegulatoryContentItem] = []
        for cand in raw_candidates:
            cand_key_info = self.extractor.extract(cand.text)
            cand.key_information = cand_key_info
            if not cand.content_type:
                cand.content_type = self.classifier.classify(cand.text, cand.section).value
            enriched_candidates.append(cand)

        # 4. Index candidates into session vector store
        self.vector_store.clear()
        self.vector_store.add_items(enriched_candidates)

        # 5. Retrieve top-k candidates by similarity
        results = self.vector_store.search(
            query=target_text,
            top_k=k,
            min_threshold=settings.SIMILARITY_THRESHOLD,
        )

        # Fallback: if similarity threshold filtered all items, return top candidate directly
        if not results and enriched_candidates:
            results = [(enriched_candidates[0], 0.30, self.vector_store.get_embedding_provider_name())]

        return results
