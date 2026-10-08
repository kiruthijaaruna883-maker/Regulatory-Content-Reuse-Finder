"""Unit tests verifying regulatory candidate reference text flow for REUSE and ADAPT decisions.

Covers:
TEST 1 - REUSE with candidate reference text uses candidate text
TEST 2 - REUSE without candidate reference fails with controlled ValueError
TEST 3 - ADAPT with candidate reference uses candidate text as base
TEST 4 - ADAPT without candidate reference fails with controlled ValueError
TEST 5 - ComparisonCandidate structure (content_item.text) extracts reference text
TEST 6 - Backend /changes/analyze resolves candidate text via decision.candidate_id fallback
"""

import pytest
from fastapi.testclient import TestClient

from app.agents.document_change_agent import RegulatoryDocumentChangeAgent
from app.main import app
from app.models.comparison import ComparisonCandidate
from app.models.content import RegulatoryContentItem
from app.models.document_change import ReviewDecisionType, ReviewerDecision
from app.services.candidate_store import get_candidate_store
from app.services.change_manager import ChangeManagerService


@pytest.fixture
def change_agent():
    return RegulatoryDocumentChangeAgent()


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# TEST 1 — REUSE with candidate reference
# ==============================================================================

def test_reuse_with_candidate_reference(change_agent):
    """TEST 1: REUSE decision must adopt selected candidate reference text, not original text."""
    original_text = "Original regulatory wording"
    candidate_text = "Selected regulatory reference wording"

    decision = ReviewerDecision(
        target_content_id="sec_001",
        candidate_id="cand_001",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Lead Reviewer",
        reviewer_notes="Direct reuse of approved DailyMed text.",
    )

    proposal = change_agent.formulate_change_proposal(
        decision=decision,
        section="Indications and Usage",
        original_text=original_text,
        candidate_text=candidate_text,
    )

    assert proposal is not None
    assert proposal.decision_type == ReviewDecisionType.REUSE
    assert proposal.proposed_text == "Selected regulatory reference wording"
    assert proposal.original_text == "Original regulatory wording"
    assert proposal.proposed_text != proposal.original_text


# ==============================================================================
# TEST 2 — REUSE without candidate reference
# ==============================================================================

def test_reuse_without_candidate_reference_raises_controlled_error(change_agent):
    """TEST 2: REUSE without candidate reference text must fail with controlled error and NEVER use original text."""
    original_text = "Original regulatory wording"

    decision = ReviewerDecision(
        target_content_id="sec_002",
        candidate_id="cand_002",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Lead Reviewer",
        reviewer_notes="Attempted reuse without reference.",
    )

    # Empty string
    with pytest.raises(ValueError, match="Candidate reference text is required for a REUSE decision"):
        change_agent.formulate_change_proposal(
            decision=decision,
            section="Indications and Usage",
            original_text=original_text,
            candidate_text="",
        )

    # None / omitted
    with pytest.raises(ValueError, match="Candidate reference text is required for a REUSE decision"):
        change_agent.formulate_change_proposal(
            decision=decision,
            section="Indications and Usage",
            original_text=original_text,
            candidate_text=None,
        )


# ==============================================================================
# TEST 3 — ADAPT with candidate reference
# ==============================================================================

def test_adapt_with_candidate_reference(change_agent, monkeypatch):
    """TEST 3: ADAPT decision must supply candidate reference text to the adaptation mechanism."""
    original_text = "Original regulatory wording"
    candidate_text = "Selected regulatory reference wording"
    instructions = "Reduce dose to 50% for hepatic impairment cohort."

    decision = ReviewerDecision(
        target_content_id="sec_003",
        candidate_id="cand_003",
        decision=ReviewDecisionType.ADAPT,
        reviewer_name="Dr. Lead Reviewer",
        reviewer_notes="Adapt reference for hepatic impairment.",
        adaptation_instructions=instructions,
    )

    # Spy on _synthesize_adaptation to verify candidate_text is passed to the adaptation process
    synthesize_calls = []
    original_synthesize = change_agent._synthesize_adaptation

    def spy_synthesize(*args, **kwargs):
        synthesize_calls.append(kwargs)
        return original_synthesize(*args, **kwargs)

    monkeypatch.setattr(change_agent, "_synthesize_adaptation", spy_synthesize)

    proposal = change_agent.formulate_change_proposal(
        decision=decision,
        section="Dosage and Administration",
        original_text=original_text,
        candidate_text=candidate_text,
    )

    assert proposal is not None
    assert proposal.decision_type == ReviewDecisionType.ADAPT
    assert proposal.original_text == original_text
    assert proposal.proposed_text != original_text
    # Verify adaptation mechanism received the candidate reference text
    assert len(synthesize_calls) == 1
    assert synthesize_calls[0]["candidate_text"] == "Selected regulatory reference wording"
    assert synthesize_calls[0]["original_text"] == "Original regulatory wording"
    assert synthesize_calls[0]["instructions"] == instructions


