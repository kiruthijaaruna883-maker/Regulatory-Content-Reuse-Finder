"""Comprehensive unit tests for Phase 3 Step 3: Deepened Regulatory Comparison & Difference Detection.

Validates the six regulatory comparison dimensions:
1. Meaning (modality shifts, administration condition conflicts, mechanical prohibitions)
2. Template (regulatory-aware slot evaluation: Posology, Indication, Contraindication)
3. Context (specialized population contexts, canonical section concepts, trial vs prescribing)
4. Structure (table rows, numbered/stepwise instructions, bullet lists, paragraphs)
5. Format (quantitative vs qualitative, fixed vs range, clinical shorthand vs narrative)
6. Key Information (duration, dose_unit, indication, age_group, canonical route/frequency)
7. DifferenceDetectionService extensions (duration, dose_unit, indication, modality, condition)
8. Evidence and source facts traceability preservation
9. Full backward compatibility
"""

import pytest
from app.models.comparison import (
    DifferenceItem,
    DimensionEvaluation,
    DimensionStatus,
    MultiDimensionalMatch,
    StructuredEvidence,
)
from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document import CanonicalSectionConcept, RegulatoryChunk
from app.services.difference_detection import DifferenceDetectionService
from app.services.multi_dimensional_comparator import MultiDimensionalComparator


# ==============================================================================
# 1. KEY INFORMATION & CANONICAL NORMALIZATION TESTS
# ==============================================================================


def test_dose_unit_mismatch_triggers_false_match():
    """1. Verify dose-unit mismatch (50 mg vs 50 mcg) triggers false-match alert and MISMATCH status."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Take 50 mg of losartan orally once daily."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        document_name="Losartan Potassium Tablets",
        section="Dosage and Administration",
        text="Adults: Take 50 mcg of losartan orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match is not None
    assert false_warning is not None
    assert "Dose unit mismatch" in false_warning
    assert match.key_information.status == DimensionStatus.MISMATCH
    assert any(d.attribute == "dose_unit" for d in diffs)
    unit_diff = next(d for d in diffs if d.attribute == "dose_unit")
    assert unit_diff.current_value == "mg"
    assert unit_diff.candidate_value == "mcg"
    assert unit_diff.reviewer_attention_required is True


def test_duration_difference_detected():
    """2. Verify treatment duration disparity (7 days vs 14 days) is extracted and reported."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Take 500 mg orally every 8 hours for 7 days."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Adults: Take 500 mg orally every 8 hours for 14 days.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert any(d.attribute == "duration" for d in diffs)
    dur_diff = next(d for d in diffs if d.attribute == "duration")
    assert "7 days" in dur_diff.current_value
    assert "14 days" in dur_diff.candidate_value
    assert match.key_information.status == DimensionStatus.PARTIAL


def test_route_canonical_normalization():
    """3. Verify canonical route normalization: PO vs oral does not produce a false difference."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Take 10 mg PO once daily."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Adults: Take 10 mg orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    # Route disparity must NOT be flagged because PO and orally both normalize to Oral
    assert not any(d.attribute == "route" for d in diffs)
    assert match.key_information.status == DimensionStatus.MATCH


def test_frequency_canonical_normalization():
    """4. Verify canonical frequency normalization: QD vs once daily does not produce a false difference."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Take 25 mg orally QD."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Adults: Take 25 mg orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    # Frequency disparity must NOT be flagged because QD and once daily both normalize to once daily
    assert not any(d.attribute == "frequency" for d in diffs)
    assert match.key_information.status == DimensionStatus.MATCH


# ==============================================================================
# 2. MEANING & REGULATORY MODALITY / CONDITION CONFLICT TESTS
# ==============================================================================


