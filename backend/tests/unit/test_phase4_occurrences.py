"""Phase 4 Step 3: Human Occurrence Confirmation / Exclusion Tests.

Covers:
- RelatedOccurrence model review states (PENDING, CONFIRMED, EXCLUDED)
- Stable occurrence identity preservation
- POST /changes/occurrences/confirm API validation
  * Valid confirmation & exclusion
  * Unknown occurrence ID rejection
  * Occurrence belonging to another proposal rejection
  * Simultaneous confirm & exclude conflict rejection
  * Nonexistent proposal rejection
  * Rejected decision rejection
- Impact analysis recalculation (only CONFIRMED included, EXCLUDED preserved as evidence)
- Human approval gate safety (PENDING occurrences block approval; resolved allow approval)
- ApprovedChangeReport compatibility (confirmed & excluded statuses survive into final report)
"""

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.agents.document_change_agent import RegulatoryDocumentChangeAgent
from app.main import app
from app.models.comparison import EvidenceTrace
from app.models.document_change import (
    ApprovedChangeReport,
    ProposedChange,
    RelatedOccurrence,
    ReviewDecisionType,
    ReviewerDecision,
)
from app.services.change_manager import ChangeManagerService
from app.services.validation import ValidationService

client = TestClient(app)


# ==============================================================================
# 1. MODEL TESTS
# ==============================================================================


def test_occurrence_default_status_is_pending():
    """Verify that a newly instantiated RelatedOccurrence defaults to PENDING."""
    occ = RelatedOccurrence(
        occurrence_id="occ_001",
        section="Warnings and Precautions",
        match_type="exact",
        current_text="Do not exceed 4000 mg per day.",
        confidence=1.0,
    )
    assert occ.status == "PENDING"
    assert occ.occurrence_id == "occ_001"


def test_occurrence_status_accepts_confirmed():
    """Verify that RelatedOccurrence accepts CONFIRMED status."""
    occ = RelatedOccurrence(
        occurrence_id="occ_002",
        section="Dosage and Administration",
        match_type="normalized",
        current_text="Maximum dose: 4000 mg daily.",
        status="CONFIRMED",
    )
    assert occ.status == "CONFIRMED"


def test_occurrence_status_accepts_excluded():
    """Verify that RelatedOccurrence accepts EXCLUDED status."""
    occ = RelatedOccurrence(
        occurrence_id="occ_003",
        section="Adverse Reactions",
        match_type="semantic",
        current_text="Overdose may cause liver damage.",
        status="EXCLUDED",
    )
    assert occ.status == "EXCLUDED"


def test_occurrence_status_rejects_invalid():
    """Verify that RelatedOccurrence rejects invalid status values."""
    with pytest.raises(ValidationError):
        RelatedOccurrence(
            occurrence_id="occ_004",
            section="Contraindications",
            match_type="exact",
            current_text="Hypersensitivity to active substance.",
            status="INVALID_STATUS",
        )


# ==============================================================================
# 2. CONFIRMATION API & SERVICE TESTS
# ==============================================================================


@pytest.fixture
def setup_proposal_with_occurrences():
    """Create a proposal with multiple occurrences in the in-memory ChangeManager."""
    agent = RegulatoryDocumentChangeAgent()
    cm = ChangeManagerService()

    decision = ReviewerDecision(
        target_content_id="rc_101",
        candidate_id="cand_101",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Jane Regulatory",
        reviewer_notes="Standardized dosage text reuse.",
    )
    cm.record_decision(decision)

    doc_sections = [
        {"section": "Warnings and Precautions", "text": "Do not exceed 4000 mg in 24 hours to prevent hepatotoxicity."},
        {"section": "Overdosage", "text": "Do not exceed 4000 mg in 24 hours."},
    ]

    proposal = agent.formulate_change_proposal(
        decision=decision,
        section="Dosage and Administration",
        original_text="Do not exceed 4000 mg in 24 hours.",
        candidate_text="Maximum daily dosage is 3000 mg in 24 hours.",
        document_sections=doc_sections,
    )
    cm._proposals[proposal.change_id] = proposal

    # Also register with the global change_manager used by routes
    from app.routes.document_review import change_manager as route_cm
    route_cm.record_decision(decision)
    route_cm._proposals[proposal.change_id] = proposal

    yield proposal
    route_cm._proposals.pop(proposal.change_id, None)



