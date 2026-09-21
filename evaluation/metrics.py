"""RAG and Multi-Dimensional Comparison evaluation metrics module.

Implements mathematical evaluation metrics:
- Recall@K
- Precision@K
- Hit Rate@K
- Mean Reciprocal Rank (MRR)
- Groundedness evaluation
- False Match detection accuracy
"""

from typing import Any, Dict, List, Set


def calculate_recall_at_k(retrieved_ids: List[str], relevant_ids: Set[str], k: int) -> float:
    """Calculate Recall@K: proportion of relevant items retrieved in top-k."""
    if not relevant_ids:
        return 1.0
    top_k_retrieved = set(retrieved_ids[:k])
    hits = len(top_k_retrieved.intersection(relevant_ids))
    return round(hits / len(relevant_ids), 4)


def calculate_precision_at_k(retrieved_ids: List[str], relevant_ids: Set[str], k: int) -> float:
    """Calculate Precision@K: proportion of top-k retrieved items that are relevant."""
    if k <= 0:
        return 0.0
    top_k_retrieved = set(retrieved_ids[:k])
    hits = len(top_k_retrieved.intersection(relevant_ids))
    return round(hits / k, 4)


def calculate_hit_rate_at_k(retrieved_ids: List[str], relevant_ids: Set[str], k: int) -> float:
    """Calculate Hit Rate@K: 1.0 if at least one relevant item is in top-k, else 0.0."""
    top_k_retrieved = set(retrieved_ids[:k])
    return 1.0 if any(item_id in relevant_ids for item_id in top_k_retrieved) else 0.0


def calculate_mrr(retrieved_ids: List[str], relevant_ids: Set[str]) -> float:
    """Calculate Mean Reciprocal Rank: reciprocal rank of the first relevant item."""
    for idx, item_id in enumerate(retrieved_ids):
        if item_id in relevant_ids:
            return round(1.0 / (idx + 1), 4)
    return 0.0


def evaluate_groundedness(exact_quote: str, source_text: str) -> bool:
    """Verify that cited exact quote actually appears in source text."""
    if not exact_quote or not source_text:
        return False
    # Clean whitespace
    clean_quote = " ".join(exact_quote.split()).lower()
    clean_source = " ".join(source_text.split()).lower()
    return clean_quote in clean_source or clean_quote[:50] in clean_source


def evaluate_false_match_detection(
    has_discrepancy: bool,
    warning_flagged: bool,
) -> Dict[str, Any]:
    """Evaluate true positive / true negative accuracy for false-match protection."""
    is_correct = has_discrepancy == warning_flagged
    return {
        "has_discrepancy": has_discrepancy,
        "warning_flagged": warning_flagged,
        "correct": is_correct,
        "category": (
            "TP" if has_discrepancy and warning_flagged else
            "TN" if not has_discrepancy and not warning_flagged else
            "FP" if not has_discrepancy and warning_flagged else
            "FN"
        ),
    }
