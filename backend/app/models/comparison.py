"""Pydantic data models for multi-dimensional content comparison, structured evidence,
deterministic differences, and false-match protection.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4
from pydantic import BaseModel, Field
from app.models.content import KeyInformation, RegulatoryContentItem


class DimensionStatus(str, Enum):
    """Categorical status for dimension alignment."""

    MATCH = "MATCH"
    PARTIAL = "PARTIAL"
    MISMATCH = "MISMATCH"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DimensionEvaluation(BaseModel):
    """Evaluation result for one of the six regulatory comparison dimensions."""

    dimension: str = Field(
        ...,
        description="Dimension evaluated: meaning, template, context, structure, format, or key_information",
    )
    status: DimensionStatus = Field(
        ...,
        description="Categorical alignment: MATCH, PARTIAL, MISMATCH, NOT_APPLICABLE",
    )
    score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional dimensional alignment score between 0.0 and 1.0",
    )
    details: str = Field(
        ...,
        description="Factual and reasoned analysis of alignment or distinction for this dimension",
    )
    observed_from_source: Optional[str] = Field(
        default=None,
        description="Directly supported facts observed from external regulatory source",
    )
    model_interpretation: Optional[str] = Field(
        default=None,
        description="Model or algorithmic reasoning grounded in observed source facts",
    )


class MultiDimensionalMatch(BaseModel):
    """Rigorous six-dimensional comparison breakdown.

    Prevents reliance on raw semantic similarity alone.
    """

    meaning: DimensionEvaluation = Field(..., description="Semantic alignment of regulatory directives")
    template: DimensionEvaluation = Field(..., description="Regulatory statement pattern and clinical template structure")
    context: DimensionEvaluation = Field(..., description="Operational setting, therapeutic context, and regulatory purpose")
    structure: DimensionEvaluation = Field(..., description="Structural entity: section, subsection, table, bullet, etc.")
    format: DimensionEvaluation = Field(..., description="Format typology: sentence, numerical, table cell, narrative")
    key_information: DimensionEvaluation = Field(..., description="Exact attribute comparisons: dose, route, population, drug")
    overall_alignment_summary: str = Field(..., description="Synthesized multi-dimensional summary")


class DifferenceItem(BaseModel):
    """Structured deterministic difference between current text and candidate regulatory record.

    No arbitrary severity scores (Critical/Major/Minor) are assigned in Phase 2.
    """

    difference_id: str = Field(
        default_factory=lambda: f"diff_{uuid4().hex[:8]}",
        description="Unique identifier for the difference entry",
    )
    attribute: str = Field(
        default="general",
        description="Attribute or aspect affected (e.g. 'dose', 'frequency', 'population', 'drug', 'route', 'format', 'key_information')",
    )
    current_value: Optional[str] = Field(
        default=None,
        description="Content as present in current internal draft",
    )
    candidate_value: Optional[str] = Field(
        default=None,
        description="Content as present in external regulatory reference",
    )
    explanation: str = Field(
        ...,
        description="Clear factual explanation of the observed distinction",
    )
    reviewer_attention_required: bool = Field(
        default=True,
        description="Flag indicating human regulatory professional attention is required",
    )
    # Backward compatibility alias for Phase 1 tests
    aspect: Optional[str] = Field(
        default=None,
        description="Legacy alias for attribute",
    )
    difference_type: Optional[str] = Field(
        default="modification",
        description="Legacy categorization: 'addition', 'deletion', 'modification', 'equivalent', or 'structural'",
    )
    regulatory_impact: Optional[str] = Field(
        default=None,
        description="Legacy impact field (kept for backward compatibility with Phase 1 tests only)",
    )

    from pydantic import model_validator

    @model_validator(mode="before")
    @classmethod
    def sync_aspect_and_attribute(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "aspect" in data and ("attribute" not in data or not data.get("attribute")):
                data["attribute"] = data["aspect"]
            elif "attribute" in data and ("aspect" not in data or not data.get("aspect")):
                data["aspect"] = data["attribute"]
        return data


class ObservedSourceFacts(BaseModel):
    """Direct, auditable facts observed from the authoritative regulatory source.

    Never mixed with AI model interpretations.
    """

    source: str = Field(..., description="Regulatory source (DailyMed, openFDA)")
    source_url: Optional[str] = Field(default=None, description="Official live URL for traceability")
    source_identifier: Optional[str] = Field(default=None, description="Set ID, SPL ID, or record ID")
    document_name: Optional[str] = Field(default=None, description="Official document or drug label title")
    version: Optional[str] = Field(default=None, description="SPL version or document revision number")
    date: Optional[str] = Field(default=None, description="Publication, approval, or effective date")
    section: Optional[str] = Field(default=None, description="Regulatory section heading")
    location: Optional[str] = Field(
        default=None,
        description="Page, paragraph, table, or section location when available (NOT LOINC code)",
    )
    loinc_code: Optional[str] = Field(
        default=None,
        description="Standard LOINC section code when provided by regulatory source",
    )
    exact_quote: Optional[str] = Field(default=None, description="Exact cited regulatory text")
    extracted_drug: Optional[str] = Field(default=None, description="Drug or substance observed in source")
    extracted_dose: Optional[str] = Field(default=None, description="Dose observed in source")
    extracted_population: Optional[str] = Field(default=None, description="Target population observed in source")
    extracted_indication: Optional[str] = Field(default=None, description="Indication observed in source")


class ModelReasoning(BaseModel):
    """AI / Algorithmic reasoning grounded strictly in observed source facts."""

    similarity_rationale: str = Field(..., description="Factual rationale explaining why content appears similar")
    difference_rationale: str = Field(..., description="Factual rationale explaining observed differences")
    adaptation_guidance: Optional[str] = Field(default=None, description="Specific attributes requiring reviewer adaptation")
    false_match_rationale: Optional[str] = Field(default=None, description="Rationale for false-match warnings if detected")


class StructuredEvidence(BaseModel):
    """Two-tier evidence model keeping source facts strictly separate from model interpretation."""

    trace_id: str = Field(
        default_factory=lambda: f"tr_{uuid4().hex[:8]}",
        description="Evidence trace identifier",
    )
    observed_from_source: ObservedSourceFacts = Field(..., description="Direct facts verified in source")
    model_interpretation: ModelReasoning = Field(..., description="Reasoning grounded in observed facts")


# Kept for backward compatibility with Phase 1 tests
class EvidenceTrace(BaseModel):
    """Legacy evidence link for backward compatibility."""

    trace_id: str = Field(default_factory=lambda: f"tr_{uuid4().hex[:8]}")
    source: str
    source_url: Optional[str] = None
    source_identifier: Optional[str] = None
    document_name: Optional[str] = None
    section: Optional[str] = None
    location: Optional[str] = None
    loinc_code: Optional[str] = None
    exact_quote: Optional[str] = None


class ComparisonCandidate(BaseModel):
    """Candidate regulatory content item evaluated against target content."""

    candidate_id: str = Field(
        default_factory=lambda: f"cand_{uuid4().hex[:8]}",
        description="Candidate identifier",
    )
    content_item: RegulatoryContentItem = Field(..., description="Referenced regulatory content item")
    similarity_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Vector or lexical retrieval score (retrieval-only; never determines reuse decision)",
    )
    embedding_provider: str = Field(
        default="openai",
        description="Provider used: 'openai' or 'fallback_deterministic' (limited test/dev fallback)",
    )
    multi_dimensional_match: Optional[MultiDimensionalMatch] = Field(
        default=None,
        description="6-dimensional comparison evaluation breakdown",
    )
    matched_aspects: List[str] = Field(
        default_factory=list,
        description="Aspects with strong alignment",
    )
    differences: List[DifferenceItem] = Field(
        default_factory=list,
        description="Structured deterministic differences",
    )
    evidence: List[Union[StructuredEvidence, EvidenceTrace]] = Field(
        default_factory=list,
        description="Structured evidence records grounding this candidate",
    )
    false_match_warning: Optional[str] = Field(
        default=None,
        description="Warning when high similarity masks critical regulatory mismatches (drug, population, context)",
    )
    requires_human_review: bool = Field(
        default=True,
        description="Enforces human regulatory professional final decision requirement",
    )


class ContentComparisonResult(BaseModel):
    """Aggregate result from comparing target regulatory content against candidates."""

    comparison_id: str = Field(
        default_factory=lambda: f"comp_{uuid4().hex[:10]}",
        description="Unique comparison session ID",
    )
    target_section: Optional[str] = Field(default=None, description="Section of the target document")
    target_text: str = Field(..., description="Original current document text being reviewed")
    target_key_information: Optional[KeyInformation] = Field(
        default=None,
        description="Key entities extracted from target text",
    )
    candidates: List[ComparisonCandidate] = Field(
        default_factory=list,
        description="List of candidate reusable regulatory items",
    )
    summary_explanation: Optional[str] = Field(
        default=None,
        description="Explanatory overview of candidates and multi-dimensional analysis",
    )
    false_matches_detected: int = Field(
        default=0,
        description="Count of candidates where critical false-match discrepancies were detected",
    )