def test_api_valid_confirmation_succeeds(setup_proposal_with_occurrences):
    """Verify POST /changes/occurrences/confirm marks an occurrence as CONFIRMED."""
    proposal = setup_proposal_with_occurrences
    assert len(proposal.related_occurrences) >= 2
    target_occ = proposal.related_occurrences[0]

    response = client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": proposal.change_id,
            "confirmed_occurrence_ids": [target_occ.occurrence_id],
            "excluded_occurrence_ids": [],
            "reviewer_notes": "Confirmed for coordinated propagation.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["change_id"] == proposal.change_id

    # Verify occurrence status in response
    updated_occ = next(o for o in data["related_occurrences"] if o["occurrence_id"] == target_occ.occurrence_id)
    assert updated_occ["status"] == "CONFIRMED"
    # Occurrence ID must be preserved
    assert updated_occ["occurrence_id"] == target_occ.occurrence_id


def test_api_valid_exclusion_succeeds(setup_proposal_with_occurrences):
    """Verify POST /changes/occurrences/confirm marks an occurrence as EXCLUDED."""
    proposal = setup_proposal_with_occurrences
    target_occ = proposal.related_occurrences[1]

    response = client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": proposal.change_id,
            "confirmed_occurrence_ids": [],
            "excluded_occurrence_ids": [target_occ.occurrence_id],
            "reviewer_notes": "Preserving original section wording.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    updated_occ = next(o for o in data["related_occurrences"] if o["occurrence_id"] == target_occ.occurrence_id)
    assert updated_occ["status"] == "EXCLUDED"


def test_api_unknown_occurrence_id_fails(setup_proposal_with_occurrences):
    """Verify unknown occurrence ID returns 400 Bad Request."""
    proposal = setup_proposal_with_occurrences

    response = client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": proposal.change_id,
            "confirmed_occurrence_ids": ["nonexistent_occ_id_999"],
            "excluded_occurrence_ids": [],
        },
    )
    assert response.status_code == 400
    assert "Unknown occurrence IDs" in response.json()["detail"]


def test_api_foreign_occurrence_id_fails(setup_proposal_with_occurrences):
    """Verify occurrence belonging to a different proposal is rejected."""
    proposal_a = setup_proposal_with_occurrences

    # Create proposal B with its own occurrence
    from app.routes.document_review import change_manager as route_cm
    decision_b = ReviewerDecision(
        target_content_id="rc_202",
        candidate_id="cand_202",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Second Reviewer",
    )
    route_cm.record_decision(decision_b)
    proposal_b = ProposedChange(
        change_id="prop_different_b",
        decision_id=decision_b.decision_id,
        section="Adverse Reactions",
        original_text="Old adverse text.",
        proposed_text="New adverse text.",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Update adverse.",
        related_occurrences=[
            RelatedOccurrence(
                occurrence_id="occ_foreign_b",
                section="Clinical Pharmacology",
                match_type="exact",
                current_text="Old adverse text.",
            )
        ],
    )
    try:
        route_cm._proposals[proposal_b.change_id] = proposal_b

        # Attempt to confirm proposal B's occurrence on proposal A
        response = client.post(
            "/changes/occurrences/confirm",
            json={
                "change_id": proposal_a.change_id,
                "confirmed_occurrence_ids": ["occ_foreign_b"],
                "excluded_occurrence_ids": [],
            },
        )
        assert response.status_code == 400
        assert "Unknown occurrence IDs do not belong to proposal" in response.json()["detail"]
    finally:
        route_cm._proposals.pop(proposal_b.change_id, None)


def test_api_simultaneous_confirm_and_exclude_fails(setup_proposal_with_occurrences):
    """Verify an occurrence cannot simultaneously be confirmed and excluded."""
    proposal = setup_proposal_with_occurrences
    occ_id = proposal.related_occurrences[0].occurrence_id

    response = client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": proposal.change_id,
            "confirmed_occurrence_ids": [occ_id],
            "excluded_occurrence_ids": [occ_id],
        },
    )
    assert response.status_code == 400
    assert "simultaneously confirmed and excluded" in response.json()["detail"]