def test_modality_shift_mandatory_vs_permissive():
    """5. Verify regulatory modality shift (must take vs may take) is flagged as a distinction."""
    comparator = MultiDimensionalComparator()
    target = "Patients must take with a full glass of water. Compliance is strictly required."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Patients may take with a full glass of water. Compliance is recommended.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.meaning.status == DimensionStatus.PARTIAL
    assert "modality shift" in match.meaning.details.lower()
    assert any(d.attribute == "modality" for d in diffs)


def test_administration_condition_conflict_food():
    """6. Verify administration condition conflict (with meals vs on an empty stomach) triggers MISMATCH."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Take 200 mg orally once daily with meals."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Adults: Take 200 mg orally once daily on an empty stomach without food.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.meaning.status == DimensionStatus.MISMATCH
    assert "administration condition conflict" in match.meaning.details.lower()
    assert any(d.attribute == "administration_condition" for d in diffs)
    cond_diff = next(d for d in diffs if d.attribute == "administration_condition")
    assert "meals" in cond_diff.current_value.lower()
    assert "empty stomach" in cond_diff.candidate_value.lower()


def test_prohibition_conflict_crushing():
    """7. Verify prohibition conflict (do not crush vs may be crushed) triggers MISMATCH."""
    comparator = MultiDimensionalComparator()
    target = "Tablets must be swallowed whole; do not crush or chew."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Tablets may be crushed and mixed with applesauce for administration.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.meaning.status == DimensionStatus.MISMATCH
    assert "prohibition conflict" in match.meaning.details.lower()
    assert any(d.attribute == "administration_condition" for d in diffs)


# ==============================================================================
# 3. TEMPLATE SLOT CONFORMANCE TESTS
# ==============================================================================


def test_posology_template_slot_alignment():
    """8. Verify Posology template slots (Population, Initial Dose, Frequency, Max Dose, Route) align."""
    comparator = MultiDimensionalComparator()
    target = "Adults: The recommended starting dose is 25 mg orally once daily. Titrate every 2 weeks to a maximum dose of 100 mg."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Adults: Starting dosage is 25 mg orally once daily. Increase every 2 weeks to a maximum dose of 100 mg.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.template.status == DimensionStatus.MATCH
    assert "POSOLOGY" in match.template.details
    assert "Matched slots" in match.template.details
    assert match.template.score >= 0.90


def test_indication_template_recognition():
    """9. Verify Indication template slot structure is recognized and evaluated."""
    comparator = MultiDimensionalComparator()
    target = "Cardivex is indicated for the treatment of hypertension in adults as monotherapy."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Cardivex is indicated for the treatment of essential hypertension in adult patients.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.template.status in {DimensionStatus.MATCH, DimensionStatus.PARTIAL}
    assert "INDICATION" in match.template.details


def test_contraindication_template_recognition():
    """10. Verify Contraindication template slot structure is recognized and evaluated."""
    comparator = MultiDimensionalComparator()
    target = "Cardivex is contraindicated in patients with severe hepatic impairment."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Cardivex is contraindicated in patients with severe hepatic impairment.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.template.status == DimensionStatus.MATCH
    assert "CONTRAINDICATION" in match.template.details


# ==============================================================================
# 4. CONTEXT & SPECIAL POPULATION / SECTION CONCEPT TESTS
# ==============================================================================


def test_special_population_context_disparity():
    """11. Verify specialized population context disparity (general adult vs renal impairment) triggers MISMATCH."""
    comparator = MultiDimensionalComparator()
    target = "Adults: The recommended starting dose is 50 mg orally once daily."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="In patients with severe renal impairment (CrCl < 30 mL/min), the starting dose is 25 mg orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.context.status == DimensionStatus.MISMATCH
    assert "specialized population context disparity" in match.context.details.lower()
    assert any(d.attribute == "context" for d in diffs)


def test_cross_section_context_disparity():
    """12. Verify cross-section context disparity (Dosage vs Adverse Reactions or Overdosage) triggers MISMATCH."""
    comparator = MultiDimensionalComparator()
    target = "Take 10 mg orally once daily."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        section="Overdosage",
        text="In acute overdosage, gastric lavage and forced emesis are recommended.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
        target_section="Dosage and Administration",
    )

    assert match.context.status == DimensionStatus.MISMATCH
    assert "regulatory section context disparity" in match.context.details.lower()
    assert any(d.attribute == "context" for d in diffs)


# ==============================================================================
# 5. STRUCTURE DIMENSION TESTS
# ==============================================================================


def test_chunk_type_structure_differences():
    """13. Verify structural disparity between tabular data and narrative prose is detected."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Take 10 mg orally once daily."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        content_type="table_row",
        text="| Creatinine Clearance | Recommended Dose |\n| < 30 mL/min | 10 mg once daily |",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.structure.status == DimensionStatus.MISMATCH
    assert "tabular" in match.structure.details.lower()
    assert any(d.attribute == "structure" for d in diffs)