def test_adapt_with_candidate_reference_deterministic():
    """Verify deterministic fallback grounds adaptation in candidate_text, never original_text."""
    agent = RegulatoryDocumentChangeAgent()
    agent.has_llm = False  # Enforce deterministic mode

    original_text = "Original regulatory wording"
    candidate_text = "Selected regulatory reference wording"
    instructions = "Reduce dose to 50% for hepatic impairment cohort."

    decision = ReviewerDecision(
        target_content_id="sec_003_det",
        candidate_id="cand_003_det",
        decision=ReviewDecisionType.ADAPT,
        reviewer_name="Dr. Lead Reviewer",
        reviewer_notes="Adapt reference.",
        adaptation_instructions=instructions,
    )

    proposal = agent.formulate_change_proposal(
        decision=decision,
        section="Dosage and Administration",
        original_text=original_text,
        candidate_text=candidate_text,
    )

    assert proposal is not None
    assert proposal.proposed_text == f"{candidate_text} [Adapted per clinical instructions: {instructions}]"
    assert proposal.proposed_text != original_text
    assert candidate_text in proposal.proposed_text


# ==============================================================================
# TEST 4 — ADAPT without candidate reference
# ==============================================================================

def test_adapt_without_candidate_reference_raises_controlled_error(change_agent):
    """TEST 4: ADAPT without candidate reference text must fail with controlled error and NEVER adapt original text."""
    original_text = "Original regulatory wording"

    decision = ReviewerDecision(
        target_content_id="sec_004",
        candidate_id="cand_004",
        decision=ReviewDecisionType.ADAPT,
        reviewer_name="Dr. Lead Reviewer",
        reviewer_notes="Attempted adapt without reference.",
        adaptation_instructions="Reduce dose to 50%.",
    )

    # Empty string
    with pytest.raises(ValueError, match="Candidate reference text is required"):
        change_agent.formulate_change_proposal(
            decision=decision,
            section="Dosage and Administration",
            original_text=original_text,
            candidate_text="",
        )

    # None / omitted
    with pytest.raises(ValueError, match="Candidate reference text is required"):
        change_agent.formulate_change_proposal(
            decision=decision,
            section="Dosage and Administration",
            original_text=original_text,
            candidate_text=None,
        )


# ==============================================================================
# TEST 5 — Candidate structure propagation
# ==============================================================================

def test_candidate_structure_propagation():
    """TEST 5: ComparisonCandidate structure (content_item.text) extracts actual reference text."""
    ref_text = "Selected regulatory reference wording"
    content_item = RegulatoryContentItem(
        content_id="rc_test_500",
        source="DailyMed",
        document_name="DailyMed Approved Label",
        section="Dosage and Administration",
        text=ref_text,
    )

    comp_cand = ComparisonCandidate(
        candidate_id="cand_rc_test_500",
        content_item=content_item,
    )

    # Verify model structure
    assert hasattr(comp_cand, "content_item")
    assert comp_cand.content_item.text == ref_text

    # Emulate the updated frontend selection logic:
    # const underlying = comp.content_item || comp.candidate || comp;
    # const text = underlying.text || comp.content_item?.text || '';
    underlying = getattr(comp_cand, "content_item", None) or getattr(comp_cand, "candidate", None) or comp_cand
    extracted_text = getattr(underlying, "text", None) or getattr(getattr(comp_cand, "content_item", None), "text", "")

    assert extracted_text == "Selected regulatory reference wording"
    assert extracted_text != ""


# ==============================================================================
# TEST 6 — Backend candidate_id fallback
# ==============================================================================

def test_backend_candidate_id_fallback_resolves_store(client):
    """TEST 6: POST /changes/analyze resolves candidate text from candidate store when payload.candidate_text is missing."""
    store = get_candidate_store()

    # 1. Register candidate item in candidate store
    cand_item_id = "chunk_ref_test_06"
    cand_text = "Authoritative DailyMed reference text for pediatric indication."
    candidate_item = RegulatoryContentItem(
        content_id=cand_item_id,
        source="DailyMed",
        document_name="Tylenol Reference Package Insert",
        section="Indications",
        text=cand_text,
    )
    store._content_items[cand_item_id] = candidate_item

    # 2. Record human decision with candidate_id
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": "sec_draft_06",
            "candidate_id": cand_item_id,
            "decision": "REUSE",
            "reviewer_name": "Dr. Sarah Regulatory",
            "reviewer_notes": "Adopt precedent from DailyMed.",
        },
    )
    assert res_dec.status_code == 200, res_dec.text
    dec_id = res_dec.json()["decision_id"]

    # 3. Formulate proposal WITHOUT candidate_text in payload
    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": dec_id,
            "section": "Indications",
            "original_text": "Draft draft draft unapproved phrasing.",
            "candidate_text": None,  # OMITTED / NULL
        },
    )
    assert res_prop.status_code == 200, res_prop.text
    prop_data = res_prop.json()

    # 4. Verify candidate text was resolved from candidate store
    assert prop_data["proposed_text"] == cand_text
    assert prop_data["original_text"] == "Draft draft draft unapproved phrasing."
    assert prop_data["proposed_text"] != prop_data["original_text"]


def test_backend_missing_candidate_fails_controlled(client):
    """POST /changes/analyze returns HTTP 400 when candidate text is missing and unresolvable."""
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": "sec_draft_07",
            "candidate_id": "nonexistent_cand_999",
            "decision": "REUSE",
            "reviewer_name": "Dr. Sarah Regulatory",
            "reviewer_notes": "Missing reference item.",
        },
    )
    assert res_dec.status_code == 200, res_dec.text
    dec_id = res_dec.json()["decision_id"]

    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": dec_id,
            "section": "Indications",
            "original_text": "Draft text baseline.",
            "candidate_text": None,
        },
    )
    # Must fail with controlled 400 error, never silently return original_text as proposed_text
    assert res_prop.status_code == 400
    assert "Candidate reference text is required for a REUSE decision" in res_prop.json()["detail"]
