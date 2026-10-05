"""Pydantic data models for human review decisions, controlled change proposals, and change reports.

Enforces human-in-the-loop governance: AI proposes changes, but regulatory professional approves.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4
from pydantic import BaseModel, Field
from app.models.comparison import EvidenceTrace


class ReviewDecisionType(str, Enum):
    """Controlled human decision states for regulatory content reuse."""

    REUSE = "REUSE"
    ADAPT = "ADAPT"
    REJECT = "REJECT"


class ReviewerDecision(BaseModel):
    """Human regulatory professional's decision on a candidate."""

    decision_id: str = Field(
        default_factory=lambda: f"dec_{uuid4().hex[:8]}",
        description="Unique decision identifier",
    )
    target_content_id: str = Field(..., description="ID of internal content being reviewed")
    candidate_id: Optional[str] = Field(
        default=None,
        description="ID of regulatory candidate accepted/adapted/rejected",
    )
    decision: ReviewDecisionType = Field(
        ...,
        description="Human professional decision: REUSE, ADAPT, or REJECT",
    )
    reviewer_name: str = Field(
        default="Regulatory Professional",
        description="Name or ID of reviewing regulatory authority",
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Professional justification and clinical rationale",
    )
    adaptation_instructions: Optional[str] = Field(
        default=None,
        description="Specific instructions when decision is ADAPT",
    )
    decided_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp of the decision",
    )


class RelatedOccurrence(BaseModel):
    """Identified occurrence of content in related sections or documents."""

    occurrence_id: str = Field(
        default_factory=lambda: f"occ_{uuid4().hex[:8]}",
        description="Occurrence identifier",
    )
    document_name: Optional[str] = Field(default=None, description="Document where occurrence exists")
    document_version: Optional[str] = Field(default=None, description="Document version if known")
    section: str = Field(..., description="Section containing the occurrence")
    location: Optional[str] = Field(default=None, description="Specific location or paragraph reference")
    match_type: str = Field(
        default="exact_match",
        description="Match layer: exact_match, normalized_match, structured_match, or semantic_match",
    )
    matched_text: Optional[str] = Field(default=None, description="Matched text excerpt")
    current_text: str = Field(..., description="Full current text snippet of the occurrence")
    relevance: str = Field(default="DIRECT", description="Relevance: DIRECT or INDIRECT")
    source_identifier: Optional[str] = Field(default=None, description="Source ID if known (e.g., Set ID)")
    source_url: Optional[str] = Field(default=None, description="Official source URL if known")
    reason: Optional[str] = Field(default=None, description="Evidence explaining why this was considered related")
    evidence_explanation: Optional[str] = Field(default=None, description="Detailed explanation of matching basis")
    status: Literal["PENDING", "CONFIRMED", "EXCLUDED"] = Field(
        default="PENDING",
        description="Reviewer confirmation status: PENDING (unreviewed), CONFIRMED (included in coordinated change), EXCLUDED (preserved/excluded)",
    )
    dimensional_evidence: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Six-dimensional alignment evidence for this occurrence.",
    )
    dimensional_scores: Optional[Dict[str, float]] = Field(
        default=None,
        description="Six-dimensional alignment scores for this occurrence.",
    )


class ConfirmOccurrencesRequest(BaseModel):
    """Payload to confirm or exclude related occurrences for a proposed change."""

    change_id: str = Field(..., min_length=1, description="Target proposed change identifier")
    confirmed_occurrence_ids: List[str] = Field(
        default_factory=list,
        description="IDs of occurrences explicitly confirmed for coordinated change",
    )
    excluded_occurrence_ids: List[str] = Field(
        default_factory=list,
        description="IDs of occurrences explicitly excluded/preserved from coordinated change",
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Optional clinical or regulatory reviewer justification notes",
    )


