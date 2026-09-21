"""API route tests for /health endpoint."""

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify GET /health returns 200 OK and expected structure."""
    with patch(
        "app.services.regulatory_source.RegulatorySourceService.check_all_sources_health",
        new_callable=AsyncMock,
    ) as mock_health:
        mock_health.return_value = {
            "overall_status": "healthy",
            "sources": {
                "dailymed": {"status": "healthy", "status_code": 200},
                "openfda": {"status": "healthy", "status_code": 200},
            },
        }

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Regulatory Content Reuse Finder"
        assert data["version"] == "1.0.0"
        assert "timestamp" in data
        assert "sources" in data
        assert data["sources"]["dailymed"]["status"] == "healthy"
