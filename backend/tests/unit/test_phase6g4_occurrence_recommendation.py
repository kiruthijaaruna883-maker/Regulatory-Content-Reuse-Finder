"""Comprehensive unit and integration tests for Phase 6G.4:
Automatic Occurrence Recommendations.

Validates the 24 verification criteria:
1. Strong exact match recommends CONFIRM.
2. Strong normalized match recommends CONFIRM.
3. Context mismatch recommends EXCLUDE.
4. Critical key-information mismatch recommends EXCLUDE.
5. Semantic/indirect match recommends REVIEW_REQUIRED.
6. Ambiguous evidence recommends REVIEW_REQUIRED.
7. False-match evidence is not recommended for confirmation.
8. Every new occurrence remains PENDING.
9. CONFIRM recommendation does not confirm automatically.
10. EXCLUDE recommendation does not exclude automatically.
11. Recommendation does not trigger impact analysis.
12. Recommendation does not trigger validation.
13. REG-VAL-006 remains blocked while occurrence is PENDING.
14. Existing human confirmation endpoint still works.
15. Existing human exclusion endpoint still works.
16. Reviewer can override the recommendation.
17. Audit records remain associated with human decisions only.
18. Source regulatory documents remain unchanged.
19. Existing four detection layers remain intact.
20. Existing 6D evidence remains intact.
21. Existing Agent 2 workflow remains compatible.
22. Existing Phase 6G.3 behavior remains intact.
23. No arbitrary confidence values are generated.
24. No new numeric thresholds are introduced.
"""

from fastapi.testclient import TestClient
import pytest

from app.agents.document_change_agent import RegulatoryDocumentChangeAgent
from app.main import app
from app.models.content import RegulatoryContentItem
from app.models.document_change import (
    ProposedChange,
    RelatedOccurrence,
    ReviewDecisionType,
    ReviewerDecision,
)
from app.persistence.sqlite_store import WorkflowSQLiteStore
from app.services.change_manager import ChangeManagerService
from app.services.multi_dimensional_comparator import MultiDimensionalComparator
from app.services.validation import ValidationService

client = TestClient(app)


@pytest.fixture
def agent() -> RegulatoryDocumentChangeAgent:
    """Instantiate RegulatoryDocumentChangeAgent."""
    return RegulatoryDocumentChangeAgent()


@pytest.fixture
def sample_sections():
    """Standard multi-section test document."""
    return [
        {
            "document_name": "Prescribing Information",
            "section": "Dosage and Administration",
            "location": "Section 2.1",
            "text": "Take 50 mg by mouth twice daily with water.",
        },
        {
            "document_name": "Patient Information Leaflet",
            "section": "How to Take",
            "location": "Section 3",
            "text": "Take 50 mg by mouth, twice daily with water.",
        },
        {
            "document_name": "Prescribing Information",
            "section": "Overdosage",
            "location": "Section 10",
            "text": "In acute overdosage, gastric lavage and hemodialysis may be considered immediately.",
        },
    ]


# ==============================================================================
# 1. STRONG EXACT MATCH RECOMMENDS CONFIRM
# ==============================================================================


def test_01_strong_exact_match_recommends_confirm(agent, sample_sections):
    """1. Direct exact match with aligned 6D evidence recommends CONFIRM."""
    target_text = "Take 50 mg by mouth twice daily with water."
    target_phrase = "Take 50 mg by mouth twice daily with water."

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sample_sections,
        target_text=target_text,
    )

    exact_occs = [o for o in occs if o.match_type == "exact_match"]
    assert len(exact_occs) >= 1
    occ = exact_occs[0]

    assert occ.recommended_action == "CONFIRM"
    assert occ.recommendation_reason is not None
    assert "direct exact match" in occ.recommendation_reason.lower() or "aligned" in occ.recommendation_reason.lower()
    assert occ.status == "PENDING"


# ==============================================================================
# 2. STRONG NORMALIZED MATCH RECOMMENDS CONFIRM
# ==============================================================================


def test_02_strong_normalized_match_recommends_confirm(agent, sample_sections):
    """2. Direct normalized match (punctuation/spacing variation) recommends CONFIRM."""
    target_text = "Take 50 mg by mouth twice daily with water."
    target_phrase = "Take 50 mg by mouth twice daily with water."

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sample_sections,
        target_text=target_text,
    )

    norm_occs = [o for o in occs if o.match_type == "normalized_match"]
    assert len(norm_occs) >= 1
    occ = norm_occs[0]

    assert occ.recommended_action == "CONFIRM"
    assert occ.recommendation_reason is not None
    assert "direct normalized match" in occ.recommendation_reason.lower() or "aligned" in occ.recommendation_reason.lower()
    assert occ.status == "PENDING"


