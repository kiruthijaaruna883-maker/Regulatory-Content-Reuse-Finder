"""Domain data models for regulatory content, comparison, and controlled change."""

from app.models.content import (
    KeyInformation,
    RegulatoryContentItem,
    RegulatoryContentType,
    RegulatorySearchRequest,
    RegulatorySearchResult,
)
from app.models.comparison import (
    ComparisonCandidate,
    DifferenceItem,
    DimensionEvaluation,
    DimensionStatus,
    EvidenceTrace,
    ModelReasoning,
    MultiDimensionalMatch,
    ObservedSourceFacts,
    StructuredEvidence,
    ContentComparisonResult,
)
from app.models.document_change import (
    ApprovedChangeReport,
    ChangeImpact,
    ProposedChange,
    RelatedOccurrence,
    ReviewDecisionType,
    ReviewerDecision,
    ValidationFinding,
)

__all__ = [
    "KeyInformation",
    "RegulatoryContentItem",
    "RegulatoryContentType",
    "RegulatorySearchRequest",
    "RegulatorySearchResult",
    "ComparisonCandidate",
    "DifferenceItem",
    "DimensionEvaluation",
    "DimensionStatus",
    "EvidenceTrace",
    "ModelReasoning",
    "MultiDimensionalMatch",
    "ObservedSourceFacts",
    "StructuredEvidence",
    "ContentComparisonResult",
    "ReviewDecisionType",
    "ReviewerDecision",
    "ProposedChange",
    "ChangeImpact",
    "ApprovedChangeReport",
    "ValidationFinding",
    "RelatedOccurrence",
]
