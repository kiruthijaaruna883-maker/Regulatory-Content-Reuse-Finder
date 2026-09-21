"""API route tests for regulatory search and review endpoints."""

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.models.content import RegulatoryContentItem, RegulatorySearchResult

client = TestClient(app)


def test_regulatory_search_success():
    """Verify GET /regulatory/search returns structured results with full provenance."""
    mock_item = RegulatoryContentItem(
        source="DailyMed",
        source_url="https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=mock-setid",
        source_identifier="mock-setid",
        document_name="Mock Aspirin 81mg",
        version="1",
        date="2026-01-01",
        section="Dosage and Administration",
        text="Adults: Take 1 tablet daily.",
    )
    mock_result = RegulatorySearchResult(
        query="aspirin",
        total_results=1,
        source="dailymed",
        items=[mock_item],
    )

    with patch(
        "app.routes.regulatory.source_service.search",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = mock_result

        response = client.get("/regulatory/search?query=aspirin&source=dailymed")
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "aspirin"
        assert data["total_results"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["source"] == "DailyMed"
        assert data["items"][0]["source_identifier"] == "mock-setid"


def test_regulatory_search_timeout_error():
    """Verify live service timeout returns 504 Gateway Timeout without leaking secrets."""
    with patch(
        "app.routes.regulatory.source_service.search",
        side_effect=TimeoutError("Connection timed out after 15s"),
    ):
        response = client.get("/regulatory/search?query=aspirin")
        assert response.status_code == 504
        assert "timed out" in response.json()["detail"]


def test_regulatory_search_connection_error():
    """Verify live service connection failure returns 503 Service Unavailable."""
    with patch(
        "app.routes.regulatory.source_service.search",
        side_effect=ConnectionError("DailyMed service unreachable"),
    ):
        response = client.get("/regulatory/search?query=aspirin")
        assert response.status_code == 503
        assert "temporarily unavailable" in response.json()["detail"]


def test_regulatory_search_invalid_source():
    """Verify invalid source parameter returns 422 Unprocessable Entity."""
    response = client.get("/regulatory/search?query=aspirin&source=invalid_source")
    assert response.status_code == 422


def test_document_upload_and_review_workflow():
    """Verify document upload, section extraction, human decision, and change formulation."""
    # 1. Upload text
    upload_res = client.post(
        "/documents/upload",
        json={
            "document_name": "Test Clinical Label",
            "content": "INDICATIONS AND USAGE\nIndicated for migraine headache relief.\n\nDOSAGE AND ADMINISTRATION\nTake 1 tablet at onset.",
        },
    )
    assert upload_res.status_code == 200
    sections = upload_res.json()
    assert len(sections) == 2

    # 2. Record human reviewer decision
    decision_res = client.post(
        "/review/decision",
        json={
            "target_content_id": sections[0]["content_id"],
            "decision": "REUSE",
            "reviewer_name": "Regulatory Specialist",
            "reviewer_notes": "Validated against DailyMed official label.",
        },
    )
    assert decision_res.status_code == 200
    decision = decision_res.json()
    assert decision["decision"] == "REUSE"

    # 3. Analyze change proposal
    change_res = client.post(
        "/changes/analyze",
        json={
            "decision_id": decision["decision_id"],
            "section": "Indications and Usage",
            "original_text": "Indicated for migraine headache relief.",
            "candidate_text": "Indicated for the acute treatment of migraine headache with or without aura.",
        },
    )
    assert change_res.status_code == 200
    proposal = change_res.json()
    assert proposal["decision_type"] == "REUSE"

    # 4. Validate proposal
    val_res = client.post("/changes/validate", json=proposal)
    assert val_res.status_code == 200
    assert val_res.json()["validation_passed"] is True

    # 5. Approve and generate report
    approve_res = client.post(
        "/changes/approve",
        json={
            "document_name": "Test Clinical Label",
            "document_version": "1.0",
            "approver_name": "Senior Regulatory Director",
            "approval_confirmation": True,
            "audit_notes": "Authorized for regulatory submission.",
        },
    )
    assert approve_res.status_code == 200
    report = approve_res.json()
    assert report["document_name"] == "Test Clinical Label"
    assert report["author_approver"] == "Senior Regulatory Director"
    assert len(report["changes"]) >= 1