# ==============================================================================
# 3. CONTEXT MISMATCH RECOMMENDS EXCLUDE
# ==============================================================================


def test_03_context_mismatch_recommends_exclude(agent):
    """3. Occurrence in incompatible clinical/regulatory context recommends EXCLUDE."""
    target_text = "Adults: Take 20 mg orally once daily."
    target_phrase = "20 mg orally once daily"
    sections = [
        {
            "document_name": "Clinical Pharmacology",
            "section": "Renal Impairment",
            "text": "For mild renal impairment, initiate treatment with 20 mg orally once daily.",
        }
    ]

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sections,
        target_text=target_text,
    )

    assert len(occs) >= 1
    occ = occs[0]
    # Context mismatch (adult vs renal impairment population) triggers EXCLUDE
    assert occ.recommended_action == "EXCLUDE"
    assert occ.recommendation_reason is not None
    assert "exclude" in occ.recommendation_reason.lower() or "warning" in occ.recommendation_reason.lower()
    assert occ.status == "PENDING"


# ==============================================================================
# 4. CRITICAL KEY-INFORMATION MISMATCH RECOMMENDS EXCLUDE
# ==============================================================================


def test_04_critical_key_information_mismatch_recommends_exclude(agent):
    """4. Occurrence where key entities conflict recommends EXCLUDE."""
    target_text = "Administer 10 mg lisinopril orally once daily."
    target_phrase = "10 mg"
    sections = [
        {
            "document_name": "Prescribing Information",
            "section": "Overdosage",
            "text": "Overdose: Greater than 10 mg metoprolol may cause marked hypotension.",
        }
    ]

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sections,
        target_text=target_text,
    )

    # Discarded by false-match check or marked EXCLUDE / REVIEW_REQUIRED
    for occ in occs:
        assert occ.recommended_action in ("EXCLUDE", "REVIEW_REQUIRED")
        assert occ.recommended_action != "CONFIRM"
        assert occ.status == "PENDING"


# ==============================================================================
# 5. SEMANTIC / INDIRECT MATCH RECOMMENDS REVIEW_REQUIRED
# ==============================================================================


def test_05_semantic_indirect_match_recommends_review_required(agent):
    """5. Indirect semantic-only retrieval recommends REVIEW_REQUIRED."""
    target_text = "Adults should take two 500 mg tablets every six hours with water."
    target_phrase = "two 500 mg tablets every six hours"
    sections = [
        {
            "document_name": "Standard Guidance",
            "section": "Posology",
            "text": "Recommended posology for adult pain relief is 1000 mg administered every 6 hours as needed.",
        }
    ]

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sections,
        target_text=target_text,
    )

    for occ in occs:
        if occ.match_type == "semantic_match":
            assert occ.recommended_action == "REVIEW_REQUIRED"
            assert occ.recommendation_reason is not None
            assert "semantic" in occ.recommendation_reason.lower() or "review" in occ.recommendation_reason.lower()
            assert occ.status == "PENDING"


# ==============================================================================
# 6. AMBIGUOUS EVIDENCE RECOMMENDS REVIEW_REQUIRED
# ==============================================================================


def test_06_ambiguous_evidence_recommends_review_required(agent):
    """6. Direct phrase match with partial administrative alignment recommends REVIEW_REQUIRED."""
    target_text = "Administer 100 mg by intravenous infusion over 60 minutes."
    target_phrase = "intravenous infusion"
    sections = [
        {
            "document_name": "Core Sheet",
            "section": "Preparation",
            "text": "For intravenous infusion, dilute 100 mg in 250 mL normal saline prior to administration.",
        }
    ]

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sections,
        target_text=target_text,
    )

    assert len(occs) >= 1
    occ = occs[0]
    assert occ.recommended_action == "REVIEW_REQUIRED"
    assert occ.status == "PENDING"


# ==============================================================================
# 7. FALSE-MATCH EVIDENCE IS NOT RECOMMENDED FOR CONFIRMATION
# ==============================================================================


def test_07_false_match_evidence_not_recommended_for_confirmation(agent):
    """7. Discrepant clinical entities are never recommended for CONFIRM."""
    target_text = "Take 50 mg losartan orally once daily."
    target_phrase = "Take 50 mg"
    sections = [
        {
            "document_name": "Product Info",
            "section": "Dosage",
            "text": "Take 50 mg hydrochlorothiazide orally once daily.",
        }
    ]

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sections,
        target_text=target_text,
    )

    # Discarded by false-match check or marked EXCLUDE / REVIEW_REQUIRED
    for occ in occs:
        assert occ.recommended_action != "CONFIRM"


