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
    ConfirmOccurrencesRequest,
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
from app.models.audit import (
    AuditEvent,
    AuditEventType,
    AuditVerificationResult,
    compute_event_hash,
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
    "ConfirmOccurrencesRequest",
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
    "AuditEvent",
    "AuditEventType",
    "AuditVerificationResult",
    "compute_event_hash",
]


