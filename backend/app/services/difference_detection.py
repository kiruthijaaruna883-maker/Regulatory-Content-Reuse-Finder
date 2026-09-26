"""Difference detection service module.

Identifies structural, terminology, numerical, and phrasing differences between
current internal document text and external regulatory candidate content.
Reports attribute, current value, candidate value, explanation, and reviewer attention required.
Does NOT assign arbitrary Critical/Major/Minor severity scores.
"""

import difflib
import re
from typing import List, Set
from app.models.comparison import DifferenceItem
from app.services.key_information_extractor import (
    KeyInformationExtractor,
    normalize_dose_unit,
    normalize_frequency,
    normalize_route,
)


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
        lower_curr = current_text.lower()
        lower_cand = candidate_text.lower()

        # 1. Dose-Unit Disparity (Critical quantitative distinction e.g. 50 mg vs 50 mcg)
        norm_curr_unit = normalize_dose_unit(curr_info.dose_unit)
        norm_cand_unit = normalize_dose_unit(cand_info.dose_unit)
        if norm_curr_unit and norm_cand_unit and norm_curr_unit != norm_cand_unit:
            differences.append(
                DifferenceItem(
                    attribute="dose_unit",
                    aspect="key_information",
                    current_value=curr_info.dose_unit,
                    candidate_value=cand_info.dose_unit,
                    explanation=f"Dose unit disparity: current is '{curr_info.dose_unit}', candidate is '{cand_info.dose_unit}'. Critical clinical risk of quantitative dosing discrepancy.",
                    reviewer_attention_required=True,
                    regulatory_impact="CRITICAL",
                    difference_type="modification",
                )
            )

        # 2. Dose Disparity
        if curr_info.dose and cand_info.dose and curr_info.dose.lower().strip() != cand_info.dose.lower().strip():
            # If not already covered by dose_unit
            if not any(d.attribute == "dose_unit" for d in differences):
                differences.append(
                    DifferenceItem(
                        attribute="dose",
                        aspect="key_information",
                        current_value=curr_info.dose,
                        candidate_value=cand_info.dose,
                        explanation=f"Dose quantity differs: current is '{curr_info.dose}', candidate is '{cand_info.dose}'.",
                        reviewer_attention_required=True,
                        regulatory_impact="MAJOR",
                        difference_type="modification",
                    )
                )

        # 3. Frequency Disparity (with conservative normalization so e.g. QD == once daily)
        norm_curr_freq = normalize_frequency(curr_info.frequency)
        norm_cand_freq = normalize_frequency(cand_info.frequency)
        if norm_curr_freq and norm_cand_freq and norm_curr_freq != norm_cand_freq:
            differences.append(
                DifferenceItem(
                    attribute="frequency",
                    aspect="key_information",
                    current_value=curr_info.frequency,
                    candidate_value=cand_info.frequency,
                    explanation=f"Dosing frequency differs: current is '{curr_info.frequency}', candidate is '{cand_info.frequency}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # 4. Route Disparity (with conservative normalization so e.g. PO == Oral)
        norm_curr_route = normalize_route(curr_info.route)
        norm_cand_route = normalize_route(cand_info.route)
        if norm_curr_route and norm_cand_route and norm_curr_route != norm_cand_route:
            differences.append(
                DifferenceItem(
                    attribute="route",
                    aspect="key_information",
                    current_value=curr_info.route,
                    candidate_value=cand_info.route,
                    explanation=f"Administration route differs: current is '{curr_info.route}', candidate is '{cand_info.route}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # 5. Population Disparity
        if curr_info.population and cand_info.population and curr_info.population.lower() != cand_info.population.lower():
            differences.append(
                DifferenceItem(
                    attribute="population",
                    aspect="key_information",
                    current_value=curr_info.population,
                    candidate_value=cand_info.population,
                    explanation=f"Target population differs: current applies to '{curr_info.population}', candidate applies to '{cand_info.population}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # 6. Drug Disparity
        if curr_info.drug and cand_info.drug and curr_info.drug.lower() != cand_info.drug.lower():
            differences.append(
                DifferenceItem(
                    attribute="drug",
                    aspect="key_information",
                    current_value=curr_info.drug,
                    candidate_value=cand_info.drug,
                    explanation=f"Active substance differs: current references '{curr_info.drug}', candidate references '{cand_info.drug}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="CRITICAL",
                    difference_type="modification",
                )
            )

        # 7. Duration Disparity
        if curr_info.duration and cand_info.duration and curr_info.duration.lower().strip() != cand_info.duration.lower().strip():
            differences.append(
                DifferenceItem(
                    attribute="duration",
                    aspect="key_information",
                    current_value=curr_info.duration,
                    candidate_value=cand_info.duration,
                    explanation=f"Treatment duration differs: current is '{curr_info.duration}', candidate is '{cand_info.duration}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # 8. Indication Disparity
        if curr_info.indication and cand_info.indication and curr_info.indication.lower().strip() != cand_info.indication.lower().strip():
            differences.append(
                DifferenceItem(
                    attribute="indication",
                    aspect="key_information",
                    current_value=curr_info.indication,
                    candidate_value=cand_info.indication,
                    explanation=f"Therapeutic indication differs: current specifies '{curr_info.indication}', candidate specifies '{cand_info.indication}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # 9. Regulatory Modality Shift
        mandatory_terms = ["must", "shall", "required", "contraindicated", "do not"]
        advisory_terms = ["may", "should", "consider", "recommended", "optional"]
        curr_mand = [t for t in mandatory_terms if re.search(r"\b" + re.escape(t) + r"\b", lower_curr)]
        curr_adv = [t for t in advisory_terms if re.search(r"\b" + re.escape(t) + r"\b", lower_curr)]
        cand_mand = [t for t in mandatory_terms if re.search(r"\b" + re.escape(t) + r"\b", lower_cand)]
        cand_adv = [t for t in advisory_terms if re.search(r"\b" + re.escape(t) + r"\b", lower_cand)]

        if (curr_mand and not curr_adv and cand_adv and not cand_mand) or (cand_mand and not cand_adv and curr_adv and not curr_mand):
            c_val = "Mandatory (" + ", ".join(curr_mand) + ")" if curr_mand else "Advisory (" + ", ".join(curr_adv) + ")"
            cand_val = "Mandatory (" + ", ".join(cand_mand) + ")" if cand_mand else "Advisory (" + ", ".join(cand_adv) + ")"
            differences.append(
                DifferenceItem(
                    attribute="modality",
                    aspect="meaning",
                    current_value=c_val,
                    candidate_value=cand_val,
                    explanation="Regulatory obligation level shifts between mandatory directive and permissive recommendation.",
                    reviewer_attention_required=True,
                    regulatory_impact="MODERATE",
                    difference_type="modification",
                )
            )

        # 10. Administration Condition & Prohibition Shift
        # A. Food intake condition
        is_curr_food = bool(re.search(r"\b(with\s+(?:food|meals?)|take\s+with\s+(?:food|meals?)|co-administered\s+with\s+food)\b", lower_curr))
        is_curr_fast = bool(re.search(r"\b(without\s+food|on\s+an\s+empty\s+stomach|fasting|1\s+hour\s+before\s+meals?)\b", lower_curr))
        is_cand_food = bool(re.search(r"\b(with\s+(?:food|meals?)|take\s+with\s+(?:food|meals?)|co-administered\s+with\s+food)\b", lower_cand))
        is_cand_fast = bool(re.search(r"\b(without\s+food|on\s+an\s+empty\s+stomach|fasting|1\s+hour\s+before\s+meals?)\b", lower_cand))

        if (is_curr_food and is_cand_fast) or (is_curr_fast and is_cand_food):
            differences.append(
                DifferenceItem(
                    attribute="administration_condition",
                    aspect="meaning",
                    current_value="With food/meals" if is_curr_food else "Without food/empty stomach",
                    candidate_value="With food/meals" if is_cand_food else "Without food/empty stomach",
                    explanation="Direct conflict in food administration condition: taking with food vs on an empty stomach.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # B. Mechanical manipulation / crushing prohibition
        is_curr_no_crush = bool(re.search(r"\b(do\s+not\s+(?:crush|chew|divide)|must\s+not\s+be\s+crushed|swallow\s+whole)\b", lower_curr))
        is_curr_crush = bool(re.search(r"\b(may\s+be\s+(?:crushed|chewed)|can\s+be\s+crushed|chewable)\b", lower_curr))
        is_cand_no_crush = bool(re.search(r"\b(do\s+not\s+(?:crush|chew|divide)|must\s+not\s+be\s+crushed|swallow\s+whole)\b", lower_cand))
        is_cand_crush = bool(re.search(r"\b(may\s+be\s+(?:crushed|chewed)|can\s+be\s+crushed|chewable)\b", lower_cand))

        if (is_curr_no_crush and is_cand_crush) or (is_curr_crush and is_cand_no_crush):
            differences.append(
                DifferenceItem(
                    attribute="administration_condition",
                    aspect="meaning",
                    current_value="Swallow whole / Do not crush" if is_curr_no_crush else "May be crushed/chewed",
                    candidate_value="Swallow whole / Do not crush" if is_cand_no_crush else "May be crushed/chewed",
                    explanation="Direct conflict in tablet manipulation: prohibition on crushing vs permission to crush.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # 11. General Numerical Comparison (fallback for uncaught numbers)
        if not any(d.attribute in {"dose", "dose_unit"} for d in differences):
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

        # 12. Structural Disparity
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

        # 13. Textual Phrasing Difference
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

        # Deduplicate differences by attribute, current_value, candidate_value
        unique_diffs: List[DifferenceItem] = []
        seen_keys: Set[tuple] = set()
        for d in differences:
            key = (d.attribute, str(d.current_value), str(d.candidate_value))
            if key not in seen_keys:
                seen_keys.add(key)
                unique_diffs.append(d)
        return unique_diffs[:15]
