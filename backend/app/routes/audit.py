"""Audit trail and tamper-evidence inspection routes.

Provides read-only access to immutable workflow audit events and hash-chain verification.
"""

from typing import List, Optional
from fastapi import APIRouter, Query
from app.models.audit import AuditEvent, AuditVerificationResult
from app.routes.document_review import change_manager

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get(
    "",
    response_model=List[AuditEvent],
    summary="Retrieve complete chronological workflow audit trail",
)
async def get_audit_trail(
    limit: Optional[int] = Query(default=None, ge=1, description="Optional maximum number of events"),
) -> List[AuditEvent]:
    """Inspect all human-controlled regulatory review transitions in append order."""
    return change_manager.list_audit_events(limit=limit)


@router.get(
    "/verify",
    response_model=AuditVerificationResult,
    summary="Verify SHA-256 hash-chain integrity for tamper detection",
)
async def verify_audit_trail() -> AuditVerificationResult:
    """Verify cryptographic hash links and canonical payload integrity across all audit events."""
    return change_manager.verify_audit_trail()


@router.get(
    "/{change_id}",
    response_model=List[AuditEvent],
    summary="Retrieve audit trail for a specific change proposal",
)
async def get_audit_events_for_change(change_id: str) -> List[AuditEvent]:
    """Inspect all audit transitions associated with the given change_id."""
    return change_manager.list_audit_events_by_change(change_id)
