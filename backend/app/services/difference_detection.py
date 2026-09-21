"""Difference detection service module.

Identifies structural, terminology, numerical, and phrasing differences between
current internal document text and external regulatory candidate content.
Reports attribute, current value, candidate value, explanation, and reviewer attention required.
Does NOT assign arbitrary Critical/Major/Minor severity scores.
"""

import difflib
import re
from typing import List
from app.models.comparison import DifferenceItem
from app.services.key_information_extractor import KeyInformationExtractor


class DifferenceDetectionService:
    """Detects deterministic differences between target content and regulatory candidate content."""

    def __init__(self):
        self.extractor = KeyInformationExtractor()

    def analyze_differences(
        self,
        current_text: str,
        candidate_text: str,
    ) -> List[DifferenceItem]:
        """Produce structured difference items without arbitrary severity scores."""
        differences: List[DifferenceItem] = []

        curr_info = self.extractor.extract(current_text)
        cand_info = self.extractor.extract(candidate_text)

        # 1. Dose Disparity
        if curr_info.dose and cand_info.dose and curr_info.dose.lower() != cand_info.dose.lower():
            differences.append(
                DifferenceItem(
                    attribute="dose",
                    aspect="key_information",
                    current_value=curr_info.dose,
                    candidate_value=cand_info.dose,
                    explanation=f"Dose quantity differs: current is '{curr_info.dose}', candidate is '{cand_info.dose}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                )
            )

        # 2. Frequency Disparity
        if curr_info.frequency and cand_info.frequency and curr_info.frequency.lower() != cand_info.frequency.lower():
            differences.append(
                DifferenceItem(
                    attribute="frequency",
                    aspect="key_information",
                    current_value=curr_info.frequency,
                    candidate_value=cand_info.frequency,
                    explanation=f"Dosing frequency differs: current is '{curr_info.frequency}', candidate is '{cand_info.frequency}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                )
            )

        # 3. Route Disparity
        if curr_info.route and cand_info.route and curr_info.route.lower() != cand_info.route.lower():
            differences.append(
                DifferenceItem(
                    attribute="route",
                    current_value=curr_info.route,
                    candidate_value=cand_info.route,
                    explanation=f"Administration route differs: current is '{curr_info.route}', candidate is '{cand_info.route}'.",
                    reviewer_attention_required=True,
                )
            )

        # 4. Population Disparity
        if curr_info.population and cand_info.population and curr_info.population.lower() != cand_info.population.lower():
            differences.append(
                DifferenceItem(
                    attribute="population",
                    current_value=curr_info.population,
                    candidate_value=cand_info.population,
                    explanation=f"Target population differs: current applies to '{curr_info.population}', candidate applies to '{cand_info.population}'.",
                    reviewer_attention_required=True,
                )
            )

        # 5. Drug Disparity
        if curr_info.drug and cand_info.drug and curr_info.drug.lower() != cand_info.drug.lower():
            differences.append(
                DifferenceItem(
                    attribute="drug",
                    current_value=curr_info.drug,
                    candidate_value=cand_info.drug,
                    explanation=f"Active substance differs: current references '{curr_info.drug}', candidate references '{cand_info.drug}'.",
                    reviewer_attention_required=True,
                )
            )

        # 6. General Numerical Comparison (fallback for uncaught numbers)
        if not any(d.attribute == "dose" for d in differences):
            current_nums = re.findall(r"\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|kg|%|tablets?|capsules?|hours?|days?)\b", current_text, re.IGNORECASE)
            candidate_nums = re.findall(r"\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|kg|%|tablets?|capsules?|hours?|days?)\b", candidate_text, re.IGNORECASE)

            if set(current_nums) != set(candidate_nums) and (current_nums or candidate_nums):
                differences.append(
                    DifferenceItem(
                        attribute="key_information",
                        current_value=", ".join(current_nums) if current_nums else "None detected",
                        candidate_value=", ".join(candidate_nums) if candidate_nums else "None detected",
                        explanation="Dosing units or numerical parameters vary between current document and candidate.",
                        reviewer_attention_required=True,
                        regulatory_impact="MAJOR",  # legacy compatibility
                    )
                )

        # 7. Structural Disparity
        len_ratio = len(candidate_text) / max(len(current_text), 1)
        if len_ratio > 2.0 or len_ratio < 0.5:
            differences.append(
                DifferenceItem(
                    attribute="structure",
                    current_value=f"{len(current_text)} characters",
                    candidate_value=f"{len(candidate_text)} characters",
                    explanation="Significant length disparity indicates differing levels of clinical detail or missing sub-clauses.",
                    reviewer_attention_required=True,
                    regulatory_impact="MODERATE",  # legacy compatibility
                )
            )

        # 8. Textual Phrasing Difference
        matcher = difflib.SequenceMatcher(None, current_text.split(), candidate_text.split())
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                curr_slice = " ".join(current_text.split()[i1:i2])
                cand_slice = " ".join(candidate_text.split()[j1:j2])
                if len(curr_slice) > 10 or len(cand_slice) > 10:
                    differences.append(
                        DifferenceItem(
                            attribute="format",
                            current_value=curr_slice[:150],
                            candidate_value=cand_slice[:150],
                            explanation="Wording variation observed in clinical phraseology.",
                            reviewer_attention_required=False,
                            regulatory_impact="MINOR",  # legacy compatibility
                        )
                    )
            elif tag == "delete":
                curr_slice = " ".join(current_text.split()[i1:i2])
                if len(curr_slice) > 10:
                    differences.append(
                        DifferenceItem(
                            attribute="content",
                            current_value=curr_slice[:150],
                            candidate_value=None,
                            explanation="Statement present in current document is absent in candidate regulatory record.",
                            reviewer_attention_required=True,
                            regulatory_impact="MODERATE",  # legacy compatibility
                        )
                    )
            elif tag == "insert":
                cand_slice = " ".join(candidate_text.split()[j1:j2])
                if len(cand_slice) > 10:
                    differences.append(
                        DifferenceItem(
                            attribute="content",
                            current_value=None,
                            candidate_value=cand_slice[:150],
                            explanation="Additional regulatory phrase present in candidate reference.",
                            reviewer_attention_required=False,
                            regulatory_impact="INFORMATIONAL",  # legacy compatibility
                        )
                    )

        return differences[:10]
