"""Six-dimensional regulatory comparison and false-match protection service.

Evaluates candidates across:
1. Meaning (semantic directive alignment, regulatory modality, administration conditions)
2. Template (regulatory-aware slot evaluation: Posology, Indication, Contraindication)
3. Context (operational setting, specialized population context, section concepts)
4. Structure (section, paragraph, table, bullet, numbered/stepwise instructions)
5. Format (quantitative vs qualitative, fixed dose vs range, abbreviation vs narrative)
6. Key Information (exact attribute comparisons with canonical clinical normalization)

Provides deterministic false-match protection to prevent superficial similarity
from overriding regulatory discrepancies.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from app.models.comparison import (
    DifferenceItem,
    DimensionEvaluation,
    DimensionStatus,
    ModelReasoning,
    MultiDimensionalMatch,
    ObservedSourceFacts,
    StructuredEvidence,
    TargetSourceFacts,
)
from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document import CanonicalSectionConcept
from app.services.key_information_extractor import (
    KeyInformationExtractor,
    normalize_dose_unit,
    normalize_frequency,
    normalize_route,
)


class MultiDimensionalComparator:
    """Evaluates regulatory content pairs across six distinct dimensions with false-match protection."""

    def __init__(self):
        self.extractor = KeyInformationExtractor()

    def compare(
        self,
        target_text: str,
        candidate: Any,
        target_key_info: Optional[KeyInformation] = None,
        target_section: Optional[str] = None,
        target_content_id: Optional[str] = None,
        target_document_id: Optional[str] = None,
        target_document_name: Optional[str] = None,
        target_subsection: Optional[str] = None,
        target_location: Optional[str] = None,
        target_page: Optional[int] = None,
        target_content_type: Optional[str] = None,
    ) -> Tuple[MultiDimensionalMatch, List[DifferenceItem], StructuredEvidence, Optional[str]]:
        """Run complete six-dimensional comparison between target text and candidate item.

        Returns:
            (MultiDimensionalMatch, List[DifferenceItem], StructuredEvidence, false_match_warning)
        """
        from app.services.compatibility.regulatory_adapter import adapt_for_comparison

        candidate: RegulatoryContentItem = adapt_for_comparison(candidate)
        curr_info = target_key_info or self.extractor.extract(target_text)
        cand_info = candidate.key_information or self.extractor.extract(candidate.text)

        # 1. Evaluate Key Information Dimension
        key_info_eval, key_diffs, key_false_reasons = self._evaluate_key_information(
            curr_info=curr_info,
            cand_info=cand_info,
            current_text=target_text,
            candidate_text=candidate.text,
        )
        for d in key_diffs:
            if not d.source_dimension:
                d.source_dimension = "key_information"

        # 2. Evaluate Context Dimension (Prescribing vs Study, Specialized populations, Section concepts)
        context_eval, context_diffs = self._evaluate_context(
            current_text=target_text,
            candidate_text=candidate.text,
            curr_section=target_section,
            cand_section=candidate.section,
        )
        for d in context_diffs:
            if not d.source_dimension:
                d.source_dimension = "context"

        # 3. Detect False Matches Across All Critical Regulatory Attributes
        false_match_reasons: List[str] = list(key_false_reasons)

        # Context discrepancy (e.g. Prescribing recommendation vs Clinical study observation or Special population)
        if context_eval.status == DimensionStatus.MISMATCH:
            false_match_reasons.append(context_eval.details)

        # Check for Dose / Unit / Route disparity when phrasing has high superficial similarity
        words_curr = set(re.findall(r"\b\w+\b", target_text.lower()))
        words_cand = set(re.findall(r"\b\w+\b", candidate.text.lower()))
        jaccard = len(words_curr.intersection(words_cand)) / max(len(words_curr.union(words_cand)), 1)

        if jaccard >= 0.4:
            # Dose unit check
            norm_curr_unit = normalize_dose_unit(curr_info.dose_unit)
            norm_cand_unit = normalize_dose_unit(cand_info.dose_unit)
            if norm_curr_unit and norm_cand_unit and norm_curr_unit != norm_cand_unit:
                unit_msg = f"Dose unit mismatch: target specifies '{curr_info.dose_unit}' but candidate specifies '{cand_info.dose_unit}'"
                if not any("Dose unit mismatch" in r for r in false_match_reasons):
                    false_match_reasons.append(unit_msg)

            if curr_info.dose and cand_info.dose and curr_info.dose.lower() != cand_info.dose.lower():
                dose_msg = f"Dose mismatch: target specifies '{curr_info.dose}' but candidate specifies '{cand_info.dose}'"
                if not any("Dose mismatch" in r for r in false_match_reasons):
                    false_match_reasons.append(dose_msg)

            norm_curr_route = normalize_route(curr_info.route)
            norm_cand_route = normalize_route(cand_info.route)
            if norm_curr_route and norm_cand_route and norm_curr_route != norm_cand_route:
                route_msg = f"Route mismatch: target specifies '{curr_info.route}' but candidate specifies '{cand_info.route}'"
                if not any("Route mismatch" in r for r in false_match_reasons):
                    false_match_reasons.append(route_msg)

        false_match_warning = (
            f"FALSE MATCH WARNING: High semantic similarity masks critical regulatory discrepancy ({'; '.join(false_match_reasons)})."
            if false_match_reasons
            else None
        )

        # 4. Evaluate Meaning Dimension (with modality, condition conflicts & false match awareness)
        meaning_eval, meaning_diffs = self._evaluate_meaning(
            current_text=target_text,
            candidate_text=candidate.text,
            curr_info=curr_info,
            cand_info=cand_info,
            has_false_match=bool(false_match_warning),
        )
        for d in meaning_diffs:
            if not d.source_dimension:
                d.source_dimension = "meaning"

        # 5. Evaluate Template Dimension (Regulatory-aware slot evaluation: Posology, Indication, Contraindication)
        template_eval, template_diffs = self._evaluate_template(
            current_text=target_text,
            candidate_text=candidate.text,
            curr_info=curr_info,
            cand_info=cand_info,
        )
        for d in template_diffs:
            if not d.source_dimension:
                d.source_dimension = "template"

        # 6. Evaluate Structure Dimension (Section, Paragraph, Table, Bullet, Numbered/Stepwise)
        structure_eval, structure_diffs = self._evaluate_structure(
            current_text=target_text,
            candidate_text=candidate.text,
            curr_section=target_section,
            cand_section=candidate.section,
            candidate_item=candidate,
        )
        for d in structure_diffs:
            if not d.source_dimension:
                d.source_dimension = "structure"

        # 7. Evaluate Format Dimension (Quantitative vs Qualitative, Fixed vs Range, Shorthand vs Narrative)
        format_eval, format_diffs = self._evaluate_format(
            current_text=target_text,
            candidate_text=candidate.text,
        )
        for d in format_diffs:
            if not d.source_dimension:
                d.source_dimension = "format"

        # Synthesize Overall Alignment
        overall_summary = self._generate_overall_summary(
            meaning=meaning_eval,
            template=template_eval,
            key_info=key_info_eval,
            context=context_eval,
            false_match_warning=false_match_warning,
        )

        match_result = MultiDimensionalMatch(
            meaning=meaning_eval,
            template=template_eval,
            context=context_eval,
            structure=structure_eval,
            format=format_eval,
            key_information=key_info_eval,
            overall_alignment_summary=overall_summary,
        )

        # Aggregate and deduplicate all structured differences
        raw_diffs = key_diffs + meaning_diffs + context_diffs + template_diffs + structure_diffs + format_diffs
        unique_diffs: List[DifferenceItem] = []
        seen_keys: Set[Tuple[str, str, str]] = set()
        for d in raw_diffs:
            k = (d.attribute, str(d.current_value), str(d.candidate_value))
            if k not in seen_keys:
                seen_keys.add(k)
                unique_diffs.append(d)

        # Assemble Structured Evidence (Observed facts vs Model interpretation)
        structured_evidence = self._assemble_evidence(
            candidate=candidate,
            cand_info=cand_info,
            match=match_result,
            diffs=unique_diffs,
            false_match_warning=false_match_warning,
            target_text=target_text,
            curr_info=curr_info,
            target_content_id=target_content_id,
            target_document_id=target_document_id,
            target_document_name=target_document_name,
            target_section=target_section,
            target_subsection=target_subsection,
            target_location=target_location,
            target_page=target_page,
            target_content_type=target_content_type,
        )

        return match_result, unique_diffs, structured_evidence, false_match_warning

    def _evaluate_key_information(
        self,
        curr_info: KeyInformation,
        cand_info: KeyInformation,
        current_text: str,
        candidate_text: str,
    ) -> Tuple[DimensionEvaluation, List[DifferenceItem], List[str]]:
        """Compare attributes and detect critical false matches with canonical normalization."""
        diffs: List[DifferenceItem] = []
        false_match_reasons: List[str] = []

        # Drug / Active Ingredient comparison
        if curr_info.drug and cand_info.drug and curr_info.drug.lower() != cand_info.drug.lower():
            reason = f"Drug mismatch: target specifies '{curr_info.drug}' but candidate specifies '{cand_info.drug}'"
            false_match_reasons.append(reason)
            diffs.append(
                DifferenceItem(
                    attribute="drug",
                    aspect="key_information",
                    current_value=curr_info.drug,
                    candidate_value=cand_info.drug,
                    explanation=f"Active substance differs from {curr_info.drug} to {cand_info.drug}.",
                    reviewer_attention_required=True,
                    regulatory_impact="CRITICAL",
                    difference_type="modification",
                )
            )
        elif (curr_info.drug and not cand_info.drug) or (not curr_info.drug and cand_info.drug):
            diffs.append(
                DifferenceItem(
                    attribute="drug",
                    aspect="key_information",
                    current_value=curr_info.drug or "Unspecified",
                    candidate_value=cand_info.drug or "Unspecified",
                    explanation="Drug specification present in only one passage.",
                    reviewer_attention_required=True,
                    regulatory_impact="MODERATE",
                    difference_type="modification",
                )
            )

        # Product comparison
        if curr_info.product and cand_info.product and curr_info.product.lower() != cand_info.product.lower():
            reason = f"Product mismatch: target specifies '{curr_info.product}' but candidate specifies '{cand_info.product}'"
            false_match_reasons.append(reason)
            diffs.append(
                DifferenceItem(
                    attribute="product",
                    aspect="key_information",
                    current_value=curr_info.product,
                    candidate_value=cand_info.product,
                    explanation=f"Commercial product differs from {curr_info.product} to {cand_info.product}.",
                    reviewer_attention_required=True,
                    regulatory_impact="CRITICAL",
                    difference_type="modification",
                )
            )

        # Population comparison
        if curr_info.population and cand_info.population and curr_info.population.lower() != cand_info.population.lower():
            reason = f"Population mismatch: target applies to '{curr_info.population}' but candidate applies to '{cand_info.population}'"
            false_match_reasons.append(reason)
            diffs.append(
                DifferenceItem(
                    attribute="population",
                    aspect="key_information",
                    current_value=curr_info.population,
                    candidate_value=cand_info.population,
                    explanation=f"Patient population disparity ({curr_info.population} vs {cand_info.population}).",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # Dose Unit comparison (e.g. 50 mg vs 50 mcg -> critical false-match)
        norm_curr_unit = normalize_dose_unit(curr_info.dose_unit)
        norm_cand_unit = normalize_dose_unit(cand_info.dose_unit)
        has_unit_mismatch = False
        if norm_curr_unit and norm_cand_unit and norm_curr_unit != norm_cand_unit:
            has_unit_mismatch = True
            reason = f"Dose unit mismatch: target specifies '{curr_info.dose_unit}' but candidate specifies '{cand_info.dose_unit}'"
            false_match_reasons.append(reason)
            diffs.append(
                DifferenceItem(
                    attribute="dose_unit",
                    aspect="key_information",
                    current_value=curr_info.dose_unit,
                    candidate_value=cand_info.dose_unit,
                    explanation=f"Dose unit disparity: target is '{curr_info.dose_unit}' while candidate is '{cand_info.dose_unit}'. Critical clinical risk of quantitative dosing discrepancy.",
                    reviewer_attention_required=True,
                    regulatory_impact="CRITICAL",
                    difference_type="modification",
                )
            )

        # Dose comparison (if not already flagged as dose unit mismatch)
        if curr_info.dose and cand_info.dose and curr_info.dose.lower().strip() != cand_info.dose.lower().strip():
            if not has_unit_mismatch:
                diffs.append(
                    DifferenceItem(
                        attribute="dose",
                        aspect="key_information",
                        current_value=curr_info.dose,
                        candidate_value=cand_info.dose,
                        explanation=f"Dose quantity differs from {curr_info.dose} to {cand_info.dose}.",
                        reviewer_attention_required=True,
                        regulatory_impact="MAJOR",
                        difference_type="modification",
                    )
                )

        # Frequency comparison with conservative canonical normalization (e.g. QD == once daily)
        norm_curr_freq = normalize_frequency(curr_info.frequency)
        norm_cand_freq = normalize_frequency(cand_info.frequency)
        if norm_curr_freq and norm_cand_freq and norm_curr_freq != norm_cand_freq:
            diffs.append(
                DifferenceItem(
                    attribute="frequency",
                    aspect="key_information",
                    current_value=curr_info.frequency,
                    candidate_value=cand_info.frequency,
                    explanation=f"Dosing frequency differs from {curr_info.frequency} to {cand_info.frequency}.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # Route comparison with conservative canonical normalization (e.g. PO == Oral)
        norm_curr_route = normalize_route(curr_info.route)
        norm_cand_route = normalize_route(cand_info.route)
        if norm_curr_route and norm_cand_route and norm_curr_route != norm_cand_route:
            diffs.append(
                DifferenceItem(
                    attribute="route",
                    aspect="key_information",
                    current_value=curr_info.route,
                    candidate_value=cand_info.route,
                    explanation=f"Administration route differs from {curr_info.route} to {cand_info.route}.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                    difference_type="modification",
                )
            )

        # Duration comparison
        if curr_info.duration and cand_info.duration and curr_info.duration.lower().strip() != cand_info.duration.lower().strip():
            diffs.append(
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

        # Indication comparison
        if curr_info.indication and cand_info.indication and curr_info.indication.lower().strip() != cand_info.indication.lower().strip():
            diffs.append(
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

        # Age Group comparison
        if curr_info.age_group and cand_info.age_group and curr_info.age_group.lower().strip() != cand_info.age_group.lower().strip():
            diffs.append(
                DifferenceItem(
                    attribute="age_group",
                    aspect="key_information",
                    current_value=curr_info.age_group,
                    candidate_value=cand_info.age_group,
                    explanation=f"Target age group differs: current specifies '{curr_info.age_group}', candidate specifies '{cand_info.age_group}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MODERATE",
                    difference_type="modification",
                )
            )

        # Determine Dimension Status
        if false_match_reasons:
            status = DimensionStatus.MISMATCH
            score = 0.2
            details = f"Critical regulatory mismatches detected: {'; '.join(false_match_reasons)}."
        elif diffs:
            status = DimensionStatus.PARTIAL
            score = 0.65
            details = f"Shared clinical intent with specific attribute variations in {', '.join(d.attribute for d in diffs)}."
        else:
            status = DimensionStatus.MATCH
            score = 1.0
            details = "All extracted key regulatory attributes align."

        dim_eval = DimensionEvaluation(
            dimension="key_information",
            status=status,
            score=score,
            details=details,
            observed_from_source=f"Candidate attributes: drug={cand_info.drug}, dose={cand_info.dose}, unit={cand_info.dose_unit}, pop={cand_info.population}, duration={cand_info.duration}",
            model_interpretation=details,
        )

        return dim_eval, diffs, false_match_reasons

    def _evaluate_meaning(
        self,
        current_text: str,
        candidate_text: str,
        curr_info: KeyInformation,
        cand_info: KeyInformation,
        has_false_match: bool,
    ) -> Tuple[DimensionEvaluation, List[DifferenceItem]]:
        """Evaluate semantic directive equivalence, regulatory modality, and condition conflicts."""
        meaning_diffs: List[DifferenceItem] = []
        lower_curr = current_text.lower()
        lower_cand = candidate_text.lower()

        # 1. Indication vs Contraindication conflict
        is_curr_contra = bool(re.search(r"\b(contraindicated|contraindication|do not use|hypersensitiv)\b", lower_curr))
        is_cand_contra = bool(re.search(r"\b(contraindicated|contraindication|do not use|hypersensitiv)\b", lower_cand))
        is_curr_ind = bool(re.search(r"\b(indicated|treatment of|management of|relief of)\b", lower_curr)) and not is_curr_contra
        is_cand_ind = bool(re.search(r"\b(indicated|treatment of|management of|relief of)\b", lower_cand)) and not is_cand_contra

        if (is_curr_ind and is_cand_contra) or (is_curr_contra and is_cand_ind):
            meaning_diffs.append(
                DifferenceItem(
                    attribute="directive_type",
                    aspect="meaning",
                    current_value="Indication" if is_curr_ind else "Contraindication",
                    candidate_value="Contraindication" if is_cand_contra else "Indication",
                    explanation="Opposing regulatory directives: therapeutic indication vs clinical contraindication.",
                    reviewer_attention_required=True,
                    regulatory_impact="CRITICAL",
                )
            )
            return DimensionEvaluation(
                dimension="meaning",
                status=DimensionStatus.MISMATCH,
                score=0.1,
                details="Meaning directly conflicts: one statement specifies a therapeutic indication while the other specifies a contraindication.",
                observed_from_source=candidate_text[:160],
                model_interpretation="Therapeutic indication versus clinical contraindication represents opposing regulatory directives.",
            ), meaning_diffs

        # 2. Administration Condition Conflicts (Food intake)
        is_curr_food = bool(re.search(r"\b(with\s+(?:food|meals?)|take\s+with\s+(?:food|meals?)|co-administered\s+with\s+food)\b", lower_curr))
        is_curr_fast = bool(re.search(r"\b(without\s+food|on\s+an\s+empty\s+stomach|fasting|1\s+hour\s+before\s+meals?)\b", lower_curr))
        is_cand_food = bool(re.search(r"\b(with\s+(?:food|meals?)|take\s+with\s+(?:food|meals?)|co-administered\s+with\s+food)\b", lower_cand))
        is_cand_fast = bool(re.search(r"\b(without\s+food|on\s+an\s+empty\s+stomach|fasting|1\s+hour\s+before\s+meals?)\b", lower_cand))

        if (is_curr_food and is_cand_fast) or (is_curr_fast and is_cand_food):
            meaning_diffs.append(
                DifferenceItem(
                    attribute="administration_condition",
                    aspect="meaning",
                    current_value="With food/meals" if is_curr_food else "Without food/empty stomach",
                    candidate_value="With food/meals" if is_cand_food else "Without food/empty stomach",
                    explanation="Direct conflict in food administration condition: taking with food vs on an empty stomach.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                )
            )
            return DimensionEvaluation(
                dimension="meaning",
                status=DimensionStatus.MISMATCH,
                score=0.25,
                details="Administration condition conflict: one directive requires administration with food/meals while the other specifies administration without food/on an empty stomach.",
                observed_from_source=candidate_text[:160],
                model_interpretation="Opposing dietary administration directives represent conflicting clinical guidance.",
            ), meaning_diffs

        # 3. Mechanical Manipulation / Crushing Prohibitions
        is_curr_no_crush = bool(re.search(r"\b(do\s+not\s+(?:crush|chew|divide)|must\s+not\s+be\s+crushed|swallow\s+whole)\b", lower_curr))
        is_curr_crush = bool(re.search(r"\b(may\s+be\s+(?:crushed|chewed)|can\s+be\s+crushed|chewable)\b", lower_curr))
        is_cand_no_crush = bool(re.search(r"\b(do\s+not\s+(?:crush|chew|divide)|must\s+not\s+be\s+crushed|swallow\s+whole)\b", lower_cand))
        is_cand_crush = bool(re.search(r"\b(may\s+be\s+(?:crushed|chewed)|can\s+be\s+crushed|chewable)\b", lower_cand))

        if (is_curr_no_crush and is_cand_crush) or (is_curr_crush and is_cand_no_crush):
            meaning_diffs.append(
                DifferenceItem(
                    attribute="administration_condition",
                    aspect="meaning",
                    current_value="Swallow whole / Do not crush" if is_curr_no_crush else "May be crushed/chewed",
                    candidate_value="Swallow whole / Do not crush" if is_cand_no_crush else "May be crushed/chewed",
                    explanation="Direct conflict in tablet manipulation: prohibition on crushing vs permission to crush.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                )
            )
            return DimensionEvaluation(
                dimension="meaning",
                status=DimensionStatus.MISMATCH,
                score=0.25,
                details="Administration prohibition conflict: one directive strictly prohibits crushing or chewing ('swallow whole / do not crush') while the other explicitly permits crushing ('may be crushed').",
                observed_from_source=candidate_text[:160],
                model_interpretation="Conflicting mechanical administration prohibitions cannot be safely interchanged.",
            ), meaning_diffs

        # 4. Regulatory Modality Shift (Mandatory vs Permissive)
        mandatory_terms = ["must", "shall", "required", "contraindicated", "do not"]
        advisory_terms = ["may", "should", "consider", "recommended", "optional"]
        curr_mand = [t for t in mandatory_terms if re.search(r"\b" + re.escape(t) + r"\b", lower_curr)]
        curr_adv = [t for t in advisory_terms if re.search(r"\b" + re.escape(t) + r"\b", lower_curr)]
        cand_mand = [t for t in mandatory_terms if re.search(r"\b" + re.escape(t) + r"\b", lower_cand)]
        cand_adv = [t for t in advisory_terms if re.search(r"\b" + re.escape(t) + r"\b", lower_cand)]

        is_modality_shift = (curr_mand and not curr_adv and cand_adv and not cand_mand) or (cand_mand and not cand_adv and curr_adv and not curr_mand)
        if is_modality_shift:
            c_val = "Mandatory (" + ", ".join(curr_mand) + ")" if curr_mand else "Advisory (" + ", ".join(curr_adv) + ")"
            cand_val = "Mandatory (" + ", ".join(cand_mand) + ")" if cand_mand else "Advisory (" + ", ".join(cand_adv) + ")"
            meaning_diffs.append(
                DifferenceItem(
                    attribute="modality",
                    aspect="meaning",
                    current_value=c_val,
                    candidate_value=cand_val,
                    explanation="Regulatory obligation level shifts between mandatory directive and permissive recommendation.",
                    reviewer_attention_required=True,
                    regulatory_impact="MODERATE",
                )
            )

        # 5. Core false-match divergence
        if has_false_match:
            return DimensionEvaluation(
                dimension="meaning",
                status=DimensionStatus.MISMATCH,
                score=0.3,
                details="Meaning diverges due to conflicting core clinical subject (different drug, target population, unit, or context).",
                observed_from_source=candidate_text[:160],
                model_interpretation="Conflicting core entities prevent regulatory directive equivalence.",
            ), meaning_diffs

        # 6. Shared regulatory dosage directives & timing differences
        curr_is_dose = bool(curr_info.dose or curr_info.frequency or "take" in lower_curr or "administer" in lower_curr)
        cand_is_dose = bool(cand_info.dose or cand_info.frequency or "take" in lower_cand or "administer" in lower_cand)

        if curr_is_dose and cand_is_dose:
            timing_diff = (
                ("prior to" in lower_curr and "following" in lower_cand)
                or ("following" in lower_curr and "prior to" in lower_cand)
                or ("rapid bolus" in lower_cand and "over" in lower_curr)
                or ("rapid bolus" in lower_curr and "over" in lower_cand)
            )
            dose_diff = bool(curr_info.dose and cand_info.dose and curr_info.dose.lower() != cand_info.dose.lower())

            if is_modality_shift:
                status = DimensionStatus.PARTIAL
                score = 0.60
                details = f"Dosage directives share clinical subject but exhibit a regulatory modality shift between binding requirement ('{', '.join(curr_mand or cand_mand)}') and advisory recommendation ('{', '.join(cand_adv or curr_adv)}')."
            elif timing_diff or dose_diff:
                status = DimensionStatus.PARTIAL
                score = 0.70
                details = "Dosage directives share general therapeutic purpose but differ in administration timing, rate, or dose quantity."
            else:
                status = DimensionStatus.MATCH
                score = 0.95
                details = "Both passages communicate equivalent dosage directives for patient administration."
        else:
            words_curr = set(re.findall(r"\b\w+\b", lower_curr))
            words_cand = set(re.findall(r"\b\w+\b", lower_cand))
            overlap = len(words_curr.intersection(words_cand))
            jaccard = overlap / max(len(words_curr.union(words_cand)), 1)
            if is_modality_shift:
                status = DimensionStatus.PARTIAL
                score = 0.60
                details = f"Passages share semantic terminology but differ in regulatory modality: binding requirement ('{', '.join(curr_mand or cand_mand)}') vs advisory recommendation ('{', '.join(cand_adv or curr_adv)}')."
            elif jaccard > 0.4:
                status = DimensionStatus.MATCH
                score = 0.85
                details = "Passages share high semantic terminology and aligned regulatory meaning."
            else:
                status = DimensionStatus.PARTIAL
                score = 0.60
                details = "Passages share general regulatory terminology with varying specific directives."

        return DimensionEvaluation(
            dimension="meaning",
            status=status,
            score=score,
            details=details,
            observed_from_source=candidate_text[:160],
            model_interpretation="Directives convey regulatory content meaning.",
        ), meaning_diffs

    def _evaluate_template(
        self,
        current_text: str,
        candidate_text: str,
        curr_info: KeyInformation,
        cand_info: KeyInformation,
    ) -> Tuple[DimensionEvaluation, List[DifferenceItem]]:
        """Evaluate regulatory-aware slot conformance across Posology, Indication, and Contraindication families."""
        template_diffs: List[DifferenceItem] = []
        lower_curr = current_text.lower()
        lower_cand = candidate_text.lower()

        # Slot extractors for Posology / Dosing family
        def extract_posology_slots(text: str, info: KeyInformation) -> Set[str]:
            slots: Set[str] = set()
            lower = text.lower()
            if info.population or re.search(r"\b(adults?|pediatric|children|elderly|geriatric|patients?)\b", lower):
                slots.add("Target Population")
            if re.search(r"\b(starting\s+dose|initial\s+dose|starting\s+dosage|initial\s+dosage|recommended\s+(?:starting\s+)?dose)\b", lower) or (info.dose and not re.search(r"\bmaximum\b", lower)):
                slots.add("Initial/Starting Dose")
            if info.frequency or re.search(r"\b(once\s+daily|twice\s+daily|every\s+\d+\s+hours?|daily|bid|tid|qd|as\s+needed)\b", lower):
                slots.add("Frequency")
            if re.search(r"\b(titrat|increase\s+by|every\s+\d+\s+(?:days|weeks)|adjust(?:ed)?)\b", lower):
                slots.add("Titration/Interval")
            if re.search(r"\b(maximum|not\s+to\s+exceed|max(?:\.|\s+dose))\b", lower):
                slots.add("Maximum Dose")
            if info.route or re.search(r"\b(oral|orally|by\s+mouth|intravenous|iv|subcutaneous|sc|im)\b", lower):
                slots.add("Administration Route")
            return slots

        # Slot extractors for Indication family
        def extract_indication_slots(text: str, info: KeyInformation) -> Set[str]:
            slots: Set[str] = set()
            lower = text.lower()
            if info.drug or info.product:
                slots.add("Drug/Product")
            if info.indication or re.search(r"\b(indicated\s+for|treatment\s+of|relief\s+of|management\s+of)\b", lower):
                slots.add("Indication/Condition")
            if info.population or re.search(r"\b(in\s+adults?|in\s+pediatric|in\s+children|in\s+patients)\b", lower):
                slots.add("Patient Population")
            if re.search(r"\b(as\s+monotherapy|in\s+combination\s+with|as\s+adjunct(?:ive)?|adjunct\s+to|concomitantly)\b", lower):
                slots.add("Monotherapy/Adjunct context")
            return slots

        # Slot extractors for Contraindication family
        def extract_contraindication_slots(text: str, info: KeyInformation) -> Set[str]:
            slots: Set[str] = set()
            lower = text.lower()
            if info.drug or info.product:
                slots.add("Drug/Product")
            if info.safety_information or re.search(r"\b(contraindicated\s+in|contraindication|do\s+not\s+use\s+if|hypersensitivity\s+to)\b", lower):
                slots.add("Contraindicated Condition/Population")
            return slots

        # Detect family
        def detect_family(text: str, info: KeyInformation) -> str:
            lower = text.lower()
            if re.search(r"\b(contraindicated|contraindication|do\s+not\s+use\s+in|do\s+not\s+use\s+if)\b", lower):
                return "CONTRAINDICATION"
            if re.search(r"\b(indicated\s+for|treatment\s+of|for\s+the\s+management\s+of|as\s+monotherapy)\b", lower):
                return "INDICATION"
            if info.dose or info.frequency or re.search(r"\b(dose|dosage|administer|take\s+\d+|starting\s+dose|titrat)\b", lower):
                return "POSOLOGY"
            return "NARRATIVE"

        curr_family = detect_family(current_text, curr_info)
        cand_family = detect_family(candidate_text, cand_info)

        if curr_family == "POSOLOGY" and cand_family == "POSOLOGY":
            curr_slots = extract_posology_slots(current_text, curr_info)
            cand_slots = extract_posology_slots(candidate_text, cand_info)
            matched = curr_slots.intersection(cand_slots)
            missing = curr_slots - cand_slots
            extra = cand_slots - curr_slots

            if len(matched) >= 2 and not missing:
                status = DimensionStatus.MATCH
                score = 0.95
                details = f"Both items conform to the POSOLOGY / DOSING template. Matched slots: [{', '.join(sorted(matched))}]."
            elif matched:
                status = DimensionStatus.PARTIAL
                score = round(0.55 + 0.35 * (len(matched) / max(len(curr_slots), 1)), 2)
                details = (
                    f"Partial POSOLOGY template alignment. Matched slots: [{', '.join(sorted(matched))}]. "
                    f"Missing candidate slots: [{', '.join(sorted(missing))}]."
                    + (f" Extra candidate slots: [{', '.join(sorted(extra))}]." if extra else "")
                )
            else:
                status = DimensionStatus.PARTIAL
                score = 0.50
                details = f"Disparate posology slots. Missing candidate slots: [{', '.join(sorted(missing))}]."

            return DimensionEvaluation(
                dimension="template",
                status=status,
                score=score,
                details=details,
                observed_from_source=f"Candidate Posology slots: [{', '.join(sorted(cand_slots)) if cand_slots else 'None'}]",
                model_interpretation="Posology dosing schema evaluated for slot completeness.",
            ), template_diffs

        elif curr_family == "INDICATION" and cand_family == "INDICATION":
            curr_slots = extract_indication_slots(current_text, curr_info)
            cand_slots = extract_indication_slots(candidate_text, cand_info)
            matched = curr_slots.intersection(cand_slots)
            missing = curr_slots - cand_slots
            extra = cand_slots - curr_slots

            if len(matched) >= 2 and not missing:
                status = DimensionStatus.MATCH
                score = 0.95
                details = f"Both items conform to the INDICATION template. Matched slots: [{', '.join(sorted(matched))}]."
            else:
                status = DimensionStatus.PARTIAL
                score = 0.65
                details = (
                    f"Partial INDICATION template alignment. Matched slots: [{', '.join(sorted(matched)) or 'None'}]. "
                    f"Missing candidate slots: [{', '.join(sorted(missing))}]."
                    + (f" Extra candidate slots: [{', '.join(sorted(extra))}]." if extra else "")
                )

            return DimensionEvaluation(
                dimension="template",
                status=status,
                score=score,
                details=details,
                observed_from_source=f"Candidate Indication slots: [{', '.join(sorted(cand_slots)) if cand_slots else 'None'}]",
                model_interpretation="Indication statement schema evaluated for slot completeness.",
            ), template_diffs

        elif curr_family == "CONTRAINDICATION" and cand_family == "CONTRAINDICATION":
            curr_slots = extract_contraindication_slots(current_text, curr_info)
            cand_slots = extract_contraindication_slots(candidate_text, cand_info)
            matched = curr_slots.intersection(cand_slots)
            status = DimensionStatus.MATCH if matched else DimensionStatus.PARTIAL
            score = 0.95 if matched else 0.65
            details = f"Both items conform to the CONTRAINDICATION template. Matched slots: [{', '.join(sorted(matched)) or 'General contraindication'}]."

            return DimensionEvaluation(
                dimension="template",
                status=status,
                score=score,
                details=details,
                observed_from_source=f"Candidate Contraindication slots: [{', '.join(sorted(cand_slots))}]",
                model_interpretation="Contraindication schema evaluated.",
            ), template_diffs

        elif curr_family != cand_family and curr_family != "NARRATIVE" and cand_family != "NARRATIVE":
            template_diffs.append(
                DifferenceItem(
                    attribute="template",
                    aspect="template",
                    current_value=curr_family,
                    candidate_value=cand_family,
                    explanation=f"Template schema disparity: current follows {curr_family} template, candidate follows {cand_family} template.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                )
            )
            return DimensionEvaluation(
                dimension="template",
                status=DimensionStatus.MISMATCH,
                score=0.30,
                details=f"Template schema disparity: current follows {curr_family} template schema while candidate follows {cand_family} template schema.",
                observed_from_source=f"Candidate template family: {cand_family}",
                model_interpretation="Template schemas differ fundamentally and cannot be directly interchanged.",
            ), template_diffs

        # Fallback for general narrative prose pattern (preserves 100% backward compatibility)
        return DimensionEvaluation(
            dimension="template",
            status=DimensionStatus.MATCH,
            score=0.80,
            details="Both statements adhere to narrative regulatory prose patterns.",
            observed_from_source="Narrative format pattern",
            model_interpretation="Standard regulatory paragraph template observed.",
        ), template_diffs

    def _evaluate_context(
        self,
        current_text: str,
        candidate_text: str,
        curr_section: Optional[str],
        cand_section: Optional[str],
    ) -> Tuple[DimensionEvaluation, List[DifferenceItem]]:
        """Differentiate operational setting, specialized clinical populations, and canonical section concepts."""
        context_diffs: List[DifferenceItem] = []
        lower_curr = current_text.lower()
        lower_cand = candidate_text.lower()

        # 1. Specialized Population Subgroup Context
        def detect_population_context(text: str) -> Optional[str]:
            lower = text.lower()
            if re.search(r"\b(renal\s+impairment|kidney\s+disease|crcl\b|creatinine\s+clearance|dialysis|esrd|gfr\b|<\s*30\s*ml/min)\b", lower):
                return "renal impairment"
            if re.search(r"\b(hepatic\s+impairment|liver\s+disease|cirrhosis|child-pugh)\b", lower):
                return "hepatic impairment"
            if re.search(r"\b(pregnancy|pregnant\s+women|teratogen|fetal\s+harm|first\s+trimester)\b", lower):
                return "pregnancy"
            if re.search(r"\b(lactation|nursing\s+mothers|breast\s*feeding|human\s+milk)\b", lower):
                return "lactation"
            if re.search(r"\b(pediatric|children|child\b|infants?|neonates?|2\s+to\s+12\s+years|under\s+18\s+years)\b", lower):
                return "pediatric"
            if re.search(r"\b(geriatric|elderly|65\s+years\s+(?:of\s+age\s+)?and\s+older)\b", lower):
                return "geriatric"
            if re.search(r"\b(adults?|adult\s+patients?)\b", lower):
                return "general adult"
            return None

        curr_pop_ctx = detect_population_context(current_text)
        cand_pop_ctx = detect_population_context(candidate_text)

        if curr_pop_ctx and cand_pop_ctx and curr_pop_ctx != cand_pop_ctx:
            context_diffs.append(
                DifferenceItem(
                    attribute="context",
                    aspect="context",
                    current_value=curr_pop_ctx,
                    candidate_value=cand_pop_ctx,
                    explanation=f"Specialized population context disparity: current applies to '{curr_pop_ctx}', whereas candidate applies to '{cand_pop_ctx}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                )
            )
            return DimensionEvaluation(
                dimension="context",
                status=DimensionStatus.MISMATCH,
                score=0.35,
                details=f"Specialized population context disparity: current applies to {curr_pop_ctx}, whereas candidate applies to {cand_pop_ctx}.",
                observed_from_source=f"Subgroup: {cand_pop_ctx}",
                model_interpretation="Specialized clinical subgroup directives cannot be interchanged with general adult directives without clinical verification.",
            ), context_diffs

        # 2. Canonical Section Concept Alignment
        def normalize_section_concept(sec: Optional[str]) -> Optional[str]:
            if not sec:
                return None
            lower = sec.lower().strip()
            if re.search(r"\bcontraindications?\b", lower):
                return "Contraindications"
            if re.search(r"\b(?:overdose|overdosage)\b", lower):
                return "Overdosage"
            if re.search(r"\b(?:adverse\s+reactions?|undesirable\s+effects?|side\s+effects?)\b", lower):
                return "Adverse Reactions"
            if re.search(r"\b(?:warnings?|precautions?)\b", lower):
                return "Warnings and Precautions"
            if re.search(r"\b(?:dosage|posology|administration|how\s+to\s+take)\b", lower):
                return "Dosage and Administration"
            if re.search(r"\b(?:indications?|therapeutic\s+indications?|usage)\b", lower):
                return "Indications and Usage"
            if re.search(r"\b(?:clinical\s+pharmacology|pharmacodynamics?|pharmacokinetics?)\b", lower):
                return "Clinical Pharmacology"
            if re.search(r"\b(?:specific\s+populations?|special\s+populations?)\b", lower):
                return "Use in Specific Populations"
            return sec

        norm_curr_sec = normalize_section_concept(curr_section)
        norm_cand_sec = normalize_section_concept(cand_section)

        if norm_curr_sec and norm_cand_sec and norm_curr_sec != norm_cand_sec:
            # Check for material section mismatch
            material_incompatible_pairs = {
                ("Dosage and Administration", "Adverse Reactions"),
                ("Dosage and Administration", "Overdosage"),
                ("Dosage and Administration", "Indications and Usage"),
                ("Indications and Usage", "Adverse Reactions"),
                ("Indications and Usage", "Contraindications"),
                ("Contraindications", "Dosage and Administration"),
                ("Warnings and Precautions", "Dosage and Administration"),
            }
            is_incompatible = (
                (norm_curr_sec, norm_cand_sec) in material_incompatible_pairs
                or (norm_cand_sec, norm_curr_sec) in material_incompatible_pairs
            )

            context_diffs.append(
                DifferenceItem(
                    attribute="context",
                    aspect="context",
                    current_value=curr_section,
                    candidate_value=cand_section,
                    explanation=f"Regulatory section context disparity: target content is from '{curr_section}', candidate is from '{cand_section}'.",
                    reviewer_attention_required=True,
                    regulatory_impact="MODERATE",
                )
            )

            if is_incompatible:
                return DimensionEvaluation(
                    dimension="context",
                    status=DimensionStatus.MISMATCH,
                    score=0.35,
                    details=f"Regulatory section context disparity: target content is from '{curr_section}', whereas candidate originates from '{cand_section}'.",
                    observed_from_source=f"Section: {cand_section}",
                    model_interpretation=f"Cross-section reuse between '{curr_section}' and '{cand_section}' represents disparate regulatory purposes.",
                ), context_diffs
            else:
                return DimensionEvaluation(
                    dimension="context",
                    status=DimensionStatus.PARTIAL,
                    score=0.65,
                    details=f"Related regulatory sections compared: target is from '{curr_section}', candidate is from '{cand_section}'.",
                    observed_from_source=f"Section: {cand_section}",
                    model_interpretation="Section boundaries differ; reviewer attention required.",
                ), context_diffs

        # 3. Clinical trial / study narrative vs Prescribing directive
        is_study_current = bool(re.search(r"\b(clinical\s+trial|patients\s+received|study\s+\d+|in\s+trials?|experienced\s+nausea|adverse\s+events?|were\s+monitored)\b", lower_curr))
        is_study_candidate = bool(re.search(r"\b(clinical\s+trial|patients\s+received|study\s+\d+|in\s+trials?|experienced\s+nausea|adverse\s+events?|were\s+monitored)\b", lower_cand))

        if is_study_current != is_study_candidate:
            context_diffs.append(
                DifferenceItem(
                    attribute="context",
                    aspect="context",
                    current_value="Clinical study observation" if is_study_current else "Prescribing directive",
                    candidate_value="Clinical study observation" if is_study_candidate else "Prescribing directive",
                    explanation="Context mismatch: clinical study observation data compared against operational prescribing directives.",
                    reviewer_attention_required=True,
                    regulatory_impact="MAJOR",
                )
            )
            return DimensionEvaluation(
                dimension="context",
                status=DimensionStatus.MISMATCH,
                score=0.35,
                details="Context mismatch: one statement describes clinical study observations, whereas the other provides prescribing recommendations.",
                observed_from_source="Study observation phraseology detected in source",
                model_interpretation="Regulatory purpose differs: trial observation data cannot be directly reused as prescribing directive.",
            ), context_diffs

        # 4. Indication vs Contraindication operational context
        is_contra_curr = bool(re.search(r"\b(contraindicated|contraindication|do\s+not\s+use)\b", lower_curr))
        is_contra_cand = bool(re.search(r"\b(contraindicated|contraindication|do\s+not\s+use)\b", lower_cand))
        is_ind_curr = bool(re.search(r"\b(indicated|treatment\s+of|management\s+of)\b", lower_curr)) and not is_contra_curr
        is_ind_cand = bool(re.search(r"\b(indicated|treatment\s+of|management\s+of)\b", lower_cand)) and not is_contra_cand

        if (is_ind_curr and is_contra_cand) or (is_contra_curr and is_ind_cand):
            return DimensionEvaluation(
                dimension="context",
                status=DimensionStatus.MISMATCH,
                score=0.25,
                details="Context mismatch: therapeutic indication context compared against contraindication safety context.",
                observed_from_source="Opposing therapeutic intent vs contraindication context",
                model_interpretation="Indication and Contraindication contexts cannot be cross-applied.",
            ), context_diffs

        return DimensionEvaluation(
            dimension="context",
            status=DimensionStatus.MATCH,
            score=0.90,
            details="Contexts align: both describe operational prescribing directives.",
            observed_from_source=f"Section: {cand_section or 'Standard Prescribing Information'}",
            model_interpretation="Aligned clinical intent and regulatory context.",
        ), context_diffs

    def _evaluate_structure(
        self,
        current_text: str,
        candidate_text: str,
        curr_section: Optional[str],
        cand_section: Optional[str],
        candidate_item: Optional[Any] = None,
    ) -> Tuple[DimensionEvaluation, List[DifferenceItem]]:
        """Compare structural entity: section, paragraph, table row, bullet, numbered/stepwise instructions."""
        struct_diffs: List[DifferenceItem] = []

        def detect_structure_type(text: str, item: Optional[Any] = None) -> str:
            clean = text.strip()
            # 1. Table Row
            if "|" in clean or "\t" in clean or (item and getattr(item, "content_type", None) == "table_row"):
                return "table_row"
            # 2. Numbered / Stepwise procedural instruction
            if re.search(r"^(?:step\s+\d+|[0-9]+\.\s+|initial:|maintenance:|titration:)", clean, re.I | re.M) or (item and getattr(item, "content_type", None) == "numbered_item"):
                return "numbered_step"
            # 3. Bullet list item
            if clean.startswith(("-", "•", "*")) or "\n-" in text or (item and getattr(item, "content_type", None) == "bullet"):
                return "bullet_item"
            # 4. Structured field
            if (item and getattr(item, "content_type", None) == "structured_field") or re.search(r"^[A-Z][a-zA-Z\s]{2,25}:\s+[^\n]+$", clean):
                return "structured_field"
            # 5. Heading
            if clean.startswith("#") or (item and getattr(item, "content_type", None) == "heading"):
                return "heading"
            # 6. Default narrative paragraph
            return "paragraph"

        curr_type = detect_structure_type(current_text)
        cand_type = detect_structure_type(candidate_text, candidate_item)

        if curr_type == cand_type:
            return DimensionEvaluation(
                dimension="structure",
                status=DimensionStatus.MATCH,
                score=0.95,
                details=f"Structural equivalence: both items structured as {curr_type.replace('_', ' ')}.",
                observed_from_source=f"Structure: {cand_type}",
                model_interpretation="Direct structural interchangeability.",
            ), struct_diffs

        struct_diffs.append(
            DifferenceItem(
                attribute="structure",
                aspect="structure",
                current_value=curr_type.replace("_", " "),
                candidate_value=cand_type.replace("_", " "),
                explanation=f"Structural format distinction: {curr_type.replace('_', ' ')} compared against {cand_type.replace('_', ' ')}.",
                reviewer_attention_required=True,
                regulatory_impact="MODERATE",
            )
        )

        if curr_type == "table_row" or cand_type == "table_row":
            return DimensionEvaluation(
                dimension="structure",
                status=DimensionStatus.MISMATCH,
                score=0.40,
                details="Structural disparity: tabular matrix content compared against non-tabular narrative content.",
                observed_from_source="Tabular matrix vs narrative structure",
                model_interpretation="Structure conversion required to incorporate candidate into document.",
            ), struct_diffs

        if curr_type == "numbered_step" or cand_type == "numbered_step":
            return DimensionEvaluation(
                dimension="structure",
                status=DimensionStatus.PARTIAL,
                score=0.70,
                details="Structural distinction: sequential numbered/stepwise procedural instructions compared against narrative/bulleted content.",
                observed_from_source="Numbered stepwise structure vs narrative/bullet",
                model_interpretation="Structural formatting required to align stepwise procedures.",
            ), struct_diffs

        if curr_type == "bullet_item" or cand_type == "bullet_item":
            return DimensionEvaluation(
                dimension="structure",
                status=DimensionStatus.PARTIAL,
                score=0.75,
                details="Structural distinction: bulleted listing compared against continuous narrative paragraph.",
                observed_from_source="Bullet list vs paragraph structure",
                model_interpretation="Minor structural adaptation required.",
            ), struct_diffs

        return DimensionEvaluation(
            dimension="structure",
            status=DimensionStatus.PARTIAL,
            score=0.80,
            details=f"Structural variation: {curr_type.replace('_', ' ')} vs {cand_type.replace('_', ' ')}.",
            observed_from_source=f"Structure: {cand_type}",
            model_interpretation="Reviewer adaptation required for structural layout.",
        ), struct_diffs

    def _evaluate_format(self, current_text: str, candidate_text: str) -> Tuple[DimensionEvaluation, List[DifferenceItem]]:
        """Deepen format evaluation: quantitative vs qualitative, fixed vs range, shorthand vs narrative."""
        format_diffs: List[DifferenceItem] = []

        # Explicit quantitative dosing pattern (numerical value + explicit pharmaceutical unit)
        quant_dose_regex = re.compile(
            r"\b\d+(?:\.\d+)?(?:\s*(?:to|-)\s*\d+(?:\.\d+)?)?\s*(?:mg|g|mcg|ml|tablets?|capsules?|drops?|units?|mEq|%)\b",
            re.IGNORECASE,
        )
        curr_has_quant = bool(quant_dose_regex.search(current_text))
        cand_has_quant = bool(quant_dose_regex.search(candidate_text))

        # Range dosage regex
        dose_range_regex = re.compile(
            r"\b\d+(?:\.\d+)?\s*(?:to|-)\s*\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|tablets?|capsules?)\b",
            re.IGNORECASE,
        )
        curr_is_range = bool(dose_range_regex.search(current_text))
        cand_is_range = bool(dose_range_regex.search(candidate_text))

        # Abbreviated clinical shorthand pattern (e.g. 50 mg PO BID, 20 mg PO QD)
        shorthand_regex = re.compile(
            r"\b\d+\s*(?:mg|g|mcg|ml)\s+(?:PO|IV|SC|IM)\s+(?:QD|BID|TID|QID|PRN|q\s*\d+\s*h)\b",
            re.IGNORECASE,
        )
        curr_is_shorthand = bool(shorthand_regex.search(current_text))
        cand_is_shorthand = bool(shorthand_regex.search(candidate_text))

        # 1. Quantitative vs Qualitative disparity
        if curr_has_quant != cand_has_quant:
            c_val = "Quantitative specification" if curr_has_quant else "Qualitative guidance"
            cand_val = "Quantitative specification" if cand_has_quant else "Qualitative guidance"
            format_diffs.append(
                DifferenceItem(
                    attribute="format",
                    aspect="format",
                    current_value=c_val,
                    candidate_value=cand_val,
                    explanation="Format distinction: one statement specifies explicit quantitative clinical dosing parameters, whereas the other provides purely qualitative guidance.",
                    reviewer_attention_required=True,
                    regulatory_impact="MODERATE",
                )
            )
            return DimensionEvaluation(
                dimension="format",
                status=DimensionStatus.PARTIAL,
                score=0.60,
                details="Format distinction: one statement specifies explicit quantitative clinical dosing parameters, whereas the other provides purely qualitative guidance.",
                observed_from_source=cand_val,
                model_interpretation="Reviewer adaptation required to harmonize quantitative dosing specifications.",
            ), format_diffs

        # 2. Fixed dose vs Dose range disparity
        if curr_has_quant and cand_has_quant and (curr_is_range != cand_is_range):
            c_val = "Dose range (titration)" if curr_is_range else "Fixed dose"
            cand_val = "Dose range (titration)" if cand_is_range else "Fixed dose"
            format_diffs.append(
                DifferenceItem(
                    attribute="format",
                    aspect="format",
                    current_value=c_val,
                    candidate_value=cand_val,
                    explanation="Format distinction: fixed single-value dosage format compared against a titrated dosage range.",
                    reviewer_attention_required=True,
                    regulatory_impact="MODERATE",
                )
            )
            return DimensionEvaluation(
                dimension="format",
                status=DimensionStatus.PARTIAL,
                score=0.75,
                details="Format distinction: fixed single-value dosage format compared against a titrated dosage range.",
                observed_from_source=cand_val,
                model_interpretation="Dose range requires adaptation to align with fixed or titrated dosing schema.",
            ), format_diffs

        # 3. Abbreviated clinical shorthand vs Narrative prose
        if curr_is_shorthand != cand_is_shorthand:
            c_val = "Abbreviated clinical shorthand" if curr_is_shorthand else "Narrative regulatory prose"
            cand_val = "Abbreviated clinical shorthand" if cand_is_shorthand else "Narrative regulatory prose"
            format_diffs.append(
                DifferenceItem(
                    attribute="format",
                    aspect="format",
                    current_value=c_val,
                    candidate_value=cand_val,
                    explanation="Format distinction: abbreviated clinical prescription shorthand compared against full regulatory narrative prose.",
                    reviewer_attention_required=False,
                    regulatory_impact="MINOR",
                )
            )
            return DimensionEvaluation(
                dimension="format",
                status=DimensionStatus.PARTIAL,
                score=0.80,
                details="Format distinction: abbreviated clinical prescription shorthand compared against full regulatory narrative prose.",
                observed_from_source=cand_val,
                model_interpretation="Minor phrasing expansion required to convert shorthand to standard regulatory narrative prose.",
            ), format_diffs

        # Aligned formats
        if curr_has_quant and cand_has_quant:
            return DimensionEvaluation(
                dimension="format",
                status=DimensionStatus.MATCH,
                score=0.95,
                details="Both statements format clinical directives with explicit quantitative numerical parameters.",
                observed_from_source="Quantitative dosing parameter format",
                model_interpretation="Compatible clinical dosing format.",
            ), format_diffs

        return DimensionEvaluation(
            dimension="format",
            status=DimensionStatus.MATCH,
            score=0.85,
            details="Both statements utilize qualitative clinical prose format.",
            observed_from_source="Narrative prose format",
            model_interpretation="Format aligns.",
        ), format_diffs

    def _generate_overall_summary(
        self,
        meaning: DimensionEvaluation,
        template: DimensionEvaluation,
        key_info: DimensionEvaluation,
        context: DimensionEvaluation,
        false_match_warning: Optional[str],
    ) -> str:
        if false_match_warning:
            return f"FALSE MATCH ALERT: {false_match_warning}"
        if context.status == DimensionStatus.MISMATCH:
            return f"Context Discrepancy: {context.details}"
        if key_info.status == DimensionStatus.MATCH and meaning.status == DimensionStatus.MATCH:
            return "Strong Multi-Dimensional Alignment across meaning, template, and key parameters."
        if key_info.status == DimensionStatus.PARTIAL or meaning.status == DimensionStatus.PARTIAL:
            return "Moderate Multi-Dimensional Alignment: shared regulatory template with specific attribute variations."
        return "Low Alignment: significant divergence in key parameters or regulatory context."

    def _assemble_evidence(
        self,
        candidate: RegulatoryContentItem,
        cand_info: KeyInformation,
        match: MultiDimensionalMatch,
        diffs: List[DifferenceItem],
        false_match_warning: Optional[str],
        target_text: Optional[str] = None,
        curr_info: Optional[KeyInformation] = None,
        target_content_id: Optional[str] = None,
        target_document_id: Optional[str] = None,
        target_document_name: Optional[str] = None,
        target_section: Optional[str] = None,
        target_subsection: Optional[str] = None,
        target_location: Optional[str] = None,
        target_page: Optional[int] = None,
        target_content_type: Optional[str] = None,
    ) -> StructuredEvidence:
        """Assemble two-tier structured evidence keeping observed facts strictly separate from interpretation."""
        cand_meta = candidate.metadata or {}

        # Tier 1: Facts directly observed from external source
        observed = ObservedSourceFacts(
            source=candidate.source,
            source_url=candidate.source_url,
            source_identifier=candidate.source_identifier,
            document_name=candidate.document_name,
            version=candidate.version,
            date=candidate.date,
            section=candidate.section,
            location=candidate.location,  # Page/paragraph/table/section (NOT LOINC code)
            loinc_code=candidate.loinc_code or cand_meta.get("loinc_code"),
            exact_quote=candidate.text,
            extracted_drug=cand_info.drug,
            extracted_dose=cand_info.dose,
            extracted_population=cand_info.population,
            extracted_indication=cand_info.indication,
            # Phase 3 Step 4 Provenance extensions:
            content_id=candidate.content_id,
            document_id=candidate.document_id or cand_meta.get("document_id"),
            subsection=candidate.subsection or cand_meta.get("section_number"),
            page=candidate.page if candidate.page is not None else cand_meta.get("page"),
            content_type=candidate.content_type or cand_meta.get("chunk_type"),
            structure_path=cand_meta.get("structure_path"),
            cross_sources=cand_meta.get("cross_sources"),
            duplicate_provenance=cand_meta.get("duplicate_provenance"),
        )

        # Tier 2: Model / Algorithmic reasoning grounded in observed facts
        reasoning = ModelReasoning(
            similarity_rationale=match.meaning.details,
            difference_rationale="; ".join(d.explanation for d in diffs) if diffs else "No material parameter differences observed.",
            adaptation_guidance=(
                f"Candidate requires adaptation for: {', '.join(sorted(set(d.attribute for d in diffs)))}."
                if diffs
                else "Candidate is suitable for direct review consideration."
            ),
            false_match_rationale=false_match_warning,
        )

        # Target Source Facts (symmetric direct observed facts from target internal document)
        target_facts: Optional[TargetSourceFacts] = None
        if (
            target_content_id is not None
            or target_document_id is not None
            or target_document_name is not None
            or target_section is not None
            or target_subsection is not None
            or target_location is not None
            or target_page is not None
            or target_content_type is not None
            or curr_info is not None
        ):
            target_facts = TargetSourceFacts(
                target_content_id=target_content_id,
                target_document_id=target_document_id,
                target_document_name=target_document_name,
                target_section=target_section,
                target_subsection=target_subsection,
                target_location=target_location,
                target_page=target_page,
                target_content_type=target_content_type,
                extracted_drug=curr_info.drug if curr_info else None,
                extracted_dose=curr_info.dose if curr_info else None,
                extracted_population=curr_info.population if curr_info else None,
                extracted_indication=curr_info.indication if curr_info else None,
            )

        return StructuredEvidence(
            observed_from_source=observed,
            model_interpretation=reasoning,
            target_facts=target_facts,
        )
