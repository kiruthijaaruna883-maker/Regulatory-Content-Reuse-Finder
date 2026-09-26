"""Cross-source candidate deduplication and filtering module.

Identifies exact duplicate and near-duplicate regulatory candidates across DailyMed,
openFDA, and ingested candidate store records.
Preserves full source traceability and provenance from all sources without fabricating metadata.
Avoids aggressive semantic assumptions and never relies on embeddings or vector databases.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.content import KeyInformation, RegulatoryContentItem

logger = logging.getLogger("candidate_deduplicator")


def normalize_text_conservative(text: str) -> str:
    """Conservatively normalize regulatory text for deterministic comparison.

    Normalizes whitespace, case, unicode punctuation, and leading list bullets,
    while preserving numerical dosage tokens, units, and words.
    """
    if not text:
        return ""

    # 1. Unicode replacements (smart quotes, dashes, non-breaking spaces)
    normalized = (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u00a0", " ")
        .replace("\r\n", "\n")
    )

    # 2. Lowercase
    normalized = normalized.lower()

    # 3. Strip leading bullet points or numbered markers
    normalized = re.sub(r"^\s*[-*•\d\.\)\(]+\s+", "", normalized)

    # 4. Collapse consecutive whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # 5. Strip trailing/leading punctuation
    normalized = normalized.strip(" .,;:!?-")

    return normalized


def extract_numerical_tokens(text: str) -> Set[str]:
    """Extract numerical and unit tokens (e.g. '10', '10mg', '500', '20%') to prevent
    falsely merging different dosage strengths or durations.
    """
    if not text:
        return set()
    # Match numbers with optional units
    matches = re.findall(r"\b\d+(?:\.\d+)?(?:\s*(?:mg|mcg|g|kg|ml|l|%|hours?|hrs?|days?|weeks?|months?|years?|tablet|capsule|tablets|capsules))?\b", text.lower())
    return {re.sub(r"\s+", "", m) for m in matches}


def normalize_drug_token(drug: Optional[str]) -> str:
    """Normalize drug or product name to a base token for conflict detection."""
    if not drug:
        return ""
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", drug.lower())
    # Remove common salt/dosage form noise if at the end
    clean = re.sub(r"\b(tablets?|capsules?|solution|injection|oral|calcium|sodium|hydrochloride|potassium|maleate|succinate|tartrate|fumarate)\b", "", clean)
    tokens = clean.split()
    return " ".join(tokens).strip()


class CandidateDeduplicator:
    """Deterministic candidate deduplicator across multiple regulatory sources."""

    def __init__(self, near_duplicate_threshold: float = 0.90):
        self.near_duplicate_threshold = near_duplicate_threshold

    def are_duplicates(self, item_a: RegulatoryContentItem, item_b: RegulatoryContentItem) -> bool:
        """Determine whether two candidates represent the same underlying regulatory content.

        Applies strict negative guards before checking positive match criteria.
        """
        # 1. Identity shortcut
        if item_a.content_id == item_b.content_id:
            return True

        # 2. Negative guard: Drug name conflict
        # If both specify a drug or active ingredient and they clearly conflict, they are NOT duplicates
        drug_a = normalize_drug_token(item_a.drug or (item_a.key_information.drug if item_a.key_information else None))
        drug_b = normalize_drug_token(item_b.drug or (item_b.key_information.drug if item_b.key_information else None))
        if drug_a and drug_b:
            # Check if one is contained in the other or token overlap exists
            tokens_a = set(drug_a.split())
            tokens_b = set(drug_b.split())
            if not tokens_a.intersection(tokens_b) and drug_a != drug_b:
                return False

        # 3. Negative guard: Section conflict when sections are standard distinct sections
        sec_a = (item_a.section or "").strip().lower()
        sec_b = (item_b.section or "").strip().lower()
        if sec_a and sec_b:
            is_sec_conflict = (
                ("contraindication" in sec_a and "contraindication" not in sec_b and "dosage" in sec_b)
                or ("dosage" in sec_a and "dosage" not in sec_b and "contraindication" in sec_b)
                or ("indication" in sec_a and "indication" not in sec_b and "warning" in sec_b)
            )
            if is_sec_conflict:
                return False

        # 4. Normalized text extraction
        norm_a = normalize_text_conservative(item_a.text)
        norm_b = normalize_text_conservative(item_b.text)

        if not norm_a or not norm_b:
            return False

        # Positive Criterion 1: Exact normalized text match
        if norm_a == norm_b:
            return True

        # 5. Negative guard: Numerical/Dosage difference check
        nums_a = extract_numerical_tokens(norm_a)
        nums_b = extract_numerical_tokens(norm_b)
        if nums_a and nums_b and nums_a != nums_b:
            # Different numerical strengths (e.g. 10 mg vs 20 mg) -> NOT duplicates
            return False

        # Positive Criterion 2: Source identifier + section + token similarity
        id_a = item_a.source_identifier or item_a.document_id
        id_b = item_b.source_identifier or item_b.document_id
        if id_a and id_b and id_a == id_b:
            if sec_a == sec_b and sec_a:
                words_a = set(norm_a.split())
                words_b = set(norm_b.split())
                if words_a and words_b:
                    jaccard = len(words_a.intersection(words_b)) / len(words_a.union(words_b))
                    if jaccard >= 0.80:
                        return True

        # Positive Criterion 3: Conservative near-duplicate match
        # Must have high token overlap AND shared context (same drug or same section)
        words_a = set(norm_a.split())
        words_b = set(norm_b.split())
        if words_a and words_b:
            jaccard = len(words_a.intersection(words_b)) / len(words_a.union(words_b))
            if jaccard >= self.near_duplicate_threshold:
                # Require common drug or section or minimal length
                has_common_context = bool(
                    (drug_a and drug_b and (drug_a in drug_b or drug_b in drug_a))
                    or (sec_a and sec_b and (sec_a in sec_b or sec_b in sec_a))
                    or (len(words_a) >= 12 and len(words_b) >= 12)
                )
                if has_common_context:
                    return True

        return False

    @staticmethod
    def _calculate_richness(item: RegulatoryContentItem) -> int:
        """Calculate metadata richness score to choose the most informative candidate as primary."""
        score = 0
        if item.page is not None:
            score += 2
        if item.location:
            score += 2
        if item.document_name:
            score += 2
        if item.source_url:
            score += 2
        if item.source_identifier:
            score += 2
        if item.section:
            score += 1
        if item.subsection:
            score += 1
        if item.loinc_code:
            score += 1
        if item.key_information:
            score += 1
        if item.date:
            score += 1
        if item.version:
            score += 1
        # Slightly prefer ingested internal drafts for local document authority
        if item.source.lower() in ("internaldraft", "ingested", "internal"):
            score += 1
        return score

    def merge_candidates(
        self,
        item_a: RegulatoryContentItem,
        item_b: RegulatoryContentItem,
    ) -> RegulatoryContentItem:
        """Merge duplicate candidate into primary candidate, preserving full cross-source provenance."""
        # Choose primary candidate with higher richness
        richness_a = self._calculate_richness(item_a)
        richness_b = self._calculate_richness(item_b)

        if richness_b > richness_a:
            primary = item_b.model_copy(deep=True)
            duplicate = item_a
        else:
            primary = item_a.model_copy(deep=True)
            duplicate = item_b

        # Ensure metadata dictionary exists
        if primary.metadata is None:
            primary.metadata = {}

        # 1. Track cross-sources across both candidates
        sources_set = set(primary.metadata.get("cross_sources", [primary.source]))
        sources_set.add(primary.source)
        sources_set.add(duplicate.source)
        if duplicate.metadata and "cross_sources" in duplicate.metadata:
            sources_set.update(duplicate.metadata["cross_sources"])
        primary.metadata["cross_sources"] = sorted(list(sources_set))

        # 2. Track duplicate provenance records
        dup_prov_list: List[Dict[str, Any]] = list(primary.metadata.get("duplicate_provenance", []))

        # Record duplicate's exact provenance
        new_entry: Dict[str, Any] = {
            "content_id": duplicate.content_id,
            "source": duplicate.source,
            "document_id": duplicate.document_id,
            "document_name": duplicate.document_name,
            "source_identifier": duplicate.source_identifier,
            "source_url": duplicate.source_url,
            "section": duplicate.section,
            "subsection": duplicate.subsection,
            "location": duplicate.location,
            "page": duplicate.page,
            "version": duplicate.version,
            "date": duplicate.date,
        }
        # Avoid duplicate entries in provenance list
        if not any(e.get("content_id") == duplicate.content_id for e in dup_prov_list):
            dup_prov_list.append(new_entry)

        # Also pull any existing duplicate provenance already on the duplicate
        if duplicate.metadata and "duplicate_provenance" in duplicate.metadata:
            for extra in duplicate.metadata["duplicate_provenance"]:
                if not any(e.get("content_id") == extra.get("content_id") for e in dup_prov_list):
                    dup_prov_list.append(extra)

        primary.metadata["duplicate_provenance"] = dup_prov_list

        # 3. Fill missing fields on primary from duplicate without overwriting primary source/url
        if primary.document_name is None and duplicate.document_name:
            primary.document_name = duplicate.document_name
        if primary.document_id is None and duplicate.document_id:
            primary.document_id = duplicate.document_id
        if primary.section is None and duplicate.section:
            primary.section = duplicate.section
        if primary.subsection is None and duplicate.subsection:
            primary.subsection = duplicate.subsection
        if primary.page is None and duplicate.page is not None and primary.source == duplicate.source:
            primary.page = duplicate.page
        if primary.location is None and duplicate.location and primary.source == duplicate.source:
            primary.location = duplicate.location
        if primary.key_information is None and duplicate.key_information:
            primary.key_information = duplicate.key_information

        return primary

    def deduplicate(self, candidates: List[RegulatoryContentItem]) -> List[RegulatoryContentItem]:
        """Perform deterministic deduplication across candidate items.

        Returns:
            Deduplicated list of RegulatoryContentItems with merged cross-source provenance.
        """
        if not candidates:
            return []

        deduped: List[RegulatoryContentItem] = []

        for candidate in candidates:
            merged = False
            for i, existing in enumerate(deduped):
                if self.are_duplicates(existing, candidate):
                    # Merge duplicate into existing entry
                    deduped[i] = self.merge_candidates(existing, candidate)
                    merged = True
                    break

            if not merged:
                # Add copy with initialized cross_sources metadata
                item_copy = candidate.model_copy(deep=True)
                if item_copy.metadata is None:
                    item_copy.metadata = {}
                if "cross_sources" not in item_copy.metadata:
                    item_copy.metadata["cross_sources"] = [item_copy.source]
                deduped.append(item_copy)

        return deduped


# Shared default singleton
_default_deduplicator = CandidateDeduplicator()


def get_candidate_deduplicator() -> CandidateDeduplicator:
    """Return the shared CandidateDeduplicator singleton."""
    return _default_deduplicator


def deduplicate_candidates(candidates: List[RegulatoryContentItem]) -> List[RegulatoryContentItem]:
    """Convenience helper to deduplicate candidates using default deduplicator."""
    return _default_deduplicator.deduplicate(candidates)
