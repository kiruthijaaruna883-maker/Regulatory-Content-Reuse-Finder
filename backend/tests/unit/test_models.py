"""Unit tests for Pydantic domain models."""

from app.models.comparison import ComparisonCandidate, DifferenceItem, EvidenceTrace
from app.models.content import RegulatoryContentItem, RegulatorySearchResult
from app.models.document_change import (
    ApprovedChangeReport,
    ChangeImpact,
    ProposedChange,
    ReviewDecisionType,
    ReviewerDecision,
    ValidationFinding,
)


def test_regulatory_content_item_metadata_preservation():
    """Verify RegulatoryContentItem preserves full metadata and defaults missing values to None."""
    item = RegulatoryContentItem(
        source="DailyMed",
        source_url="https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=test-set-id",
        source_identifier="test-set-id",
        document_name="Aspirin 81mg Tablet",
        version="4",
        date="2026-01-15",
        section="Dosage and Administration",
        text="Adults: Take 1 tablet every 4 hours.",
        drug="Aspirin",
        product="Bayer Aspirin",
        dose="81mg",
        route="Oral",
    )

    assert item.content_id.startswith("rc_")
    assert item.source == "DailyMed"
    assert item.source_identifier == "test-set-id"
    assert item.dose == "81mg"
    assert item.population is None
    assert item.indication is None
    assert "Take 1 tablet" in item.text


def test_regulatory_search_result():
    """Verify search result container encapsulates items and metadata."""
    item = RegulatoryContentItem(
        source="openFDA",
        text="Sample FDA label text.",
    )
    result = RegulatorySearchResult(
        query="ibuprofen",
        total_results=1,
        source="all",
        items=[item],
    )
    assert result.query == "ibuprofen"
    assert result.total_results == 1
    assert len(result.items) == 1
    assert result.retrieved_at is not None


def test_comparison_candidate_and_differences():
    """Verify ComparisonCandidate links to differences and source evidence."""
    item = RegulatoryContentItem(source="DailyMed", text="Candidate text.")
    diff = DifferenceItem(
        aspect="key_information",
        difference_type="modification",
        current_value="100mg",
        candidate_value="200mg",
        explanation="Dose disparity",
        regulatory_impact="MAJOR",
    )
    trace = EvidenceTrace(
        source="DailyMed",
        source_url="https://dailymed.nlm.nih.gov/test",
        exact_quote="Candidate text.",
    )
    candidate = ComparisonCandidate(
        content_item=item,
        similarity_score=0.85,
        differences=[diff],
        evidence=[trace],
    )

    assert candidate.similarity_score == 0.85
    assert len(candidate.differences) == 1
    assert candidate.differences[0].regulatory_impact == "MAJOR"
    assert len(candidate.evidence) == 1


def test_reviewer_decision_and_proposed_change():
    """Verify human reviewer decision states and change formulation."""
    decision = ReviewerDecision(
        target_content_id="rc_target_123",
        candidate_id="cand_456",
        decision=ReviewDecisionType.ADAPT,
        reviewer_name="Dr. Jane Regulatory",
        reviewer_notes="Adjust dose frequency for pediatric subgroup",
        adaptation_instructions="Use once daily instead of twice daily",
    )
    assert decision.decision == ReviewDecisionType.ADAPT
    assert decision.reviewer_name == "Dr. Jane Regulatory"

    proposal = ProposedChange(
        decision_id=decision.decision_id,
        section="Dosage and Administration",
        original_text="Take twice daily",
        proposed_text="Take once daily for pediatric subgroup",
        decision_type=decision.decision,
        rationale="Adapted per clinical justification",
    )
    assert proposal.decision_id == decision.decision_id
    assert proposal.decision_type == ReviewDecisionType.ADAPT