def test_api_nonexistent_proposal_fails():
    """Verify confirming occurrences for a nonexistent proposal returns 404."""
    response = client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": "nonexistent_proposal_12345",
            "confirmed_occurrence_ids": ["occ_1"],
            "excluded_occurrence_ids": [],
        },
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_api_rejected_decision_cannot_confirm():
    """Verify proposals with REJECT decisions cannot have occurrences confirmed."""
    from app.routes.document_review import change_manager as route_cm
    decision_rej = ReviewerDecision(
        target_content_id="rc_rej",
        candidate_id="cand_rej",
        decision=ReviewDecisionType.REJECT,
        reviewer_name="Dr. Reject Reviewer",
    )
    route_cm.record_decision(decision_rej)
    proposal_rej = ProposedChange(
        change_id="prop_rejected_test",
        decision_id=decision_rej.decision_id,
        section="Warnings",
        original_text="Keep original text.",
        proposed_text="Rejected candidate text.",
        decision_type=ReviewDecisionType.REJECT,
        rationale="Rejected candidate.",
        status="REJECTED",
        related_occurrences=[
            RelatedOccurrence(
                occurrence_id="occ_rej_1",
                section="Dosage",
                match_type="exact",
                current_text="Keep original text.",
            )
        ],
    )
    try:
        route_cm._proposals[proposal_rej.change_id] = proposal_rej

        response = client.post(
            "/changes/occurrences/confirm",
            json={
                "change_id": proposal_rej.change_id,
                "confirmed_occurrence_ids": ["occ_rej_1"],
                "excluded_occurrence_ids": [],
            },
        )
        assert response.status_code == 400
        assert "REJECT" in response.json()["detail"]
    finally:
        route_cm._proposals.pop(proposal_rej.change_id, None)


# ==============================================================================
# 3. IMPACT ANALYSIS RECALCULATION TESTS
# ==============================================================================


def test_impact_analysis_recalculated_with_confirmed_only(setup_proposal_with_occurrences):
    """Verify that with 2 detected occurrences, 1 confirmed and 1 excluded,
    the impact analysis counts only the confirmed occurrence as affected,
    and preserves the excluded occurrence as evidence.
    """
    proposal = setup_proposal_with_occurrences
    assert len(proposal.related_occurrences) >= 2
    occ_confirm = proposal.related_occurrences[0]
    occ_exclude = proposal.related_occurrences[1]

    response = client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": proposal.change_id,
            "confirmed_occurrence_ids": [occ_confirm.occurrence_id],
            "excluded_occurrence_ids": [occ_exclude.occurrence_id],
        },
    )
    assert response.status_code == 200
    updated_data = response.json()

    impact = updated_data["impact_analysis"]
    # Target section + 1 confirmed occurrence = 2 affected sections
    assert impact["affected_sections_count"] == 2
    assert occ_confirm.section in impact["affected_sections"]
    # Excluded occurrence's section should NOT be counted as an affected section
    assert occ_exclude.section not in impact["affected_sections"]
    # Total affected items count is target (1) + confirmed (1) = 2
    assert impact["affected_content_count"] == 2

    # Verify both occurrences remain preserved in proposal
    assert len(updated_data["related_occurrences"]) == len(proposal.related_occurrences)
    preserved_excluded = next(
        o for o in updated_data["related_occurrences"] if o["occurrence_id"] == occ_exclude.occurrence_id
    )
    assert preserved_excluded["status"] == "EXCLUDED"
    assert preserved_excluded["current_text"] == occ_exclude.current_text


# ==============================================================================
# 4. PENDING OCCURRENCES GATE TESTS
# ==============================================================================


