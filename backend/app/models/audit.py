"""Pydantic data models for the tamper-evident regulatory audit trail.

Maintains an append-only, SHA-256 hash-chained log of all human-controlled
regulatory workflow actions and governance transitions.
Provides tamper evidence (detection), not cryptographic immutability.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """Explicit event types for human regulatory workflow transitions."""

    REVIEWER_DECISION_CREATED = "REVIEWER_DECISION_CREATED"
    CHANGE_PROPOSAL_CREATED = "CHANGE_PROPOSAL_CREATED"
    OCCURRENCES_CONFIRMED = "OCCURRENCES_CONFIRMED"
    CHANGE_VALIDATED = "CHANGE_VALIDATED"
    CHANGE_APPROVED = "CHANGE_APPROVED"
    CHANGE_REJECTED = "CHANGE_REJECTED"
    APPROVED_REPORT_CREATED = "APPROVED_REPORT_CREATED"


def compute_event_hash(
    event_id: str,
    event_type: str,
    occurred_at: str,
    change_id: Optional[str],
    decision_id: Optional[str],
    report_id: Optional[str],
    reviewer_name: Optional[str],
    previous_status: Optional[str],
    new_status: Optional[str],
    details: Dict[str, Any],
    previous_state: Optional[Dict[str, Any]],
    new_state: Optional[Dict[str, Any]],
    previous_event_hash: Optional[str],
) -> str:
    """Calculate deterministic SHA-256 tamper-evident hash over canonical JSON representation."""
    canonical_payload = {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "change_id": change_id,
        "decision_id": decision_id,
        "report_id": report_id,
        "reviewer_name": reviewer_name,
        "previous_status": previous_status,
        "new_status": new_status,
        "details": details or {},
        "previous_state": previous_state,
        "new_state": new_state,
        "previous_event_hash": previous_event_hash or "",
    }
    canonical_bytes = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


class AuditEvent(BaseModel):
    """Immutable record of a human-controlled workflow transition."""

    event_id: str = Field(
        default_factory=lambda: f"evt_{uuid4().hex[:12]}",
        description="Unique audit event identifier",
    )
    event_type: str = Field(..., description="Explicit workflow transition type")
    occurred_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO-8601 timestamp of event occurrence",
    )
    change_id: Optional[str] = Field(default=None, description="Related change proposal ID if applicable")
    decision_id: Optional[str] = Field(default=None, description="Related reviewer decision ID if applicable")
    report_id: Optional[str] = Field(default=None, description="Related approved report ID if applicable")
    reviewer_name: Optional[str] = Field(default=None, description="Name/identity of human reviewer")
    previous_status: Optional[str] = Field(default=None, description="Status before transition")
    new_status: Optional[str] = Field(default=None, description="Status after transition")
    details: Dict[str, Any] = Field(default_factory=dict, description="Structured event context")
    previous_state: Optional[Dict[str, Any]] = Field(default=None, description="State snapshot prior to transition")
    new_state: Optional[Dict[str, Any]] = Field(default=None, description="State snapshot after transition")
    previous_event_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of previous event in chain (empty/null for genesis event)",
    )
    event_hash: str = Field(..., description="SHA-256 hash of canonical payload + previous_event_hash")


class AuditVerificationResult(BaseModel):
    """Result of full hash-chain verification for tamper detection."""

    valid: bool = Field(..., description="Whether entire audit hash chain is intact and un-tampered")
    checked_event_count: int = Field(default=0, description="Total number of events verified")
    first_invalid_event_id: Optional[str] = Field(default=None, description="ID of first event where verification failed")
    reason: Optional[str] = Field(default=None, description="Explanation if verification failed")
