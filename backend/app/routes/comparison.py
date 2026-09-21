"""Content analysis and comparison routes module."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.agents.content_analysis_agent import RegulatoryContentAnalysisAgent
from app.models.comparison import ContentComparisonResult, DifferenceItem
from app.models.content import RegulatoryContentItem
from app.services.difference_detection import DifferenceDetectionService

router = APIRouter(prefix="/content", tags=["Content Analysis & Comparison"])

analysis_agent = RegulatoryContentAnalysisAgent()
differ_service = DifferenceDetectionService()


class AnalyzeRequest(BaseModel):
    """Payload to trigger Agent 1 content analysis."""
    target_text: str = Field(..., min_length=5, description="Target document content snippet")
    section_name: Optional[str] = Field(None, description="Section heading")
    candidates: List[RegulatoryContentItem] = Field(default_factory=list, description="Retrieved candidates")
    retrieve_live: bool = Field(default=False, description="Trigger on-demand live RAG retrieval if candidates are not provided")
    source_filter: str = Field(default="all", description="Live source filter: 'all', 'dailymed', or 'openfda'")
    top_k: Optional[int] = Field(default=None, description="Max candidates to retrieve")


class ComparePairRequest(BaseModel):
    """Payload to compare two distinct regulatory texts."""
    current_text: str = Field(..., min_length=1, description="Current internal text")
    candidate_text: str = Field(..., min_length=1, description="External candidate text")


@router.post("/analyze", response_model=ContentComparisonResult, summary="Analyze candidate alignment with Agent 1")
async def analyze_candidates(payload: AnalyzeRequest) -> ContentComparisonResult:
    """Evaluate candidate items against target content, rank by similarity, and detect differences."""
    try:
        if payload.candidates:
            return analysis_agent.analyze_and_compare(
                target_text=payload.target_text,
                candidates=payload.candidates,
                section_name=payload.section_name,
            )
        else:
            # On-demand live RAG retrieval and analysis
            return await analysis_agent.analyze_and_retrieve(
                target_text=payload.target_text,
                section_name=payload.section_name,
                source_filter=payload.source_filter,
                top_k=payload.top_k,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content analysis failed: {exc}",
        )


@router.post("/compare", response_model=List[DifferenceItem], summary="Detect differences between two regulatory passages")
async def compare_texts(payload: ComparePairRequest) -> List[DifferenceItem]:
    """Compute structured differences across numerical, phrasing, and structural aspects."""
    try:
        return differ_service.analyze_differences(
            current_text=payload.current_text,
            candidate_text=payload.candidate_text,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Comparison failed: {exc}",
        )
