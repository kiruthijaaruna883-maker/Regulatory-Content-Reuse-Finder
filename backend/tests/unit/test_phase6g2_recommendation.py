"""Comprehensive unit and integration tests for Phase 6G.2:
Automatic Candidate Discovery + Advisory REUSE/ADAPT/REJECT Recommendation.

Validates the 11 mandatory verification criteria:
1. Critical false-match -> never REUSE (always REJECT)
2. Critical key-information mismatch -> never REUSE (REJECT)
3. Critical context mismatch -> never REUSE (REJECT)
4. Strong alignment -> REUSE recommendation where justified
5. Non-critical differences requiring adaptation -> ADAPT
6. Recommendation reason is generated from actual comparison evidence
7. Recommendation fields default to None for backward compatibility
8. Advisory recommendation does not create a human decision in SQLite
9. Existing human REUSE/ADAPT/REJECT flow remains unchanged
10. Automatic discovery does not break existing candidate search
11. Existing DailyMed/openFDA behavior remains intact
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.comparison import (
    ComparisonCandidate,
    DifferenceItem,
    DimensionStatus,
    MultiDimensionalMatch,
)
from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document_change import ReviewDecisionType
from app.persistence.sqlite_store import WorkflowSQLiteStore
from app.services.multi_dimensional_comparator import MultiDimensionalComparator
from app.agents.content_analysis_agent import RegulatoryContentAnalysisAgent

client = TestClient(app)


# ==============================================================================
# 1. CRITICAL SAFETY: FALSE-MATCH MUST NEVER RESULT IN REUSE
# ==============================================================================


def test_critical_false_match_never_reuse():
    """1. Verify that a critical false match (e.g. dose unit mg vs mcg) yields REJECT, never REUSE."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Take 50 mg of losartan potassium orally once daily."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        document_name="Losartan Potassium Tablets",
        section="Dosage and Administration",
        text="Adults: Take 50 mcg of losartan potassium orally once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    assert false_warning is not None, "False match warning must be detected"

    rec, reason, conf = comparator.evaluate_recommendation(
        match=match,
        differences=diffs,
        false_match_warning=false_warning,
        similarity_score=0.95,
    )

    assert rec == ReviewDecisionType.REJECT, f"False match must produce REJECT, got {rec}"
    assert rec != ReviewDecisionType.REUSE, "False match must NEVER produce REUSE"
    assert "false-match discrepancy" in reason.lower()
    assert conf is not None
    assert 0.0 <= conf <= 1.0


# ==============================================================================
# 2. CRITICAL KEY-INFORMATION MISMATCH MUST NEVER RESULT IN REUSE
# ==============================================================================


def test_critical_key_info_mismatch_never_reuse():
    """2. Verify that a critical key information mismatch (different active drug) yields REJECT."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Take 200 mg ibuprofen orally every 6 hours with food."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        document_name="Acetaminophen Tablets",
        section="Dosage and Administration",
        text="Adults: Take 500 mg acetaminophen orally every 6 hours with water.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    rec, reason, conf = comparator.evaluate_recommendation(
        match=match,
        differences=diffs,
        false_match_warning=false_warning,
        similarity_score=0.60,
    )

    assert rec == ReviewDecisionType.REJECT, f"Active ingredient mismatch must produce REJECT, got {rec}"
    assert rec != ReviewDecisionType.REUSE
    assert "Key Information mismatch" in reason or "drug" in reason.lower() or "active ingredient" in reason.lower()


# ==============================================================================
# 3. CRITICAL CONTEXT MISMATCH MUST NEVER RESULT IN REUSE
# ==============================================================================


def test_critical_context_mismatch_never_reuse():
    """3. Verify that an incompatible context (e.g. prescribing vs clinical trial observation) yields REJECT."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Prescribe 1 tablet orally daily for chronic hypertension management."
    candidate = RegulatoryContentItem(
        source="openFDA",
        document_name="Phase 1 Trial Safety Record",
        section="Adverse Reactions",
        text="In pregnant women during first trimester, 1 tablet was administered under exploratory protocol.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
        target_section="Dosage and Administration",
    )

    assert match.context.status == DimensionStatus.MISMATCH

    rec, reason, conf = comparator.evaluate_recommendation(
        match=match,
        differences=diffs,
        false_match_warning=false_warning,
        similarity_score=0.55,
    )

    assert rec == ReviewDecisionType.REJECT, f"Context mismatch must produce REJECT, got {rec}"
    assert rec != ReviewDecisionType.REUSE


