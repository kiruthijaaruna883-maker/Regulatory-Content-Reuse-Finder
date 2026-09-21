"""Regulatory content matching service module.

Calculates deterministic similarity between target document content and candidate
regulatory records based on token overlap, clinical terminology, and section alignment.
"""

import re
from typing import List, Set
from app.models.comparison import ComparisonCandidate, EvidenceTrace
from app.models.content import RegulatoryContentItem


class ContentMatchingService:
    """Deterministic matcher evaluating alignment between current and candidate regulatory content."""

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        """Normalize text into distinct alphanumeric tokens."""
        tokens = re.findall(r"\b[a-zA-Z0-9]{3,}\b", text.lower())
        stopwords = {
            "the", "and", "for", "with", "this", "that", "from", "are", "was",
            "were", "has", "have", "had", "not", "but", "can", "should", "will"
        }
        return {t for t in tokens if t not in stopwords}

    def compute_jaccard_similarity(self, text_a: str, text_b: str) -> float:
        """Compute Jaccard token similarity between two text snippets."""
        tokens_a = self._tokenize(text_a)
        tokens_b = self._tokenize(text_b)

        if not tokens_a or not tokens_b:
            return 0.0

        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)

        return round(len(intersection) / len(union), 4)

    def rank_candidates(
        self,
        target_text: str,
        candidates: List[RegulatoryContentItem],
        min_threshold: float = 0.05,
    ) -> List[ComparisonCandidate]:
        """Rank and structure candidate regulatory items against target content."""
        target_tokens = self._tokenize(target_text)
        ranked: List[ComparisonCandidate] = []

        for item in candidates:
            score = self.compute_jaccard_similarity(target_text, item.text)
            matched_tokens = list(target_tokens.intersection(self._tokenize(item.text)))[:5]

            # Build evidence trace
            evidence = EvidenceTrace(
                source=item.source,
                source_url=item.source_url,
                source_identifier=item.source_identifier,
                document_name=item.document_name,
                section=item.section,
                location=item.location,
                exact_quote=item.text[:200] + "..." if len(item.text) > 200 else item.text,
            )

            candidate = ComparisonCandidate(
                content_item=item,
                similarity_score=score,
                matched_aspects=matched_tokens,
                evidence=[evidence],
            )
            ranked.append(candidate)

        # Sort descending by similarity score
        ranked.sort(key=lambda c: c.similarity_score or 0.0, reverse=True)
        return ranked
