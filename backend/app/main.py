"""FastAPI main application entrypoint for Regulatory Content Reuse Finder.

Provides core routing, CORS configuration, centralized error handling,
and source health verification.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.routes.comparison import router as comparison_router
from app.routes.document_review import router as document_review_router
from app.routes.regulatory import router as regulatory_router
from app.services.regulatory_source import RegulatorySourceService

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("regulatory_reuse_finder")

app = FastAPI(
    title="Regulatory Content Reuse Finder API",
    description=(
        "AI-assisted Life Sciences regulatory platform for content reuse, candidate comparison, "
        "evidence traceability, and controlled document changes with human-in-the-loop governance."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for React frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Safe Global Exception Handler ensuring secrets are never leaked in stack traces
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log securely on backend
    logger.error("Unhandled exception processing %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected server error occurred while processing the regulatory request.",
            "path": request.url.path,
        },
    )


# Health check endpoint
@app.get(
    "/health",
    summary="Application Health Check",
    tags=["Health & Status"],
)
async def health_check() -> Dict[str, Any]:
    """Verify backend status, live regulatory source availability, and configuration."""
    sources_service = RegulatorySourceService()
    sources_health = await sources_service.check_all_sources_health()

    return {
        "status": "healthy",
        "service": "Regulatory Content Reuse Finder",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "openai_configured": settings.has_openai_configured,
        "openfda_key_configured": settings.has_openfda_key_configured,
        "sources": sources_health.get("sources", {}),
    }


# Include functional routers
app.include_router(regulatory_router)
app.include_router(comparison_router)
app.include_router(document_review_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True,
    )
