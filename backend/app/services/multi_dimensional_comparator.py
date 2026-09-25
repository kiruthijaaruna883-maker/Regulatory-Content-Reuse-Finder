"""Six-dimensional regulatory comparison and false-match protection service.

Evaluates candidates across:
1. Meaning (semantic directive alignment)
2. Template (regulatory sentence pattern: population + drug + dose + frequency)
3. Context (prescribing recommendation vs clinical trial observation)
4. Structure (section, paragraph, table, bullet)
5. Format (sentence, numerical specification, bullet list)
6. Key Information (exact attribute comparisons)

Provides deterministic false-match protection to prevent superficial similarity
from overriding regulatory discrepancies.
"""

import re
from typing import Any, List, Optional, Tuple
from app.models.comparison import (
    DifferenceItem,
    DimensionEvaluation,
    DimensionStatus,
    ModelReasoning,
    MultiDimensionalMatch,
    ObservedSourceFacts,
    StructuredEvidence,
)
from app.models.content import KeyInformation, RegulatoryContentItem
from app.services.key_information_extractor import KeyInformationExtractor


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

        # 2. Evaluate Context Dimension (Prescribing vs Study past treatment vs Indication/Safety)
        context_eval = self._evaluate_context(
            current_text=target_text,
            candidate_text=candidate.text,
            curr_section=target_section,
            cand_section=candidate.section,
        )

        # 3. Detect False Matches Across All Critical Regulatory Attributes
        false_match_reasons: List[str] = list(key_false_reasons)

        # Context discrepancy (e.g. Prescribing recommendation vs Clinical study observation)
        if context_eval.status == DimensionStatus.MISMATCH:
            false_match_reasons.append(context_eval.details)

        # Check for Dose / Route disparity when phrasing has high superficial similarity
        words_curr = set(re.findall(r"\b\w+\b", target_text.lower()))
        words_cand = set(re.findall(r"\b\w+\b", candidate.text.lower()))
        jaccard = len(words_curr.intersection(words_cand)) / max(len(words_curr.union(words_cand)), 1)

        if jaccard >= 0.4:
            if curr_info.dose and cand_info.dose and curr_info.dose.lower() != cand_info.dose.lower():
                dose_msg = f"Dose mismatch: target specifies '{curr_info.dose}' but candidate specifies '{cand_info.dose}'"
                if not any("Dose mismatch" in r for r in false_match_reasons):
                    false_match_reasons.append(dose_msg)
            if curr_info.route and cand_info.route and curr_info.route.lower() != cand_info.route.lower():
                route_msg = f"Route mismatch: target specifies '{curr_info.route}' but candidate specifies '{cand_info.route}'"
                if not any("Route mismatch" in r for r in false_match_reasons):
                    false_match_reasons.append(route_msg)

        false_match_warning = (
            f"FALSE MATCH WARNING: High semantic similarity masks critical regulatory discrepancy ({'; '.join(false_match_reasons)})."
            if false_match_reasons
            else None
        )

        # 4. Evaluate Meaning Dimension (with false match & directive awareness)
        meaning_eval = self._evaluate_meaning(
            current_text=target_text,
            candidate_text=candidate.text,
            curr_info=curr_info,
            cand_info=cand_info,
            has_false_match=bool(false_match_warning),
        )

        # 5. Evaluate Template Dimension (Regulatory sentence structure)
        template_eval = self._evaluate_template(curr_info=curr_info, cand_info=cand_info)

        # 6. Evaluate Structure Dimension (Section, Paragraph, Table, Bullet)
        structure_eval = self._evaluate_structure(
            current_text=target_text,
            candidate_text=candidate.text,
            curr_section=target_section,
            cand_section=candidate.section,
        )

        # 7. Evaluate Format Dimension (Sentence, Numerical, Bullet)
        format_eval = self._evaluate_format(
            current_text=target_text,
            candidate_text=candidate.text,
        )

        # Synthesize Overall Alignment
        overall_summary = self._generate_overall_summary(
            meaning=meaning_eval,
            template=template_eval,
            key_info=key_info_eval,
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

        # Assemble Structured Evidence (Observed facts vs Model interpretation)
        structured_evidence = self._assemble_evidence(
            candidate=candidate,
            cand_info=cand_info,
            match=match_result,
            diffs=key_diffs,
            false_match_warning=false_match_warning,
        )

        return match_result, key_diffs, structured_evidence, false_match_warning

    def _evaluate_key_information(
        self,
        curr_info: KeyInformation,
        cand_info: KeyInformation,
        current_text: str,
        candidate_text: str,
    ) -> Tuple[DimensionEvaluation, List[DifferenceItem], List[str]]:
        """Compare attributes and detect critical false matches."""
        diffs: List[DifferenceItem] = []
        false_match_reasons: List[str] = []

        # Drug / Active Ingredient comparison
        if curr_info.drug and cand_info.drug and curr_info.drug.lower() != cand_info.drug.lower():
            reason = f"Drug mismatch: target specifies '{curr_info.drug}' but candidate specifies '{cand_info.drug}'"
            false_match_reasons.append(reason)
            diffs.append(
                DifferenceItem(
                    attribute="drug",
                    current_value=curr_info.drug,
                    candidate_value=cand_info.drug,
                    explanation=f"Active substance differs from {curr_info.drug} to {cand_info.drug}.",
                    reviewer_attention_required=True,
                )
            )
        elif (curr_info.drug and not cand_info.drug) or (not curr_info.drug and cand_info.drug):
            diffs.append(
                DifferenceItem(
                    attribute="drug",
                    current_value=curr_info.drug or "Unspecified",
                    candidate_value=cand_info.drug or "Unspecified",
                    explanation="Drug specification present in only one passage.",
                    reviewer_attention_required=True,
                )
            )

        # Product comparison
        if curr_info.product and cand_info.product and curr_info.product.lower() != cand_info.product.lower():
            reason = f"Product mismatch: target specifies '{curr_info.product}' but candidate specifies '{cand_info.product}'"
            false_match_reasons.append(reason)
            diffs.append(
                DifferenceItem(
                    attribute="product",
                    current_value=curr_info.product,
                    candidate_value=cand_info.product,
                    explanation=f"Commercial product differs from {curr_info.product} to {cand_info.product}.",
                    reviewer_attention_required=True,
                )
            )

        # Population comparison
        if curr_info.population and cand_info.population and curr_info.population.lower() != cand_info.population.lower():
            reason = f"Population mismatch: target applies to '{curr_info.population}' but candidate applies to '{cand_info.population}'"
            false_match_reasons.append(reason)
            diffs.append(
                DifferenceItem(
                    attribute="population",
                    current_value=curr_info.population,
                    candidate_value=cand_info.population,
                    explanation=f"Patient population disparity ({curr_info.population} vs {cand_info.population}).",
                    reviewer_attention_required=True,
                )
            )

        # Dose comparison
        if curr_info.dose and cand_info.dose and curr_info.dose.lower() != cand_info.dose.lower():
            diffs.append(
                DifferenceItem(
                    attribute="dose",
                    current_value=curr_info.dose,
                    candidate_value=cand_info.dose,
                    explanation=f"Dose quantity differs from {curr_info.dose} to {cand_info.dose}.",
                    reviewer_attention_required=True,
                )
            )

        # Frequency comparison
        if curr_info.frequency and cand_info.frequency and curr_info.frequency.lower() != cand_info.frequency.lower():
            diffs.append(
                DifferenceItem(
                    attribute="frequency",
                    current_value=curr_info.frequency,
                    candidate_value=cand_info.frequency,
                    explanation=f"Dosing frequency differs from {curr_info.frequency} to {cand_info.frequency}.",
                    reviewer_attention_required=True,
                )
            )

        # Route comparison
        if curr_info.route and cand_info.route and curr_info.route.lower() != cand_info.route.lower():
            diffs.append(
                DifferenceItem(
                    attribute="route",
                    current_value=curr_info.route,
                    candidate_value=cand_info.route,
                    explanation=f"Administration route differs from {curr_info.route} to {cand_info.route}.",
                    reviewer_attention_required=True,
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
            observed_from_source=f"Candidate attributes: drug={cand_info.drug}, dose={cand_info.dose}, pop={cand_info.population}",
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
    ) -> DimensionEvaluation:
        """Evaluate semantic directive equivalence."""
        lower_curr = current_text.lower()
        lower_cand = candidate_text.lower()

        # Check Indication vs Contraindication conflict
        is_curr_contra = bool(re.search(r"\b(contraindicated|contraindication|do not use|hypersensitiv)\b", lower_curr))
        is_cand_contra = bool(re.search(r"\b(contraindicated|contraindication|do not use|hypersensitiv)\b", lower_cand))
        is_curr_ind = bool(re.search(r"\b(indicated|treatment of|management of|relief of)\b", lower_curr)) and not is_curr_contra
        is_cand_ind = bool(re.search(r"\b(indicated|treatment of|management of|relief of)\b", lower_cand)) and not is_cand_contra

        if (is_curr_ind and is_cand_contra) or (is_curr_contra and is_cand_ind):
            return DimensionEvaluation(
                dimension="meaning",
                status=DimensionStatus.MISMATCH,
                score=0.1,
                details="Meaning directly conflicts: one statement specifies a therapeutic indication while the other specifies a contraindication.",
                observed_from_source=candidate_text[:160],
                model_interpretation="Therapeutic indication versus clinical contraindication represents opposing regulatory directives.",
            )

        if has_false_match:
            return DimensionEvaluation(
                dimension="meaning",
                status=DimensionStatus.MISMATCH,
                score=0.3,
                details="Meaning diverges due to conflicting core clinical subject (different drug, target population, or context).",
                observed_from_source=candidate_text[:160],
                model_interpretation="Conflicting core entities prevent regulatory directive equivalence.",
            )

        # Check shared regulatory dosage directives
        curr_is_dose = bool(curr_info.dose or curr_info.frequency or "take" in lower_curr or "administer" in lower_curr)
        cand_is_dose = bool(cand_info.dose or cand_info.frequency or "take" in lower_cand or "administer" in lower_cand)

        if curr_is_dose and cand_is_dose:
            # Check timing disparities (e.g. prior to vs following, bolus vs infusion)
            timing_diff = (
                ("prior to" in lower_curr and "following" in lower_cand)
                or ("following" in lower_curr and "prior to" in lower_cand)
                or ("rapid bolus" in lower_cand and "over" in lower_curr)
                or ("rapid bolus" in lower_curr and "over" in lower_cand)
            )
            dose_diff = bool(curr_info.dose and cand_info.dose and curr_info.dose.lower() != cand_info.dose.lower())

            if timing_diff or dose_diff:
                status = DimensionStatus.PARTIAL
                score = 0.7
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
            if jaccard > 0.4:
                status = DimensionStatus.MATCH
                score = 0.85
                details = "Passages share high semantic terminology and aligned regulatory meaning."
            else:
                status = DimensionStatus.PARTIAL
                score = 0.6
                details = "Passages share general regulatory terminology with varying specific directives."

        return DimensionEvaluation(
            dimension="meaning",
            status=status,
            score=score,
            details=details,
            observed_from_source=candidate_text[:160],
            model_interpretation="Directives convey regulatory content meaning.",
        )

    def _evaluate_template(self, curr_info: KeyInformation, cand_info: KeyInformation) -> DimensionEvaluation:
        """Evaluate pattern: [Population] + [Drug] + [Dose] + [Frequency] + [Route]."""
        curr_has_pattern = bool(curr_info.dose and (curr_info.frequency or curr_info.route or curr_info.population))
        cand_has_pattern = bool(cand_info.dose and (cand_info.frequency or cand_info.route or cand_info.population))

        if curr_has_pattern and cand_has_pattern:
            return DimensionEvaluation(
                dimension="template",
                status=DimensionStatus.MATCH,
                score=0.95,
                details="Both items follow the standard regulatory dosage instruction pattern: [Dose] + [Frequency] + [Administration Instructions].",
                observed_from_source=f"Pattern elements detected: dose={cand_info.dose}, frequency={cand_info.frequency}",
                model_interpretation="High template reusability: structure accommodates standard regulatory phrasing.",
            )
        elif curr_has_pattern or cand_has_pattern:
            return DimensionEvaluation(
                dimension="template",
                status=DimensionStatus.PARTIAL,
                score=0.6,
                details="Partial pattern match: one statement specifies dosage parameters while the other is narrative.",
                observed_from_source="Disparate template schema",
                model_interpretation="Template requires expansion to align with standard dosing schema.",
            )
        return DimensionEvaluation(
            dimension="template",
            status=DimensionStatus.MATCH,
            score=0.8,
            details="Both statements adhere to narrative regulatory prose patterns.",
            observed_from_source="Narrative format pattern",
            model_interpretation="Standard regulatory paragraph template observed.",
        )

    def _evaluate_context(
        self,
        current_text: str,
        candidate_text: str,
        curr_section: Optional[str],
        cand_section: Optional[str],
    ) -> DimensionEvaluation:
        """Differentiate operational setting: Prescribing recommendation vs Study adverse event."""
        lower_curr = current_text.lower()
        lower_cand = candidate_text.lower()

        # Detect clinical trial / study narrative
        is_study_current = bool(re.search(r"\b(clinical\s+trial|patients\s+received|study\s+\d+|in\s+trials?|experienced\s+nausea|adverse\s+events?|were\s+monitored)\b", lower_curr))
        is_study_candidate = bool(re.search(r"\b(clinical\s+trial|patients\s+received|study\s+\d+|in\s+trials?|experienced\s+nausea|adverse\s+events?|were\s+monitored)\b", lower_cand))

        if is_study_current != is_study_candidate:
            return DimensionEvaluation(
                dimension="context",
                status=DimensionStatus.MISMATCH,
                score=0.35,
                details="Context mismatch: one statement describes clinical study observations, whereas the other provides prescribing recommendations.",
                observed_from_source="Study observation phraseology detected in source",
                model_interpretation="Regulatory purpose differs: trial observation data cannot be directly reused as prescribing directive.",
            )

        # Detect Indication vs Contraindication operational context
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
            )

        return DimensionEvaluation(
            dimension="context",
            status=DimensionStatus.MATCH,
            score=0.9,
            details="Contexts align: both describe operational prescribing directives.",
            observed_from_source=f"Section: {cand_section or 'Standard Prescribing Information'}",
            model_interpretation="Aligned clinical intent and regulatory context.",
        )


    def _evaluate_structure(
        self,
        current_text: str,
        candidate_text: str,
        curr_section: Optional[str],
        cand_section: Optional[str],
    ) -> DimensionEvaluation:
        """Compare structural entity: section, subsection, paragraph, table, bullet."""
        curr_is_bullet = current_text.strip().startswith(("-", "•", "*")) or "\n-" in current_text
        cand_is_bullet = candidate_text.strip().startswith(("-", "•", "*")) or "\n-" in candidate_text
        curr_is_table = "|" in current_text or "\t" in current_text
        cand_is_table = "|" in candidate_text or "\t" in candidate_text

        if curr_is_table != cand_is_table:
            return DimensionEvaluation(
                dimension="structure",
                status=DimensionStatus.MISMATCH,
                score=0.4,
                details="Structural disparity: tabular content compared against non-tabular narrative content.",
                observed_from_source="Tabular matrix vs narrative structure",
                model_interpretation="Structure conversion required to incorporate candidate into document.",
            )

        if curr_is_bullet != cand_is_bullet:
            return DimensionEvaluation(
                dimension="structure",
                status=DimensionStatus.PARTIAL,
                score=0.7,
                details="Structural distinction: bulleted listing compared against narrative paragraph.",
                observed_from_source="Bullet list vs paragraph structure",
                model_interpretation="Minor structural adaptation required.",
            )

        return DimensionEvaluation(
            dimension="structure",
            status=DimensionStatus.MATCH,
            score=0.95,
            details="Structural equivalence: both occur as standard narrative paragraphs.",
            observed_from_source="Paragraph structure",
            model_interpretation="Direct structural interchangeability.",
        )

    def _evaluate_format(self, current_text: str, candidate_text: str) -> DimensionEvaluation:
        """Compare format: sentence, numerical specification, condensed field."""
        curr_has_nums = bool(re.search(r"\d+", current_text))
        cand_has_nums = bool(re.search(r"\d+", candidate_text))

        if curr_has_nums and cand_has_nums:
            return DimensionEvaluation(
                dimension="format",
                status=DimensionStatus.MATCH,
                score=0.9,
                details="Both statements format clinical directives with explicit numerical parameters.",
                observed_from_source="Numerical specification format",
                model_interpretation="Compatible clinical dosing format.",
            )
        elif curr_has_nums != cand_has_nums:
            return DimensionEvaluation(
                dimension="format",
                status=DimensionStatus.PARTIAL,
                score=0.65,
                details="Format distinction: one statement contains numerical specifications while the other is purely qualitative.",
                observed_from_source="Qualitative vs Quantitative format",
                model_interpretation="Reviewer adaptation required to format numbers consistently.",
            )
        return DimensionEvaluation(
            dimension="format",
            status=DimensionStatus.MATCH,
            score=0.85,
            details="Both statements utilize qualitative clinical prose format.",
            observed_from_source="Narrative prose format",
            model_interpretation="Format aligns.",
        )

    def _generate_overall_summary(
        self,
        meaning: DimensionEvaluation,
        template: DimensionEvaluation,
        key_info: DimensionEvaluation,
        false_match_warning: Optional[str],
    ) -> str:
        if false_match_warning:
            return f"FALSE MATCH ALERT: {false_match_warning}"
        if key_info.status == DimensionStatus.MATCH and meaning.status == DimensionStatus.MATCH:
            return "Strong Multi-Dimensional Alignment across meaning, template, and key parameters."
        if key_info.status == DimensionStatus.PARTIAL:
            return "Moderate Multi-Dimensional Alignment: shared regulatory template with specific attribute variations."
        return "Low Alignment: significant divergence in key parameters or regulatory context."

    def _assemble_evidence(
        self,
        candidate: RegulatoryContentItem,
        cand_info: KeyInformation,
        match: MultiDimensionalMatch,
        diffs: List[DifferenceItem],
        false_match_warning: Optional[str],
    ) -> StructuredEvidence:
        """Assemble two-tier structured evidence keeping observed facts strictly separate from interpretation."""
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
            loinc_code=candidate.loinc_code or candidate.metadata.get("loinc_code"),
            exact_quote=candidate.text[:300] + ("..." if len(candidate.text) > 300 else ""),
            extracted_drug=cand_info.drug,
            extracted_dose=cand_info.dose,
            extracted_population=cand_info.population,
            extracted_indication=cand_info.indication,
        )

        # Tier 2: Model / Algorithmic reasoning grounded in observed facts
        reasoning = ModelReasoning(
            similarity_rationale=match.meaning.details,
            difference_rationale="; ".join(d.explanation for d in diffs) if diffs else "No material parameter differences observed.",
            adaptation_guidance=(
                f"Candidate requires adaptation for: {', '.join(d.attribute for d in diffs)}."
                if diffs
                else "Candidate is suitable for direct review consideration."
            ),
            false_match_rationale=false_match_warning,
        )

        return StructuredEvidence(
            observed_from_source=observed,
            model_interpretation=reasoning,
        )
