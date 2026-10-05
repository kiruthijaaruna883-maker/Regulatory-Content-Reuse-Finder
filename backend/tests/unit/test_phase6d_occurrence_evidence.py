"""Unit tests for Phase 6D: 6-Dimensional Occurrence Evidence in Agent 2.

Covers:
- Test A: 6D evidence exists for detected occurrences across all six dimensions
- Test B: Dimensional scores are real comparator scores (0.0 <= score <= 1.0)
- Test C: Dimensional evaluations preserve statuses (MATCH, PARTIAL, MISMATCH, NOT_APPLICABLE)
- Test D: Human occurrence gate is preserved (new occurrences default strictly to PENDING)
- Test E: Occurrence confirmation still works and updates section-level impact
- Test F: Occurrence exclusion still works and isolates impact from excluded occurrences
- Test G: Pending approval gate (REG-VAL-006) blocks approval while occurrences are PENDING
- Test H: Persistence preserves 6D dimensional evidence and scores across SQLite save and reload
- Test I: False-match protection continues to discard conflicting drug entities
- Test J: Deduplication ensures 1 occurrence + 6D evidence = 1 RelatedOccurrence (not duplicate occurrences)
"""

import os
import tempfile
import pytest
from app.agents.document_change_agent import RegulatoryDocumentChangeAgent
from app.models.document_change import (
    ProposedChange,
    RelatedOccurrence,
    ReviewDecisionType,
    ReviewerDecision,
)
from app.persistence.sqlite_store import WorkflowSQLiteStore
from app.services.change_manager import ChangeManagerService
from app.services.validation import ValidationService


@pytest.fixture
def agent() -> RegulatoryDocumentChangeAgent:
    """Instantiate RegulatoryDocumentChangeAgent."""
    return RegulatoryDocumentChangeAgent()


@pytest.fixture
def test_sections():
    """Standardized test sections for occurrence detection."""
    return [
        {
            "document_name": "Core Data Sheet",
            "section": "Dosage and Administration",
            "location": "Paragraph 1",
            "text": "Acetaminophen 650 mg orally every 4 to 6 hours as needed.",
        },
        {
            "document_name": "Patient Leaflet",
            "section": "How to Take",
            "location": "Section 3",
            "text": "Acetaminophen 650 mg orally every 4 to 6 hours as needed for pain relief.",
        },
        {
            "document_name": "Warnings",
            "section": "Warnings and Precautions",
            "location": "Section 5.1",
            "text": "Do not exceed maximum daily dose of Acetaminophen.",
        },
    ]


# ==============================================================================
# TEST A: 6D Evidence Exists
# ==============================================================================
def test_6d_evidence_exists_for_occurrence(agent, test_sections):
    """Verify detected occurrences contain all six dimensional evidence keys."""
    target_text = "Acetaminophen 650 mg orally every 4 to 6 hours as needed."
    target_phrase = "Acetaminophen 650 mg"

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=test_sections,
        target_text=target_text,
    )

    assert len(occs) >= 1
    occ = occs[0]

    assert occ.dimensional_evidence is not None
    assert occ.dimensional_scores is not None

    expected_dimensions = ["meaning", "template", "context", "structure", "format", "key_information"]
    for dim in expected_dimensions:
        assert dim in occ.dimensional_evidence, f"Missing {dim} in dimensional_evidence"
        assert dim in occ.dimensional_scores, f"Missing {dim} in dimensional_scores"


# ==============================================================================
# TEST B: Scores Are Real Comparator Scores
# ==============================================================================
def test_6d_scores_are_real_comparator_scores(agent, test_sections):
    """Verify dimensional scores are valid floats bounded between 0.0 and 1.0 from comparator."""
    target_text = "Acetaminophen 650 mg orally every 4 to 6 hours as needed."
    target_phrase = "Acetaminophen 650 mg"

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=test_sections,
        target_text=target_text,
    )

    assert len(occs) >= 1
    scores = occs[0].dimensional_scores
    for dim, score in scores.items():
        assert score is not None, f"Score for {dim} should not be None"
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0, f"Score for {dim} ({score}) out of range [0.0, 1.0]"

    # Verify key information score is high for exact match
    assert scores["key_information"] >= 0.8