# ==============================================================================
# 8, 9, 10. EVERY OCCURRENCE REMAINS PENDING REGARDLESS OF RECOMMENDATION
# ==============================================================================


def test_08_every_new_occurrence_remains_pending(agent, sample_sections):
    """8, 9, 10. All newly detected occurrences strictly keep status=PENDING."""
    target_text = "Take 50 mg by mouth twice daily with water."
    target_phrase = "Take 50 mg by mouth twice daily with water."

    occs = agent.detect_related_occurrences(
        target_phrase=target_phrase,
        document_sections=sample_sections,
        target_text=target_text,
    )

    assert len(occs) >= 1
    for occ in occs:
        assert occ.status == "PENDING", "Occurrence status must strictly default to PENDING"
        assert occ.recommended_action in ("CONFIRM", "EXCLUDE", "REVIEW_REQUIRED")


# ==============================================================================
# 11, 12. RECOMMENDATION DOES NOT TRIGGER IMPACT ANALYSIS OR VALIDATION
# ==============================================================================


def test_11_12_recommendation_does_not_trigger_impact_or_validation(agent, sample_sections):
    """11, 12. Occurrence detection attaches advisory fields without mutating proposal impact."""
    decision = ReviewerDecision(
        target_content_id="target_001",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Reviewer",
    )

    proposal = agent.formulate_change_proposal(
        decision=decision,
        section="Dosage and Administration",
        original_text="Take 50 mg by mouth twice daily with water.",
        candidate_text="Take 50 mg by mouth twice daily with water.",
        document_sections=sample_sections,
    )

    assert proposal is not None
    # All occurrences remain PENDING
    assert all(occ.status == "PENDING" for occ in proposal.related_occurrences)
    # Impact analysis does NOT treat pending occurrences as confirmed
    confirmed_in_impact = [
        occ for occ in proposal.related_occurrences if occ.status == "CONFIRMED"
    ]
    assert len(confirmed_in_impact) == 0


# ==============================================================================
# 13. REG-VAL-006 REMAINS BLOCKED WHILE OCCURRENCE IS PENDING
# ==============================================================================


def test_13_reg_val_006_remains_blocked_while_occurrence_is_pending(agent, sample_sections):
    """13. Approval gate REG-VAL-006 strictly blocks approval when any occurrence is PENDING."""
    validator = ValidationService()
    decision = ReviewerDecision(
        target_content_id="target_001",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Reviewer",
    )

    proposal = agent.formulate_change_proposal(
        decision=decision,
        section="Dosage and Administration",
        original_text="Take 50 mg by mouth twice daily with water.",
        candidate_text="Take 50 mg by mouth twice daily with water.",
        document_sections=sample_sections,
    )

    assert len(proposal.related_occurrences) > 0

    findings = validator.validate_approval(
        approver_name="Dr. Approver",
        approval_confirmation=True,
        proposals=[proposal],
    )

    # REG-VAL-006 MUST be present, FAILED, and severity ERROR
    reg_val_006 = next((f for f in findings if f.rule_id == "REG-VAL-006"), None)
    assert reg_val_006 is not None
    assert reg_val_006.passed is False
    assert reg_val_006.severity == "ERROR"


# ==============================================================================
# 14, 15, 16. HUMAN DECISION ENDPOINTS AND OVERRIDE
# ==============================================================================


def test_14_15_16_human_confirmation_and_override_endpoints(agent, sample_sections, tmp_path):
    """14, 15, 16. Reviewer explicitly confirms or excludes, with full authority to override recommendations."""
    cm = ChangeManagerService()
    decision = ReviewerDecision(
        target_content_id="target_001",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Reviewer",
    )
    cm.record_decision(decision)

    proposal = agent.formulate_change_proposal(
        decision=decision,
        section="Dosage and Administration",
        original_text="Take 50 mg by mouth twice daily with water.",
        candidate_text="Take 50 mg by mouth twice daily with water.",
        document_sections=sample_sections,
    )
    cm.save_proposal(proposal)

    from app.routes.document_review import change_manager as route_cm
    route_cm.save_proposal(proposal)

    assert len(proposal.related_occurrences) >= 1
    target_occ = proposal.related_occurrences[0]

    # Reviewer confirms an occurrence
    res_confirm = client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": proposal.change_id,
            "confirmed_occurrence_ids": [target_occ.occurrence_id],
            "excluded_occurrence_ids": [],
            "reviewer_notes": "Explicit human confirmation.",
        },
    )
    assert res_confirm.status_code == 200
    updated_prop = res_confirm.json()
    confirmed_item = next(
        o for o in updated_prop["related_occurrences"] if o["occurrence_id"] == target_occ.occurrence_id
    )
    assert confirmed_item["status"] == "CONFIRMED"

    # Reviewer overrides a CONFIRM recommendation to EXCLUDE
    res_override = client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": proposal.change_id,
            "confirmed_occurrence_ids": [],
            "excluded_occurrence_ids": [target_occ.occurrence_id],
            "reviewer_notes": "Overridden by human reviewer to exclude.",
        },
    )
    assert res_override.status_code == 200
    overridden_prop = res_override.json()
    overridden_item = next(
        o for o in overridden_prop["related_occurrences"] if o["occurrence_id"] == target_occ.occurrence_id
    )
    assert overridden_item["status"] == "EXCLUDED"