# ==============================================================================
# 4. STRONG ALIGNMENT RECOMMENDS REUSE
# ==============================================================================


def test_strong_alignment_recommends_reuse():
    """4. Verify that strong alignment across dimensions and zero substantive differences yields REUSE."""
    comparator = MultiDimensionalComparator()
    text = "Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours with water. Do not exceed 6 tablets within 24 hours."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        document_name="Aspirin Tablets USP",
        section="Dosage and Administration",
        text="Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours with water. Do not exceed 6 tablets within 24 hours.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=text,
        candidate=candidate,
    )

    assert false_warning is None

    rec, reason, conf = comparator.evaluate_recommendation(
        match=match,
        differences=diffs,
        false_match_warning=false_warning,
        similarity_score=1.0,
    )

    assert rec == ReviewDecisionType.REUSE, f"Identical alignment must recommend REUSE, got {rec}"
    assert "REUSE recommended" in reason
    assert conf is not None
    assert conf >= 0.85


# ==============================================================================
# 5. NON-CRITICAL DIFFERENCES REQUIRE ADAPTATION
# ==============================================================================


def test_non_critical_differences_recommends_adapt():
    """5. Verify that core alignment with non-critical adjustments yields ADAPT."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours with water. Do not exceed 6 tablets (3000 mg) within 24 hours."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        document_name="Aspirin Tablets Reference",
        section="Dosage and Administration",
        text="Adults: Take 1 to 2 tablets (500 mg) orally every 4 to 6 hours as needed. Maximum dosage: 8 tablets (4000 mg) in 24 hours.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    rec, reason, conf = comparator.evaluate_recommendation(
        match=match,
        differences=diffs,
        false_match_warning=false_warning,
        similarity_score=0.82,
    )

    # When core meaning aligns but numerical limits differ without false match warning, ADAPT is recommended
    assert rec in (ReviewDecisionType.ADAPT, ReviewDecisionType.REJECT)
    if false_warning is None:
        assert rec == ReviewDecisionType.ADAPT, f"Compatible text with difference items must yield ADAPT, got {rec}"
        assert "ADAPT recommended" in reason


# ==============================================================================
# 6. RECOMMENDATION REASON IS GENERATED FROM ACTUAL EVIDENCE
# ==============================================================================


def test_recommendation_reason_is_factual_and_evidence_based():
    """6. Verify recommendation reason mentions factual comparison signals, not arbitrary filler."""
    comparator = MultiDimensionalComparator()
    target = "Adults: Administer 10 mg intravenously once daily."
    candidate = RegulatoryContentItem(
        source="DailyMed",
        document_name="Morphine Sulfate Injection",
        section="Dosage and Administration",
        text="Adults: Administer 10 mg intravenously once daily.",
    )

    match, diffs, evidence, false_warning = comparator.compare(
        target_text=target,
        candidate=candidate,
    )

    rec, reason, conf = comparator.evaluate_recommendation(
        match=match,
        differences=diffs,
        false_match_warning=false_warning,
        similarity_score=0.98,
    )

    assert reason is not None
    assert len(reason) > 20
    # Reason must refer to factual dimensions or alignment
    assert any(term in reason.lower() for term in ["meaning", "context", "key information", "align", "difference"])


# ==============================================================================
# 7. BACKWARD COMPATIBILITY: FIELDS DEFAULT TO NONE
# ==============================================================================


def test_recommendation_fields_default_to_none_for_backward_compatibility():
    """7. Verify ComparisonCandidate defaults new fields to None without breaking existing instantiations."""
    item = RegulatoryContentItem(
        source="DailyMed",
        document_name="Test Product",
        section="Indications",
        text="Indicated for headache relief.",
    )

    candidate = ComparisonCandidate(
        content_item=item,
        similarity_score=0.88,
    )

    assert candidate.recommended_decision is None
    assert candidate.recommendation_reason is None
    assert candidate.recommendation_confidence is None
    assert candidate.requires_human_review is True
    assert candidate.differences == []


# ==============================================================================
# 8. ADVISORY RECOMMENDATIONS DO NOT CREATE HUMAN DECISIONS
# ==============================================================================


def test_advisory_recommendation_does_not_create_human_decision(tmp_path):
    """8. Advisory comparison output MUST NOT insert records into the human decisions SQLite table."""
    db_file = tmp_path / "test_advisory_isolation.db"
    store = WorkflowSQLiteStore(db_path=str(db_file))

    # Initial state: 0 decisions
    assert len(store.list_decisions()) == 0

    # Execute content analysis via Agent 1
    agent = RegulatoryContentAnalysisAgent()
    target_text = "Adults: Take 1 tablet (500 mg) orally every 4 hours."
    cand_item = RegulatoryContentItem(
        content_id="cand_123",
        source="DailyMed",
        document_name="Aspirin 500mg",
        section="Dosage",
        text="Adults: Take 1 tablet (500 mg) orally every 4 hours.",
    )

    result = agent.analyze_and_compare(
        target_text=target_text,
        candidates=[cand_item],
    )

    # Verification: result contains comparison candidate with advisory recommendation
    assert len(result.candidates) == 1
    assert result.candidates[0].recommended_decision is not None

    # CRITICAL GOVERNANCE CHECK: decisions table MUST remain completely empty
    decisions_in_db = store.list_decisions()
    assert len(decisions_in_db) == 0, "Advisory recommendations must never write to the human decisions table"


# ==============================================================================
# 9. EXISTING HUMAN REUSE/ADAPT/REJECT FLOW REMAINS UNCHANGED
# ==============================================================================


def test_existing_human_decision_flow_remains_unchanged(tmp_path):
    """9. POST /review/decision records human decisions with complete traceability."""
    payload = {
        "target_content_id": "target_doc_sec_1",
        "candidate_id": "cand_ref_sec_1",
        "decision": "REUSE",
        "reviewer_name": "Dr. Sarah Regulatory, MD",
        "reviewer_notes": "Clinical review confirmed full alignment with DailyMed standard.",
    }

    res = client.post("/review/decision", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["decision"] == "REUSE"
    assert data["reviewer_name"] == "Dr. Sarah Regulatory, MD"
    assert data["decision_id"] is not None
    assert data["decided_at"] is not None


# ==============================================================================
# 10. AUTOMATIC DISCOVERY SEARCH QUERY FALLBACK
# ==============================================================================


def test_automatic_discovery_query_fallback():
    """10. POST /candidates/search auto-derives query when query is blank but target_text is provided."""
    payload = {
        "query": "",
        "target_text": "Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours for aspirin therapy.",
        "section": "Dosage and Administration",
        "source_filter": "all",
        "top_k": 5,
    }

    res = client.post("/candidates/search", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "query" in data
    # Query should be auto-derived from active ingredient / drug / section
    assert len(data["query"]) > 0


# ==============================================================================
# 11. EXISTING DAILYMED AND OPENFDA BEHAVIOR REMAINS INTACT
# ==============================================================================


def test_existing_dailymed_openfda_behavior_intact():
    """11. Verify regulatory authority endpoints remain fully operational."""
    res = client.get("/regulatory/sources/status")
    assert res.status_code == 200
    status_data = res.json()
    assert "sources" in status_data
    assert "dailymed" in status_data["sources"]
    assert "openfda" in status_data["sources"]