def test_numbered_stepwise_structure():
    """14. Verify sequential numbered/stepwise procedural structure is distinguished from flat prose."""
    comparator = MultiDimensionalComparator()
    target = "Step 1: Administer initial dose of 10 mg.\nStep 2: Titrate to 20 mg after 4 weeks."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Adults take 10 mg initially, followed by 20 mg maintenance.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.structure.status == DimensionStatus.PARTIAL
    assert "stepwise" in match.structure.details.lower()


# ==============================================================================
# 6. FORMAT DIMENSION TESTS
# ==============================================================================


def test_quantitative_vs_qualitative_format():
    """15. Verify quantitative dosing specification is distinguished from qualitative guidance."""
    comparator = MultiDimensionalComparator()
    target = "Take 20 mg orally once daily."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Take the medication orally as directed by your physician.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.format.status == DimensionStatus.PARTIAL
    assert "qualitative" in match.format.details.lower()
    assert any(d.attribute == "format" for d in diffs)


def test_fixed_dose_vs_dose_range_format():
    """16. Verify fixed dose (20 mg) is distinguished from titrated dose range (10 to 20 mg)."""
    comparator = MultiDimensionalComparator()
    target = "The recommended dose is 20 mg orally once daily."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="The recommended dose is 10 to 20 mg orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.format.status == DimensionStatus.PARTIAL
    assert "range" in match.format.details.lower()


def test_abbreviation_vs_narrative_format():
    """17. Verify clinical prescription shorthand (50 mg PO BID) is distinguished from narrative prose."""
    comparator = MultiDimensionalComparator()
    target = "50 mg PO BID"
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Take 50 mg by mouth twice daily with a full glass of water.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert match.format.status == DimensionStatus.PARTIAL
    assert "shorthand" in match.format.details.lower()


# ==============================================================================
# 7. EXTENDED DIFFERENCE DETECTION SERVICE TESTS
# ==============================================================================


def test_extended_difference_detection_service_attributes():
    """18. Verify DifferenceDetectionService detects duration, unit, indication, modality, and conditions."""
    differ = DifferenceDetectionService()

    # A. Dose unit difference (50 mg vs 50 mcg)
    diffs_unit = differ.analyze_differences(
        "Adults: Take 50 mg orally once daily.",
        "Adults: Take 50 mcg orally once daily.",
    )
    assert any(d.attribute == "dose_unit" for d in diffs_unit)

    # B. Duration difference (7 days vs 14 days)
    diffs_dur = differ.analyze_differences(
        "Adults: Take 500 mg for 7 days.",
        "Adults: Take 500 mg for 14 days.",
    )
    assert any(d.attribute == "duration" for d in diffs_dur)

    # C. Modality shift (must vs may)
    diffs_mod = differ.analyze_differences(
        "Patients must take with water.",
        "Patients may take with water.",
    )
    assert any(d.attribute == "modality" for d in diffs_mod)

    # D. Condition conflict (with meals vs on an empty stomach)
    diffs_cond = differ.analyze_differences(
        "Take 10 mg with meals.",
        "Take 10 mg on an empty stomach.",
    )
    assert any(d.attribute == "administration_condition" for d in diffs_cond)

    # E. Route canonical normalization (PO vs Oral -> NO difference)
    diffs_route = differ.analyze_differences(
        "Take 10 mg PO once daily.",
        "Take 10 mg orally once daily.",
    )
    assert not any(d.attribute == "route" for d in diffs_route)

    # F. Frequency canonical normalization (QD vs once daily -> NO difference)
    diffs_freq = differ.analyze_differences(
        "Take 10 mg orally QD.",
        "Take 10 mg orally once daily.",
    )
    assert not any(d.attribute == "frequency" for d in diffs_freq)