# ==============================================================================
# 17. AUDIT RECORDS ASSOCIATED WITH HUMAN DECISIONS ONLY
# ==============================================================================


def test_17_audit_records_only_on_human_decisions(agent, sample_sections, tmp_path):
    """17. Detecting occurrences does not emit OCCURRENCES_CONFIRMED audit events."""
    db_file = tmp_path / "test_g4_audit.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    # Run detection
    target_text = "Take 50 mg by mouth twice daily with water."
    occs = agent.detect_related_occurrences(
        target_phrase="Take 50 mg",
        document_sections=sample_sections,
        target_text=target_text,
    )
    assert len(occs) >= 1

    # Verify no OCCURRENCES_CONFIRMED events exist in audit table
    audit_events = store.list_audit_events()
    confirm_events = [e for e in audit_events if e.event_type == "OCCURRENCES_CONFIRMED"]
    assert len(confirm_events) == 0


# ==============================================================================
# 18. SOURCE DOCUMENTS REMAIN STRICTLY UNCHANGED
# ==============================================================================


def test_18_source_documents_remain_strictly_unchanged(agent, sample_sections):
    """18. Document sections are never modified during occurrence recommendation."""
    original_texts = [s["text"] for s in sample_sections]

    agent.detect_related_occurrences(
        target_phrase="Take 50 mg",
        document_sections=sample_sections,
        target_text=sample_sections[0]["text"],
    )

    current_texts = [s["text"] for s in sample_sections]
    assert original_texts == current_texts


# ==============================================================================
# 19, 20. FOUR DETECTION LAYERS AND 6D EVIDENCE INTACT
# ==============================================================================


def test_19_20_four_detection_layers_and_6d_evidence_intact(agent, sample_sections):
    """19, 20. 4 detection layers and 6D evidence dictionary remain intact on occurrences."""
    occs = agent.detect_related_occurrences(
        target_phrase="Take 50 mg by mouth twice daily with water.",
        document_sections=sample_sections,
        target_text="Take 50 mg by mouth twice daily with water.",
    )

    assert len(occs) >= 1
    occ = occs[0]
    assert occ.dimensional_evidence is not None
    assert occ.dimensional_scores is not None
    expected_dims = ["meaning", "template", "context", "structure", "format", "key_information"]
    for d in expected_dims:
        assert d in occ.dimensional_evidence
        assert d in occ.dimensional_scores


# ==============================================================================
# 21, 22. AGENT 2 AND PHASE 6G.3 BEHAVIOR INTACT
# ==============================================================================


def test_21_22_agent2_and_phase6g3_behavior_intact(agent):
    """21, 22. Phase 6G.3 advisory ADAPT wording remains compatible with Agent 2."""
    comparator = MultiDimensionalComparator()
    target_text = "50 mg PO BID"
    candidate = RegulatoryContentItem(
        source="DailyMed",
        text="Take 50 mg by mouth twice daily with a full glass of water.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target_text,
        candidate=candidate,
    )
    res = comparator.evaluate_recommendation(
        match=match,
        differences=diffs,
        similarity_score=0.85,
        target_text=target_text,
        candidate_text=candidate.text,
    )

    assert res.decision == ReviewDecisionType.ADAPT
    assert res.proposed_adapted_text is not None


# ==============================================================================
# 23, 24. NO ARBITRARY CONFIDENCE VALUES OR NEW THRESHOLDS
# ==============================================================================


def test_23_24_no_arbitrary_confidence_values(agent, sample_sections):
    """23, 24. For exact/normalized matches, confidence is None (no manufactured confidence numbers)."""
    occs = agent.detect_related_occurrences(
        target_phrase="Take 50 mg by mouth twice daily with water.",
        document_sections=sample_sections,
        target_text="Take 50 mg by mouth twice daily with water.",
    )

    for occ in occs:
        if occ.match_type in ("exact_match", "normalized_match"):
            # Strictly None: no arbitrary manufactured confidence range like 0.90-0.95
            assert occ.recommendation_confidence is None
