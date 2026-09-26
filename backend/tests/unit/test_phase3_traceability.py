"""Unit tests for Phase 3 Step 4: Complete Evidence / Target Traceability.

Validates that:
1. WHAT matched and WHY it matched remain traceable across all 6 dimensions.
2. Target provenance (content ID, document ID, document name, section, subsection, location, page) is preserved.
3. Candidate provenance (content ID, document ID, text, etc.) is preserved.
4. Source provenance (source, URL, identifier) is preserved.
5. Document identity (name, ID, version) is traceable.
6. Section/subsection hierarchy is preserved.
7. Page/location traceability is maintained.
8. Structure path traceability is preserved.
9. Verbatim original text integrity is preserved.
10. Contributing comparison dimensions are identifiable.
11. Difference origin (source_dimension) is populated for all differences.
12. Strict two-tier separation: ObservedSourceFacts / TargetSourceFacts vs ModelReasoning.
13. Cross-source corroboration (cross_sources, duplicate_provenance) survives evidence assembly.
14. No-fabrication rule: missing metadata defaults to None, never invented.
15. Backward compatibility: minimal comparison payloads and legacy EvidenceTrace work.
16. Frontend-consumed fields remain available.
17. Human review decision contracts (REUSE / ADAPT / REJECT) remain strictly intact.
"""

import pytest
from app.agents.content_analysis_agent import RegulatoryContentAnalysisAgent
from app.models.comparison import (
    ComparisonCandidate,
    ContentComparisonResult,
    DifferenceItem,
    DimensionEvaluation,
    DimensionStatus,
    EvidenceTrace,
    ModelReasoning,
    MultiDimensionalMatch,
    ObservedSourceFacts,
    StructuredEvidence,
    TargetSourceFacts,
)
from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document_change import ReviewDecisionType, ReviewerDecision
from app.services.multi_dimensional_comparator import MultiDimensionalComparator


@pytest.fixture
def comparator() -> MultiDimensionalComparator:
    return MultiDimensionalComparator()


@pytest.fixture
def agent() -> RegulatoryContentAnalysisAgent:
    return RegulatoryContentAnalysisAgent()


# ---------------------------------------------------------------------------
# Test 1: What matched and why (six-dimensional traceability)
# ---------------------------------------------------------------------------
def test_what_matched_and_why_dimension_breakdown(comparator: MultiDimensionalComparator):
    """Verify that match result and dimensional rationale explain WHAT matched and WHY."""
    target_text = "Adults: Take 500 mg orally once daily with meals."
    candidate = RegulatoryContentItem(
        content_id="rc_cand_001",
        document_name="Aspirin Tablet Label",
        source="DailyMed",
        section="Dosage and Administration",
        text="Adults: Take 500 mg PO QD with food.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target_text,
        candidate=candidate,
        target_section="Dosage and Administration",
    )

    assert isinstance(match, MultiDimensionalMatch)
    # Check all 6 dimensions have details explaining why they matched or varied
    assert match.meaning.dimension == "meaning"
    assert match.meaning.details != ""
    assert match.key_information.dimension == "key_information"
    assert match.key_information.details != ""
    assert match.template.dimension == "template"
    assert match.template.details != ""
    assert match.context.dimension == "context"
    assert match.context.details != ""
    assert match.structure.dimension == "structure"
    assert match.structure.details != ""
    assert match.format.dimension == "format"
    assert match.format.details != ""
    assert match.overall_alignment_summary != ""


# ---------------------------------------------------------------------------
# Test 2: Target provenance preservation
# ---------------------------------------------------------------------------
def test_target_provenance_preservation(comparator: MultiDimensionalComparator):
    """Verify target content ID, document ID, document name, section, subsection, location, page."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_002",
        source="DailyMed",
        text="Take 10 mg orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Take 10 mg orally once daily.",
        candidate=candidate,
        target_content_id="target_chk_123",
        target_document_id="doc_internal_456",
        target_document_name="Internal Cardiovascular Draft",
        target_section="Dosage and Administration",
        target_subsection="2.1 General Dosing",
        target_location="Section 2, Paragraph 1",
        target_page=12,
        target_content_type="paragraph",
    )

    assert evidence.target_facts is not None
    tf = evidence.target_facts
    assert tf.target_content_id == "target_chk_123"
    assert tf.target_document_id == "doc_internal_456"
    assert tf.target_document_name == "Internal Cardiovascular Draft"
    assert tf.target_section == "Dosage and Administration"
    assert tf.target_subsection == "2.1 General Dosing"
    assert tf.target_location == "Section 2, Paragraph 1"
    assert tf.target_page == 12
    assert tf.target_content_type == "paragraph"


# ---------------------------------------------------------------------------
# Test 3: Candidate provenance preservation
# ---------------------------------------------------------------------------
def test_candidate_provenance_preservation(comparator: MultiDimensionalComparator):
    """Verify candidate content ID, document ID, and original text are preserved."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_003",
        document_id="doc_ext_789",
        document_name="Lipitor Prescribing Information",
        source="DailyMed",
        text="Adults: 10 mg to 80 mg orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Adults: 20 mg orally once daily.",
        candidate=candidate,
    )

    observed = evidence.observed_from_source
    assert observed.content_id == "rc_cand_003"
    assert observed.document_id == "doc_ext_789"
    assert observed.document_name == "Lipitor Prescribing Information"
    assert observed.exact_quote == "Adults: 10 mg to 80 mg orally once daily."