# ==============================================================================
# 8. EVIDENCE TRACEABILITY PRESERVATION TESTS
# ==============================================================================


def test_evidence_traceability_preservation():
    """19. Verify two-tier evidence structure preserves authoritative source facts and model reasoning."""
    comparator = MultiDimensionalComparator()
    candidate = RegulatoryContentItem(
        source="DailyMed",
        source_url="https://dailymed.nlm.nih.gov/test-set-id",
        source_identifier="set-xyz-987",
        document_name="Aspirin 81 mg Delayed Release",
        version="3.0",
        date="2026-02-15",
        section="Dosage and Administration",
        location="Section 2, Paragraph 1",
        loinc_code="34068-7",
        text="Adults: Take 81 mg orally once daily with food.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Adults: Take 81 mg orally once daily with food.",
        candidate=candidate,
    )

    assert isinstance(evidence, StructuredEvidence)
    observed = evidence.observed_from_source
    reasoning = evidence.model_interpretation

    # Observed facts must be strictly populated from source
    assert observed.source == "DailyMed"
    assert observed.source_url == "https://dailymed.nlm.nih.gov/test-set-id"
    assert observed.source_identifier == "set-xyz-987"
    assert observed.document_name == "Aspirin 81 mg Delayed Release"
    assert observed.version == "3.0"
    assert observed.date == "2026-02-15"
    assert observed.section == "Dosage and Administration"
    assert observed.location == "Section 2, Paragraph 1"
    assert observed.loinc_code == "34068-7"
    assert "81 mg" in observed.exact_quote
    assert observed.extracted_dose == "81 mg"
    assert observed.extracted_population == "Adults"

    # Model reasoning must be grounded in observed facts
    assert reasoning.similarity_rationale is not None
    assert reasoning.difference_rationale is not None
    assert reasoning.adaptation_guidance is not None


# ==============================================================================
# 9. BACKWARD COMPATIBILITY WITH REGULATORY CHUNK TESTS
# ==============================================================================


def test_backward_compatibility_regulatory_chunk_candidate():
    """20. Verify comparator seamlessly accepts a RegulatoryChunk candidate without regression."""
    comparator = MultiDimensionalComparator()
    target_text = "Adults: The recommended starting dose is 10 mg orally once daily."

    candidate_chunk = RegulatoryChunk(
        chunk_id="chk_deep_comp_01",
        document_id="doc_chk_01",
        section_id="sec_posology",
        document_name="Ramipril Oral Tablets",
        section_title="Dosage and Administration",
        content="Adults: The recommended starting dose is 10 mg orally once daily.",
        source="DailyMed",
        key_information=KeyInformation(
            dose="10 mg",
            frequency="once daily",
            route="Oral",
            population="Adults",
        ),
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target_text,
        candidate=candidate_chunk,
    )

    assert match is not None
    assert match.meaning.status == DimensionStatus.MATCH
    assert match.key_information.status == DimensionStatus.MATCH
    assert evidence.observed_from_source.source == "DailyMed"
    assert evidence.observed_from_source.document_name == "Ramipril Oral Tablets"
    assert evidence.observed_from_source.extracted_dose == "10 mg"
    assert false_warning is None
