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
from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryChunk,
    RegulatoryChunkType,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
    RegulatoryTable,
    RegulatoryTableRow,
)
from app.models.ingest import (
    CandidateSearchRequest,
    DocumentIngestResponse,
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
    "CanonicalSectionConcept",
    "RegulatoryChunk",
    "RegulatoryChunkType",
    "RegulatoryDocument",
    "RegulatoryProvenance",
    "RegulatorySection",
    "RegulatoryTable",
    "RegulatoryTableRow",
    "DocumentIngestResponse",
    "CandidateSearchRequest",
]