def test_approval_gate_blocked_when_occurrences_remain_pending(setup_proposal_with_occurrences):
    """Verify final human approval is blocked when any occurrence remains PENDING."""
    proposal = setup_proposal_with_occurrences
    # Ensure occurrences are PENDING
    assert any(occ.status == "PENDING" for occ in proposal.related_occurrences)

    # 1. Direct validation check: REG-VAL-006 error
    validator = ValidationService()
    findings = validator.validate_approval(
        approver_name="Dr. Regulatory Authority",
        approval_confirmation=True,
        proposals=[proposal],
    )
    error_findings = [f for f in findings if f.rule_id == "REG-VAL-006" and not f.passed]
    assert len(error_findings) == 1
    assert "unresolved related occurrences" in error_findings[0].message.lower()

    # 2. Endpoint check: POST /changes/approve fails
    response = client.post(
        "/changes/approve",
        json={
            "approver_name": "Dr. Regulatory Authority",
            "approval_confirmation": True,
            "proposal_ids": [proposal.change_id],
        },
    )
    assert response.status_code == 400
    assert "unresolved related occurrences" in response.json()["detail"].lower()


def test_approval_gate_proceeds_when_all_occurrences_resolved(setup_proposal_with_occurrences):
    """Verify final human approval succeeds once all occurrences are CONFIRMED or EXCLUDED."""
    proposal = setup_proposal_with_occurrences

    # Confirm first occurrence and exclude remaining
    confirmed_ids = [proposal.related_occurrences[0].occurrence_id]
    excluded_ids = [occ.occurrence_id for occ in proposal.related_occurrences[1:]]

    res_confirm = client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": proposal.change_id,
            "confirmed_occurrence_ids": confirmed_ids,
            "excluded_occurrence_ids": excluded_ids,
        },
    )
    assert res_confirm.status_code == 200

    # Validation check: REG-VAL-006 no longer fails
    from app.routes.document_review import change_manager as route_cm
    updated_proposal = route_cm.get_proposal(proposal.change_id)
    validator = ValidationService()
    findings = validator.validate_approval(
        approver_name="Dr. Regulatory Authority",
        approval_confirmation=True,
        proposals=[updated_proposal],
    )
    error_findings = [f for f in findings if f.severity == "ERROR" and not f.passed]
    assert len(error_findings) == 0

    # API approval succeeds
    response = client.post(
        "/changes/approve",
        json={
            "approver_name": "Dr. Regulatory Authority",
            "approval_confirmation": True,
            "proposal_ids": [proposal.change_id],
            "document_name": "Test Drug Labeling",
        },
    )
    assert response.status_code == 200
    report = response.json()
    assert report["author_approver"] == "Dr. Regulatory Authority"
    assert report["approval_confirmation"] is True


# ==============================================================================
# 5. APPROVED CHANGE REPORT COMPATIBILITY TESTS
# ==============================================================================


def test_report_preserves_confirmed_and_excluded_occurrence_statuses(setup_proposal_with_occurrences):
    """Verify occurrence statuses survive into the generated ApprovedChangeReport."""
    proposal = setup_proposal_with_occurrences
    occ_confirm = proposal.related_occurrences[0]
    occ_exclude = proposal.related_occurrences[1]

    # Resolve all occurrences
    client.post(
        "/changes/occurrences/confirm",
        json={
            "change_id": proposal.change_id,
            "confirmed_occurrence_ids": [occ_confirm.occurrence_id],
            "excluded_occurrence_ids": [occ_exclude.occurrence_id],
        },
    )

    # Approve and generate report
    response = client.post(
        "/changes/approve",
        json={
            "approver_name": "Dr. Lead Approver",
            "approval_confirmation": True,
            "proposal_ids": [proposal.change_id],
            "document_name": "Core Data Sheet v2.0",
        },
    )
    assert response.status_code == 200
    report_data = response.json()

    approved_change = report_data["changes"][0]
    assert approved_change["change_id"] == proposal.change_id

    # Verify occurrence statuses survive in report
    report_occs = approved_change["related_occurrences"]
    assert len(report_occs) >= 2

    rep_confirmed = next(o for o in report_occs if o["occurrence_id"] == occ_confirm.occurrence_id)
    assert rep_confirmed["status"] == "CONFIRMED"

    rep_excluded = next(o for o in report_occs if o["occurrence_id"] == occ_exclude.occurrence_id)
    assert rep_excluded["status"] == "EXCLUDED"
