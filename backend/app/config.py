"""Application configuration module using Pydantic Settings.

Reads configuration from environment variables and .env files safely.
Ensures API keys are never exposed or printed.
"""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with strong validation and defaults."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment and Server
    ENVIRONMENT: str = Field(default="development", description="Runtime environment")
    BACKEND_HOST: str = Field(default="127.0.0.1", description="Backend host")
    BACKEND_PORT: int = Field(default=8000, description="Backend port")
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
        description="Comma-separated allowed CORS origins",
    )

    # Live External Regulatory Sources
    DAILYMED_BASE_URL: str = Field(
        default="https://dailymed.nlm.nih.gov/dailymed/services/v2",
        description="Base URL for NLM DailyMed Web Services",
    )
    OPENFDA_BASE_URL: str = Field(
        default="https://api.fda.gov/drug/label.json",
        description="Base URL for openFDA drug label endpoint",
    )
    REQUEST_TIMEOUT_SECONDS: float = Field(
        default=15.0,
        description="Timeout for external regulatory service HTTP requests in seconds",
    )

    # API Keys (Backend-only, never exposed to frontend)
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenAI API key for LLM agents (strictly backend-only)",
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4o-mini",
        description="Primary OpenAI chat model for Agent 1 regulatory analysis",
    )
    OPENAI_EMBEDDING_MODEL: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model for semantic candidate representation",
    )
    SIMILARITY_THRESHOLD: float = Field(
        default=0.35,
        description="Retrieval-only candidate similarity threshold (never determines reuse decision)",
    )
    TOP_K_CANDIDATES: int = Field(
        default=5,
        description="Maximum number of candidate records to retrieve for Agent 1 review",
    )
    OPENFDA_API_KEY: Optional[str] = Field(
        default=None,
        description="Optional openFDA API key for increased rate limits",
    )

    # LangSmith / Observability
    LANGSMITH_API_KEY: Optional[str] = Field(
        default=None,
        description="LangSmith API key for tracing/evaluations",
    )
    LANGSMITH_TRACING: bool = Field(
        default=False,
        description="Enable LangSmith tracing",
    )
    LANGSMITH_PROJECT: str = Field(
        default="regulatory-content-reuse-finder",
        description="LangSmith project name",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        """Parse CORS origins string into a list of sanitized origins."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def has_openai_configured(self) -> bool:
        """Check if an OpenAI API key is configured without exposing it."""
        return bool(self.OPENAI_API_KEY and len(self.OPENAI_API_KEY.strip()) > 5)

    @property
    def has_openfda_key_configured(self) -> bool:
        """Check if an openFDA key is configured without exposing it."""
        return bool(self.OPENFDA_API_KEY and len(self.OPENFDA_API_KEY.strip()) > 5)


# Global settings instance
settings = Settings()
