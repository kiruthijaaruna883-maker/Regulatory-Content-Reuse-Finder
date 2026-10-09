"""On-demand live Retrieval-Augmented Generation (RAG) retriever module.

Coordinates on-demand queries to live external sources (DailyMed, openFDA),
indexes candidates for the current session in the local VectorStore,
and retrieves candidates with attribute filtering and full traceability.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from app.config import settings
from app.models.content import KeyInformation, RegulatoryContentItem
from app.services.content_classifier import ContentClassifier
from app.services.key_information_extractor import KeyInformationExtractor
from app.services.regulatory_source import RegulatorySourceService
from app.services.vector_store import VectorStore

logger = logging.getLogger("rag_retriever")

SECTION_HEADING_PATTERN = re.compile(
    r"^(section\s*\d+|part\s*\d+|chapter\s*\d+|[0-9]+[\.\:\s]+|indications?(\s+and\s+usage)?|dosage(\s+and\s+administration)?|contraindications?|warnings?(\s+and\s+precautions)?|precautions?|adverse\s*reactions?|drug\s*interactions?|clinical\s*pharmacology|storage|how\s*supplied|description|overdosage|patient\s*counseling)",
    re.IGNORECASE,
)


def is_section_heading(text: Optional[str]) -> bool:
    """Determine whether text represents a regulatory section header rather than a drug name."""
    if not text:
        return False
    return bool(SECTION_HEADING_PATTERN.search(text.strip()))


class LiveRAGRetriever:
    """Retrieves candidates on-demand from live regulatory services and ingested candidate store,
    performing session vector filtering with full traceability.
    """

    def __init__(
        self,
        source_service: Optional[RegulatorySourceService] = None,
        vector_store: Optional[VectorStore] = None,
        candidate_store: Optional[Any] = None,
        deduplicator: Optional[Any] = None,
    ):
        self.sources = source_service or RegulatorySourceService()
        self.vector_store = vector_store or VectorStore()
        if candidate_store is None:
            from app.services.candidate_store import get_candidate_store
            self.candidate_store = get_candidate_store()
        else:
            self.candidate_store = candidate_store
        if deduplicator is None:
            from app.services.candidate_deduplicator import get_candidate_deduplicator
            self.deduplicator = get_candidate_deduplicator()
        else:
            self.deduplicator = deduplicator
        self.extractor = KeyInformationExtractor()
        self.classifier = ContentClassifier()

    async def retrieve_candidates(
        self,
        target_text: str,
        section_hint: Optional[str] = None,
        target_key_info: Optional[KeyInformation] = None,
        top_k: Optional[int] = None,
        source_filter: str = "all",
        exclude_document_id: Optional[str] = None,
        exclude_content_id: Optional[str] = None,
        exclude_document_fingerprint: Optional[str] = None,
    ) -> List[Tuple[RegulatoryContentItem, float, str]]:
        """Execute on-demand RAG pipeline for the given target text.

        Queries live external sources (DailyMed, openFDA) and the ingested document
        candidate store, indexes candidates into the session vector store, and returns
        ranked candidates.

        Returns list of tuples: (candidate_item, similarity_score, embedding_provider).
        """
        k = top_k or settings.TOP_K_CANDIDATES
        key_info = target_key_info or self.extractor.extract(target_text)

        # 1. Determine search query from extracted key information or text snippet
        query = key_info.drug or key_info.active_ingredient or key_info.indication
        if not query and section_hint and section_hint.strip():
            query = section_hint.strip()
        if not query:
            # Extract first 3-5 alphanumeric words as fallback query
            words = [w for w in target_text.split() if len(w) > 3 and w.isalpha()]
            query = " ".join(words[:3]) if words else target_text[:40].strip()

        if not query:
            return []

        # Resolve verified drug name without fabricating or inferring from section titles
        verified_drug = None
        if key_info and key_info.drug and not is_section_heading(key_info.drug):
            verified_drug = key_info.drug
        elif key_info and key_info.active_ingredient and not is_section_heading(key_info.active_ingredient):
            verified_drug = key_info.active_ingredient
        elif exclude_document_id and hasattr(self.candidate_store, "get_document"):
            doc = self.candidate_store.get_document(exclude_document_id)
            if doc:
                doc_ing = getattr(doc, "active_ingredient", None)
                doc_prod = getattr(doc, "product_name", None)
                if doc_ing and not is_section_heading(doc_ing):
                    verified_drug = doc_ing
                elif doc_prod and not is_section_heading(doc_prod):
                    verified_drug = doc_prod
                elif hasattr(self.candidate_store, "list_content_items"):
                    for it in self.candidate_store.list_content_items(exclude_document_id):
                        if it.drug and not is_section_heading(it.drug):
                            verified_drug = it.drug
                            break

        # Determine external query: never send a section heading to DailyMed as drug_name
        external_query = verified_drug
        if not external_query and not is_section_heading(query):
            external_query = query

        raw_candidates: List[RegulatoryContentItem] = []
        norm_filter = (source_filter or "all").lower().strip()
        fetch_limit = max(k * 2, 10)

        # 2a. Query live external trusted sources on demand (DailyMed, openFDA)
        if norm_filter in ("all", "dailymed", "openfda"):
            if external_query:
                try:
                    search_result = await self.sources.search(
                        query=external_query,
                        source=norm_filter if norm_filter != "all" else "all",
                        section=section_hint,
                        limit=fetch_limit,
                    )
                    raw_candidates.extend(search_result.items)
                except Exception as exc:
                    logger.warning("Live regulatory query failed: %s", exc)
            else:
                # If no reliable drug name exists, openFDA can perform text/section search
                if norm_filter in ("all", "openfda") and (section_hint or query):
                    try:
                        fda_q = section_hint or query
                        fda_items = await self.sources.openfda.search(
                            query=fda_q,
                            section=section_hint,
                            limit=fetch_limit,
                        )
                        raw_candidates.extend(fda_items)
                    except Exception as exc:
                        logger.warning("openFDA fallback query failed: %s", exc)
                if norm_filter == "dailymed":
                    logger.info("DailyMed query skipped: no verified drug name available for query '%s'", query)

        # Resolve target document fingerprint: use supplied directly, or resolve via canonical store
        target_fp = exclude_document_fingerprint
        if not target_fp and exclude_document_id and hasattr(self.candidate_store, "get_document_fingerprint"):
            target_fp = self.candidate_store.get_document_fingerprint(exclude_document_id)

        # 2b. Query ingested document candidate store (newly ingested regulatory documents)
        if norm_filter in ("all", "ingested", "internal"):
            try:
                ingested_candidates = self.candidate_store.search(
                    query=query,
                    section=section_hint,
                    limit=fetch_limit,
                    target_text=target_text,
                    exclude_document_id=exclude_document_id,
                    exclude_content_id=exclude_content_id,
                    exclude_document_fingerprint=target_fp,
                )
                raw_candidates.extend(ingested_candidates)
            except Exception as exc:
                logger.warning("Ingested candidate store query failed: %s", exc)

        # Defensive exclusion filter to ensure source document chunks never reach vector similarity
        raw_candidates = [
            candidate
            for candidate in raw_candidates
            if not (
                exclude_document_id
                and candidate.document_id == exclude_document_id
            )
            and not (
                target_fp
                and (
                    getattr(candidate, "document_fingerprint", None) == target_fp
                    or (
                        hasattr(self.candidate_store, "get_document_fingerprint")
                        and self.candidate_store.get_document_fingerprint(candidate.document_id) == target_fp
                    )
                )
            )
            and not (
                exclude_content_id
                and candidate.content_id == exclude_content_id
            )
        ]

        if not raw_candidates:
            return []

        # 3. Enrich candidates with key information and classification
        enriched_candidates: List[RegulatoryContentItem] = []
        for cand in raw_candidates:
            if not cand.key_information:
                cand.key_information = self.extractor.extract(cand.text)
            if not cand.content_type:
                cand.content_type = self.classifier.classify(cand.text, cand.section).value
            enriched_candidates.append(cand)

        # 4. Cross-source candidate deduplication with provenance merging
        deduped_candidates = self.deduplicator.deduplicate(enriched_candidates)

        # 5. Index candidates into ephemeral session vector store (isolated from persistent candidate store)
        self.vector_store.clear()
        self.vector_store.add_items(deduped_candidates)

        # 6. Retrieve top-k candidates by similarity
        results = self.vector_store.search(
            query=target_text,
            top_k=k,
            min_threshold=settings.SIMILARITY_THRESHOLD,
        )

        # Fallback: if similarity threshold filtered all items, return top candidate directly
        if not results and deduped_candidates:
            results = [(deduped_candidates[0], 0.30, self.vector_store.get_embedding_provider_name())]

        return results