# ---------------------------------------------------------------------------
# Test 4: Source provenance (source, URL, identifier)
# ---------------------------------------------------------------------------
def test_source_and_url_provenance(comparator: MultiDimensionalComparator):
    """Verify source, source URL, and source identifier are accurately captured."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_004",
        source="DailyMed",
        source_url="https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=abc-123",
        source_identifier="set-abc-123-spl",
        text="Initial dose: 50 mg orally twice daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Initial dose: 50 mg orally twice daily.",
        candidate=candidate,
    )

    observed = evidence.observed_from_source
    assert observed.source == "DailyMed"
    assert observed.source_url == "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=abc-123"
    assert observed.source_identifier == "set-abc-123-spl"


# ---------------------------------------------------------------------------
# Test 5: Document identity (name, ID, version, date)
# ---------------------------------------------------------------------------
def test_document_identity_traceability(comparator: MultiDimensionalComparator):
    """Verify document name, ID, version, and publication date are preserved."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_005",
        document_id="doc_spl_999",
        document_name="Metformin Hydrochloride Tablets",
        version="4.2",
        date="2025-11-15",
        source="openFDA",
        text="Starting dose of Metformin is 500 mg orally twice daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Starting dose is 500 mg orally twice daily.",
        candidate=candidate,
    )

    observed = evidence.observed_from_source
    assert observed.document_name == "Metformin Hydrochloride Tablets"
    assert observed.document_id == "doc_spl_999"
    assert observed.version == "4.2"
    assert observed.date == "2025-11-15"


# ---------------------------------------------------------------------------
# Test 6: Section and subsection hierarchy
# ---------------------------------------------------------------------------
def test_section_and_subsection_hierarchy(comparator: MultiDimensionalComparator):
    """Verify section heading, subsection outline number, and LOINC code."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_006",
        source="DailyMed",
        section="Dosage and Administration",
        subsection="2.2 Recommended Dosage for Adult Patients",
        loinc_code="34068-7",
        text="Recommended dose is 100 mg once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Recommended dose is 100 mg once daily.",
        candidate=candidate,
    )

    observed = evidence.observed_from_source
    assert observed.section == "Dosage and Administration"
    assert observed.subsection == "2.2 Recommended Dosage for Adult Patients"
    assert observed.loinc_code == "34068-7"


# ---------------------------------------------------------------------------
# Test 7: Page and physical location traceability
# ---------------------------------------------------------------------------
def test_page_and_location_traceability(comparator: MultiDimensionalComparator):
    """Verify physical location and page number are preserved without fabrication."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_007",
        source="InternalDraft",
        location="Table 3, Row 2",
        page=18,
        text="Severe Renal Impairment (CrCl < 30 mL/min): 25 mg once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Severe Renal Impairment: 25 mg once daily.",
        candidate=candidate,
    )

    observed = evidence.observed_from_source
    assert observed.location == "Table 3, Row 2"
    assert observed.page == 18