class ProposedChange(BaseModel):
    """Controlled change proposal produced by Agent 2 based on human approval."""

    change_id: str = Field(
        default_factory=lambda: f"chg_{uuid4().hex[:8]}",
        description="Proposal identifier",
    )
    decision_id: str = Field(..., description="Linked human reviewer decision ID")
    document_name: Optional[str] = Field(default=None, description="Subject regulatory document name if provided")
    document_version: Optional[str] = Field(default=None, description="Subject document version if provided")
    section: str = Field(..., description="Target regulatory section")
    original_text: str = Field(..., description="Original text prior to proposed change")
    proposed_text: str = Field(..., description="Proposed replacement/adapted text")
    decision_type: ReviewDecisionType = Field(..., description="Source decision type")
    rationale: str = Field(..., description="Traceable rationale for the modification")
    source_evidence: Optional[EvidenceTrace] = Field(
        default=None,
        description="Cited external regulatory provenance",
    )
    related_occurrences: List[RelatedOccurrence] = Field(
        default_factory=list,
        description="Other occurrences identified for coordinated update",
    )
    impact_analysis: Optional[Any] = Field(default=None, description="Structured ChangeImpact summary")
    validation_findings: List[Any] = Field(default_factory=list, description="Validation check results")
    status: str = Field(
        default="PROPOSED",
        description="Proposal lifecycle status: PROPOSED, PENDING_APPROVAL, APPROVED, REJECTED",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Proposal creation timestamp",
    )


class ValidationFinding(BaseModel):
    """Validation finding evaluating compliance and consistency of a change."""

    rule_id: str = Field(..., description="Validation rule code")
    rule_name: Optional[str] = Field(default=None, description="Descriptive name of rule")
    severity: str = Field(..., description="Formally defined severity: INFO, WARNING, or ERROR")
    status: Optional[str] = Field(default=None, description="PASSED or FAILED")
    message: str = Field(..., description="Finding description")
    field: Optional[str] = Field(default=None, description="Specific field evaluated")
    passed: bool = Field(..., description="Whether check passed")


class ChangeImpact(BaseModel):
    """Impact assessment of proposed changes across document boundaries."""

    impact_id: str = Field(
        default_factory=lambda: f"imp_{uuid4().hex[:8]}",
        description="Impact assessment identifier",
    )
    risk_level: str = Field(default="LOW", description="Assessed risk: LOW, MEDIUM, HIGH")
    affected_sections_count: int = Field(default=1, description="Count of distinct affected sections")
    affected_sections: List[str] = Field(default_factory=list, description="List of affected section titles")
    affected_occurrences: List[RelatedOccurrence] = Field(
        default_factory=list,
        description="Related occurrences affected",
    )
    affected_documents: List[str] = Field(default_factory=list, description="Distinct affected documents")
    affected_content_count: int = Field(default=1, description="Total affected content count")
    observed_impacts: List[str] = Field(
        default_factory=list,
        description="Observed impacts verified directly against source texts",
    )
    potential_impacts: List[str] = Field(
        default_factory=list,
        description="Potential impacts requiring human regulatory reviewer verification",
    )
    reviewer_attention_required: bool = Field(
        default=False,
        description="Flag indicating reviewer must review specific impact anomalies",
    )
    findings: List[ValidationFinding] = Field(default_factory=list, description="Validation check results")
    validation_passed: bool = Field(default=True, description="Overall validation status")
    validation_status: bool = Field(default=True, description="Alias for overall validation status")


class ApprovedChangeReport(BaseModel):
    """Audit-ready change report documenting all approved changes with full source traceability."""

    report_id: str = Field(
        default_factory=lambda: f"rep_{uuid4().hex[:10]}",
        description="Audit report identifier",
    )
    document_name: Optional[str] = Field(default=None, description="Subject regulatory document name if provided")
    document_version: Optional[str] = Field(default=None, description="Target document revision if provided")
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Report generation timestamp",
    )
    author_approver: str = Field(..., description="Name of final regulatory approver")
    decision_ids: List[str] = Field(default_factory=list, description="List of authorized decision IDs")
    changes: List[ProposedChange] = Field(default_factory=list, description="List of approved changes")
    source_evidence: List[EvidenceTrace] = Field(
        default_factory=list,
        description="Supporting external regulatory evidence traces",
    )
    validation_summary: Optional[str] = Field(default=None, description="Summary of validation findings")
    impact_summary: Optional[str] = Field(default=None, description="Summary of evaluated impact")
    audit_notes: Optional[str] = Field(default=None, description="Regulatory compliance commentary")
    approval_timestamp: Optional[str] = Field(default=None, description="Timestamp of explicit human approval")
    approval_confirmation: bool = Field(
        default=False,
        description="Explicit human approval confirmation. MUST NEVER DEFAULT TO TRUE.",
    )