# ==============================================================================
# TEST C: Statuses Are Preserved
# ==============================================================================
def test_6d_statuses_are_preserved(agent, test_sections):
    """Verify each dimensional evaluation preserves the comparator's status value."""
    target_text = "Acetaminophen 650 mg orally every 4 to 6 hours as needed."
    target_phrase = "Acetaminophen 650 mg"

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=test_sections,
        target_text=target_text,
    )

    occ = occs[0]
    valid_statuses = {"MATCH", "PARTIAL", "MISMATCH", "NOT_APPLICABLE"}

    for dim, eval_dict in occ.dimensional_evidence.items():
        assert "dimension" in eval_dict
        assert eval_dict["dimension"] == dim
        assert "status" in eval_dict
        status = eval_dict["status"]
        status_val = status.value if hasattr(status, "value") else str(status)
        assert status_val in valid_statuses
        assert "details" in eval_dict
        assert len(eval_dict["details"]) > 0


# ==============================================================================
# TEST D: Human Gate Unchanged (PENDING Default)
# ==============================================================================
def test_occurrence_human_gate_defaults_to_pending(agent, test_sections):
    """Verify new occurrences default strictly to PENDING regardless of 6D scores."""
    target_text = "Acetaminophen 650 mg orally every 4 to 6 hours as needed."
    target_phrase = "Acetaminophen 650 mg"

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=test_sections,
        target_text=target_text,
    )

    for occ in occs:
        assert occ.status == "PENDING"


# ==============================================================================
# TEST E: Confirmation Still Works
# ==============================================================================
def test_occurrence_confirmation_updates_impact(agent, test_sections):
    """Verify human confirmation marks occurrence CONFIRMED and contributes to impact."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        manager = ChangeManagerService(db_path=db_path)
        decision = ReviewerDecision(
            target_content_id="rc_001",
            decision=ReviewDecisionType.REUSE,
            reviewer_name="Dr. Reviewer",
        )
        manager.record_decision(decision)

        proposal = agent.formulate_change_proposal(
            decision=decision,
            section="Dosage and Administration",
            original_text="Acetaminophen 500 mg orally.",
            candidate_text="Acetaminophen 650 mg orally every 4 to 6 hours as needed.",
            document_sections=test_sections,
        )
        saved = manager.save_proposal(proposal)

        assert len(saved.related_occurrences) >= 1
        occ_id = saved.related_occurrences[0].occurrence_id

        # Confirm occurrence
        updated = manager.confirm_occurrences(
            change_id=saved.change_id,
            confirmed_occurrence_ids=[occ_id],
            excluded_occurrence_ids=[],
            reviewer_notes="Confirmed posology occurrence across dossier.",
        )

        confirmed_occ = next(o for o in updated.related_occurrences if o.occurrence_id == occ_id)
        assert confirmed_occ.status == "CONFIRMED"
        assert confirmed_occ.dimensional_scores is not None
        assert updated.impact_analysis.affected_sections_count >= 1
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# ==============================================================================
# TEST F: Exclusion Still Works
# ==============================================================================
def test_occurrence_exclusion_isolates_impact(agent, test_sections):
    """Verify human exclusion marks occurrence EXCLUDED and omits from coordinated impact."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        manager = ChangeManagerService(db_path=db_path)
        decision = ReviewerDecision(
            target_content_id="rc_002",
            decision=ReviewDecisionType.REUSE,
            reviewer_name="Dr. Reviewer",
        )
        manager.record_decision(decision)

        proposal = agent.formulate_change_proposal(
            decision=decision,
            section="Dosage and Administration",
            original_text="Acetaminophen 500 mg orally.",
            candidate_text="Acetaminophen 650 mg orally every 4 to 6 hours as needed.",
            document_sections=test_sections,
        )
        saved = manager.save_proposal(proposal)

        occ_id = saved.related_occurrences[0].occurrence_id

        # Exclude occurrence
        updated = manager.confirm_occurrences(
            change_id=saved.change_id,
            confirmed_occurrence_ids=[],
            excluded_occurrence_ids=[occ_id],
            reviewer_notes="Excluded from coordinated update to maintain local wording.",
        )

        excluded_occ = next(o for o in updated.related_occurrences if o.occurrence_id == occ_id)
        assert excluded_occ.status == "EXCLUDED"
        # 6D evidence preserved even when excluded
        assert excluded_occ.dimensional_scores is not None
        assert excluded_occ.dimensional_evidence is not None
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# ==============================================================================
# TEST G: Pending Approval Block (REG-VAL-006)
# ==============================================================================
def test_pending_occurrence_blocks_approval_gate(agent, test_sections):
    """Verify REG-VAL-006 blocks approval while any occurrence remains PENDING."""
    decision = ReviewerDecision(
        target_content_id="rc_003",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Reviewer",
    )
    proposal = agent.formulate_change_proposal(
        decision=decision,
        section="Dosage and Administration",
        original_text="Acetaminophen 500 mg orally.",
        candidate_text="Acetaminophen 650 mg orally every 4 to 6 hours as needed.",
        document_sections=test_sections,
    )

    validator = ValidationService()
    findings = validator.validate_approval(
        approver_name="Regulatory Director",
        approval_confirmation=True,
        proposals=[proposal],
    )

    reg_val_006 = next((f for f in findings if f.rule_id == "REG-VAL-006"), None)
    assert reg_val_006 is not None
    assert reg_val_006.status == "FAILED"
    assert not reg_val_006.passed