# ---------------------------------------------------------------------------
# Test 8: Structure path traceability
# ---------------------------------------------------------------------------
def test_structure_path_traceability(comparator: MultiDimensionalComparator):
    """Verify full hierarchical structure breadcrumbs (Document > Section > Subsection > Table > Row)."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_008",
        source="InternalDraft",
        content_type="table_row",
        metadata={
            "structure_path": "Core Data Sheet > 4.2 Posology > Special Populations > Table 1 > Row 4",
        },
        text="Hemodialysis patients: 10 mg post-dialysis.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Hemodialysis patients: 10 mg post-dialysis.",
        candidate=candidate,
    )

    observed = evidence.observed_from_source
    assert observed.content_type == "table_row"
    assert observed.structure_path == "Core Data Sheet > 4.2 Posology > Special Populations > Table 1 > Row 4"


# ---------------------------------------------------------------------------
# Test 9: Verbatim original text preservation
# ---------------------------------------------------------------------------
def test_verbatim_original_text_preservation(comparator: MultiDimensionalComparator):
    """Verify that verbatim candidate text is preserved in exact_quote without mutation."""
    long_regulatory_text = (
        "In clinical controlled trials involving adult patients with major depressive disorder, "
        "the recommended starting dose is 20 mg administered orally once daily in the morning. "
        "A dose increase may be considered after a minimum interval of two weeks up to a maximum "
        "authorized dose of 50 mg daily, depending on clinical response and tolerability."
    )
    candidate = RegulatoryContentItem(
        content_id="rc_cand_009",
        source="DailyMed",
        text=long_regulatory_text,
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=long_regulatory_text,
        candidate=candidate,
    )

    observed = evidence.observed_from_source
    assert observed.exact_quote == long_regulatory_text


# ---------------------------------------------------------------------------
# Test 10: Contributing comparison dimensions
# ---------------------------------------------------------------------------
def test_contributing_comparison_dimensions(comparator: MultiDimensionalComparator):
    """Verify that all six dimensions contribute distinct evaluations and scores."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_010",
        source="DailyMed",
        text="Adults: 20 mg PO QD.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Take the medicine as directed.",
        candidate=candidate,
    )

    dimensions = [
        match.meaning,
        match.template,
        match.context,
        match.structure,
        match.format,
        match.key_information,
    ]
    for dim in dimensions:
        assert isinstance(dim, DimensionEvaluation)
        assert dim.dimension in {"meaning", "template", "context", "structure", "format", "key_information"}
        assert dim.status in {DimensionStatus.MATCH, DimensionStatus.PARTIAL, DimensionStatus.MISMATCH}


# ---------------------------------------------------------------------------
# Test 11: Difference origin and source_dimension traceability
# ---------------------------------------------------------------------------
def test_difference_origin_source_dimension(comparator: MultiDimensionalComparator):
    """Verify each generated DifferenceItem is tagged with its originating comparison dimension."""
    # Dose mismatch -> key_information
    # Quantitative vs qualitative -> format
    # Mandatory vs advisory -> meaning
    target_text = "Adults: Patients must take 20 mg orally once daily with food."
    candidate_text = "Adults: Patients may take 40 mg orally once daily on an empty stomach."

    candidate = RegulatoryContentItem(
        content_id="rc_cand_011",
        source="DailyMed",
        text=candidate_text,
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target_text,
        candidate=candidate,
    )

    assert len(diffs) > 0
    dimensions_found = set()
    for d in diffs:
        assert d.source_dimension is not None
        assert d.source_dimension in {"meaning", "template", "context", "structure", "format", "key_information"}
        dimensions_found.add(d.source_dimension)

    # Must contain at least key_information (dose 20 vs 40) and meaning (must vs may, with food vs empty stomach)
    assert "key_information" in dimensions_found
    assert "meaning" in dimensions_found


# ---------------------------------------------------------------------------
# Test 12: Strict two-tier evidence separation
# ---------------------------------------------------------------------------
def test_two_tier_evidence_separation(comparator: MultiDimensionalComparator):
    """Verify Tier 1 observed facts are strictly separated from Tier 2 model reasoning."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_012",
        source="DailyMed",
        document_name="FDA Reference Standard",
        text="Adults: Take 100 mg orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Adults: Take 200 mg orally once daily.",
        candidate=candidate,
    )

    assert isinstance(evidence, StructuredEvidence)
    observed = evidence.observed_from_source
    reasoning = evidence.model_interpretation

    # Observed facts must be concrete factual records from candidate
    assert observed.source == "DailyMed"
    assert observed.document_name == "FDA Reference Standard"
    assert "100 mg" in observed.exact_quote

    # Model reasoning must be analytical interpretations
    assert isinstance(reasoning, ModelReasoning)
    assert reasoning.similarity_rationale != ""
    assert reasoning.difference_rationale != ""
    assert "dose" in reasoning.adaptation_guidance.lower()


# ---------------------------------------------------------------------------
# Test 13: Cross-source corroboration traceability
# ---------------------------------------------------------------------------
def test_cross_source_corroboration_traceability(comparator: MultiDimensionalComparator):
    """Verify that cross_sources and duplicate_provenance from Step 2 survive evidence assembly."""
    dup_prov = [
        {
            "content_id": "rc_dup_openfda",
            "source": "openFDA",
            "document_name": "Atorvastatin NDA 020702",
            "source_identifier": "NDA020702",
            "section": "DOSAGE AND ADMINISTRATION",
        }
    ]
    candidate = RegulatoryContentItem(
        content_id="rc_primary_dailymed",
        source="DailyMed",
        source_identifier="set-12345",
        document_name="Lipitor Label",
        metadata={
            "cross_sources": ["DailyMed", "openFDA"],
            "duplicate_provenance": dup_prov,
        },
        text="Initial recommended dose: 10 to 20 mg once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Initial dose: 10 to 20 mg once daily.",
        candidate=candidate,
    )

    observed = evidence.observed_from_source
    assert observed.cross_sources == ["DailyMed", "openFDA"]
    assert observed.duplicate_provenance is not None
    assert len(observed.duplicate_provenance) == 1
    assert observed.duplicate_provenance[0]["source"] == "openFDA"
    assert observed.duplicate_provenance[0]["source_identifier"] == "NDA020702"


# ---------------------------------------------------------------------------
# Test 14: No-fabrication rule (unavailable metadata remains None)
# ---------------------------------------------------------------------------
def test_no_fabrication_rule(comparator: MultiDimensionalComparator):
    """Verify that fields not provided by source default to None, never invented."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_minimal",
        source="DailyMed",
        text="Adults: 50 mg orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Adults: 50 mg orally once daily.",
        candidate=candidate,
    )

    observed = evidence.observed_from_source
    # Verify unsupplied fields are None rather than fabricated
    assert observed.source_url is None
    assert observed.source_identifier is None
    assert observed.document_id is None
    assert observed.page is None
    assert observed.subsection is None
    assert observed.structure_path is None


