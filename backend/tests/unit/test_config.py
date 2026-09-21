"""Unit tests for configuration loading and security masking."""

from app.config import Settings


def test_settings_defaults():
    """Verify default configurations are populated correctly."""
    cfg = Settings(
        ENVIRONMENT="test",
        OPENAI_API_KEY=None,
        OPENFDA_API_KEY=None,
    )
    assert cfg.ENVIRONMENT == "test"
    assert cfg.BACKEND_PORT == 8000
    assert "https://dailymed.nlm.nih.gov" in cfg.DAILYMED_BASE_URL
    assert "https://api.fda.gov" in cfg.OPENFDA_BASE_URL
    assert cfg.REQUEST_TIMEOUT_SECONDS == 15.0
    assert cfg.has_openai_configured is False
    assert cfg.has_openfda_key_configured is False


def test_cors_origin_parsing():
    """Verify CORS origins are parsed cleanly into a list."""
    cfg = Settings(CORS_ORIGINS="http://localhost:3000, https://app.example.com , ")
    origins = cfg.cors_origin_list
    assert "http://localhost:3000" in origins
    assert "https://app.example.com" in origins
    assert len(origins) == 2


def test_api_key_detection():
    """Verify API key presence detection without exposing key content."""
    cfg_with_key = Settings(OPENAI_API_KEY="sk-proj-test123456789")
    assert cfg_with_key.has_openai_configured is True

    cfg_without_key = Settings(OPENAI_API_KEY="")
    assert cfg_without_key.has_openai_configured is False