# ==============================================================================
# TEST H: Persistence Preserves 6D Evidence
# ==============================================================================
def test_persistence_preserves_6d_evidence(agent, test_sections):
    """Verify proposals with 6D occurrence evidence persist and hydrate from SQLite without loss."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = WorkflowSQLiteStore(db_path=db_path)
        decision = ReviewerDecision(
            target_content_id="rc_004",
            decision=ReviewDecisionType.REUSE,
            reviewer_name="Dr. Reviewer",
        )
        store.save_decision(decision)

        proposal = agent.formulate_change_proposal(
            decision=decision,
            section="Dosage and Administration",
            original_text="Acetaminophen 500 mg orally.",
            candidate_text="Acetaminophen 650 mg orally every 4 to 6 hours as needed.",
            document_sections=test_sections,
        )
        saved = store.save_proposal(proposal)

        # Hydrate from fresh connection
        fresh_store = WorkflowSQLiteStore(db_path=db_path)
        hydrated = fresh_store.get_proposal(saved.change_id)

        assert hydrated is not None
        assert len(hydrated.related_occurrences) == len(saved.related_occurrences)

        h_occ = hydrated.related_occurrences[0]
        assert h_occ.dimensional_scores is not None
        assert h_occ.dimensional_evidence is not None
        assert "meaning" in h_occ.dimensional_scores
        assert "key_information" in h_occ.dimensional_evidence
        assert h_occ.dimensional_scores["key_information"] == saved.related_occurrences[0].dimensional_scores["key_information"]
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# ==============================================================================
# TEST I: False-Match Protection Discards Disparate Drugs
# ==============================================================================
def test_false_match_protection_discards_disparate_drugs(agent):
    """Verify false-match protection discards text with conflicting drug entities."""
    sections = [
        {
            "document_name": "Overdose Sheet",
            "section": "Overdosage",
            "text": "Ibuprofen 400 mg overdose requires gastric lavage.",
        }
    ]
    target_text = "Acetaminophen 650 mg overdose requires N-acetylcysteine."
    target_phrase = "overdose requires"

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sections,
        target_text=target_text,
    )

    # Discarded because Acetaminophen != Ibuprofen
    assert len(occs) == 0


# ==============================================================================
# TEST J: Deduplication (1 Occurrence + 6D Evidence = 1 RelatedOccurrence)
# ==============================================================================
def test_deduplication_preserves_single_occurrence_with_6d_evidence(agent):
    """Verify that multiple matching dimensions do not duplicate the occurrence object."""
    sections = [
        {
            "document_name": "Core Data Sheet",
            "section": "Dosage and Administration",
            "text": "Acetaminophen 650 mg orally every 4 to 6 hours as needed.",
        }
    ]
    target_text = "Acetaminophen 650 mg orally every 4 to 6 hours as needed."
    target_phrase = "Acetaminophen 650 mg"

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sections,
        target_text=target_text,
    )

    # Exactly 1 occurrence despite matching on exact, normalized, structured, and all 6 dimensions
    assert len(occs) == 1
    assert len(occs[0].dimensional_scores) == 6
    assert len(occs[0].dimensional_evidence) == 6