# ---------------------------------------------------------------------------
# Test 15: Backward compatibility of minimal calls and legacy EvidenceTrace
# ---------------------------------------------------------------------------
def test_backward_compatibility_minimal_calls(comparator: MultiDimensionalComparator):
    """Verify comparator.compare works with minimal arguments and legacy EvidenceTrace is valid."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_legacy",
        source="DailyMed",
        text="Adults: Take 1 tablet daily.",
    )

    # Minimal call with only 2 arguments
    match, diffs, evidence, false_warning = comparator.compare(
        target_text="Adults: Take 1 tablet daily.",
        candidate=candidate,
    )
    assert match.meaning.status == DimensionStatus.MATCH
    assert evidence.observed_from_source.source == "DailyMed"

    # Legacy EvidenceTrace compatibility
    legacy_trace = EvidenceTrace(
        source="DailyMed",
        source_url="https://dailymed.nlm.nih.gov",
        exact_quote="Adults: Take 1 tablet daily.",
    )
    comp_cand = ComparisonCandidate(
        content_item=candidate,
        evidence=[legacy_trace],
    )
    assert len(comp_cand.evidence) == 1
    assert comp_cand.evidence[0].source == "DailyMed"


# ---------------------------------------------------------------------------
# Test 16: Agent 1 End-to-End target provenance forwarding
# ---------------------------------------------------------------------------
def test_agent_target_provenance_forwarding(agent: RegulatoryContentAnalysisAgent):
    """Verify that ContentComparisonResult captures target provenance fields through agent."""
    candidate = RegulatoryContentItem(
        content_id="rc_cand_agent",
        source="DailyMed",
        text="Adults: Take 20 mg orally once daily.",
    )

    result: ContentComparisonResult = agent.analyze_and_compare(
        target_text="Adults: Take 20 mg orally once daily.",
        candidates=[candidate],
        section_name="Dosage and Administration",
        target_content_id="target_sec_001",
        target_document_id="doc_internal_001",
        target_document_name="Internal Label Draft v1.0",
        target_subsection="2.1 Adult Dosage",
        target_location="Paragraph 1",
        target_page=5,
        target_content_type="paragraph",
    )

    assert isinstance(result, ContentComparisonResult)
    assert result.target_content_id == "target_sec_001"
    assert result.target_document_id == "doc_internal_001"
    assert result.target_document_name == "Internal Label Draft v1.0"
    assert result.target_section == "Dosage and Administration"
    assert result.target_subsection == "2.1 Adult Dosage"
    assert result.target_location == "Paragraph 1"
    assert result.target_page == 5
    assert result.target_content_type == "paragraph"

    # Candidate evidence also preserves target facts
    cand = result.candidates[0]
    assert len(cand.evidence) > 0
    ev = cand.evidence[0]
    assert isinstance(ev, StructuredEvidence)
    assert ev.target_facts is not None
    assert ev.target_facts.target_content_id == "target_sec_001"
    assert ev.target_facts.target_document_name == "Internal Label Draft v1.0"


# ---------------------------------------------------------------------------
# Test 17: Human Review Decision contracts preserved (REUSE, ADAPT, REJECT)
# ---------------------------------------------------------------------------
def test_human_review_decision_contracts_preserved():
    """Verify that human review decision workflow remains REUSE, ADAPT, REJECT."""
    assert set(ReviewDecisionType) == {
        ReviewDecisionType.REUSE,
        ReviewDecisionType.ADAPT,
        ReviewDecisionType.REJECT,
    }

    decision = ReviewerDecision(
        target_content_id="target_sec_001",
        candidate_id="cand_rc_001",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Lead Regulatory Affairs",
        reviewer_notes="Direct reuse approved against FDA DailyMed standard.",
    )
    assert decision.decision == ReviewDecisionType.REUSE
    assert decision.reviewer_name == "Dr. Lead Regulatory Affairs"
