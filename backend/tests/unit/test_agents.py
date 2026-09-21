"""Unit tests for Agent 1 and Agent 2 architectural foundations."""

from app.agents.content_analysis_agent import RegulatoryContentAnalysisAgent
from app.agents.document_change_agent import RegulatoryDocumentChangeAgent
from app.models.content import RegulatoryContentItem
from app.models.document_change import ReviewDecisionType, ReviewerDecision


def test_agent_1_content_classification_and_comparison():
    """Verify Agent 1 classifies sections and compares candidates without making autonomous approval decisions."""
    agent = RegulatoryContentAnalysisAgent()

    # Classification
    assert agent.classify_regulatory_section("Take 2 tablets every 4 hours") == "Dosage and Administration"
    assert agent.classify_regulatory_section("Indicated for relief of pain") == "Indications and Usage"
    assert agent.classify_regulatory_section("Do not use if allergic") == "Contraindications"

    # Comparison
    target_text = "Take 2 tablets with water every 4 hours."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Adults: 2 tablets every 4 hours with water. Maximum 8 tablets daily.",
    )
    result = agent.analyze_and_compare(target_text=target_text, candidates=[candidate])

    assert result.target_text == target_text
    assert len(result.candidates) == 1
    assert result.candidates[0].similarity_score is not None
    assert len(result.candidates[0].evidence) == 1


def test_agent_2_controlled_change_proposal_and_occurrences():
    """Verify Agent 2 converts human decisions into proposals and tracks occurrences without autonomous approval."""
    agent = RegulatoryDocumentChangeAgent()

    decision = ReviewerDecision(
        target_content_id="rc_target_1",
        decision=ReviewDecisionType.ADAPT,
        reviewer_name="Regulatory Lead",
        adaptation_instructions="Add food intake cautionary notice",
    )

    proposal = agent.formulate_change_proposal(
        decision=decision,
        section="Dosage and Administration",
        original_text="Take 1 tablet daily.",
        candidate_text="Take 1 tablet daily with meals.",
    )

    assert proposal.decision_type == ReviewDecisionType.ADAPT
    assert "food intake" in proposal.proposed_text

    # Occurrence tracking across document sections
    document_sections = [
        {"document_name": "Core Data Sheet", "section": "Dosage", "text": "Take 1 tablet daily with meals."},
        {"document_name": "Core Data Sheet", "section": "Adverse Events", "text": "Nausea reported when taken without food."},
        {"document_name": "Patient Leaflet", "section": "How to take", "text": "Take 1 tablet daily."},
    ]
    occurrences = agent.detect_related_occurrences("tablet daily", document_sections)
    assert len(occurrences) == 2  # Found in section 1 and 3
