"""SQLite persistence store for regulatory workflow decisions, proposals, and reports.

Uses Python's standard-library sqlite3 module.
Maintains persistent audit state across application restarts without external database dependencies.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.audit import (
    AuditEvent,
    AuditVerificationResult,
    compute_event_hash,
)
from app.models.document_change import (
    ApprovedChangeReport,
    ChangeImpact,
    ProposedChange,
    ReviewDecisionType,
    ReviewerDecision,
    ValidationFinding,
)


class WorkflowSQLiteStore:
    """Handles durable SQLite read/write operations for workflow entities."""

    def __init__(self, db_path: Optional[str] = None):
        self._memory_conn: Optional[sqlite3.Connection] = None
        self.db_path = self._resolve_db_path(db_path)
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        else:
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    @staticmethod
    def _resolve_db_path(db_path: Optional[str] = None) -> str:
        """Resolve database path against settings or project root."""
        if db_path:
            return db_path

        configured = getattr(settings, "SQLITE_DB_PATH", "backend/data/gpr_workflow.db")
        if configured == ":memory:":
            return ":memory:"

        path_obj = Path(configured)
        if path_obj.is_absolute():
            return str(path_obj)

        # Resolve relative to project root (parent of backend)
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        return str((project_root / path_obj).resolve())

    def reconnect(self, new_db_path: str) -> None:
        """Switch store to another database path (used for test isolation)."""
        if self._memory_conn:
            try:
                self._memory_conn.close()
            except Exception:
                pass
            self._memory_conn = None

        self.db_path = self._resolve_db_path(new_db_path)
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        else:
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Provide a transactional SQLite connection with parameterized safety."""
        if self._memory_conn is not None:
            try:
                yield self._memory_conn
                self._memory_conn.commit()
            except Exception:
                self._memory_conn.rollback()
                raise
        else:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode = WAL;")
                cursor.execute("PRAGMA synchronous = NORMAL;")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_db(self) -> None:
        """Initialize database tables and schema version."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version;")
            row = cursor.fetchone()
            version = row[0] if row else 0

            # 1. Reviewer decisions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    decided_at TEXT,
                    data TEXT NOT NULL
                );
            """)

            # 2. Proposed changes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    change_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT,
                    data TEXT NOT NULL
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);")

            # 3. Approved change reports table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS approved_reports (
                    report_id TEXT PRIMARY KEY,
                    created_at TEXT,
                    data TEXT NOT NULL
                );
            """)

            # 4. Tamper-evident audit events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    change_id TEXT,
                    decision_id TEXT,
                    report_id TEXT,
                    reviewer_name TEXT,
                    previous_status TEXT,
                    new_status TEXT,
                    details TEXT NOT NULL,
                    previous_state TEXT,
                    new_state TEXT,
                    previous_event_hash TEXT,
                    event_hash TEXT NOT NULL
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_change_id ON audit_events(change_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_occurred_at ON audit_events(occurred_at);")

            if version < 2:
                cursor.execute("PRAGMA user_version = 2;")

    # =========================================================================
    # DECISIONS PERSISTENCE
    # =========================================================================

    def save_decision(self, decision: ReviewerDecision) -> ReviewerDecision:
        """Persist or update a reviewer decision."""
        data_json = decision.model_dump_json()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO decisions (decision_id, decided_at, data)
                VALUES (?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    decided_at = excluded.decided_at,
                    data = excluded.data;
            """, (decision.decision_id, decision.decided_at, data_json))
        return decision

    def get_decision(self, decision_id: str) -> Optional[ReviewerDecision]:
        """Fetch a reviewer decision by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM decisions WHERE decision_id = ?;", (decision_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ReviewerDecision.model_validate_json(row["data"])

    def list_decisions(self) -> List[ReviewerDecision]:
        """List all recorded decisions in insertion order."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM decisions ORDER BY rowid ASC;")
            rows = cursor.fetchall()
            return [ReviewerDecision.model_validate_json(row["data"]) for row in rows]

    def delete_decision(self, decision_id: str) -> bool:
        """Delete a decision by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM decisions WHERE decision_id = ?;", (decision_id,))
            return cursor.rowcount > 0

    def clear_decisions(self) -> None:
        """Remove all decisions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM decisions;")

    # =========================================================================
    # PROPOSALS PERSISTENCE
    # =========================================================================

    def _hydrate_proposal(self, row: sqlite3.Row) -> ProposedChange:
        """Deserialize and hydrate a proposal record with sub-models."""
        prop = ProposedChange.model_validate_json(row["data"])
        if isinstance(prop.impact_analysis, dict):
            try:
                prop.impact_analysis = ChangeImpact.model_validate(prop.impact_analysis)
            except Exception:
                pass
        if prop.validation_findings:
            hydrated_findings = []
            for item in prop.validation_findings:
                if isinstance(item, dict):
                    try:
                        hydrated_findings.append(ValidationFinding.model_validate(item))
                    except Exception:
                        hydrated_findings.append(item)
                else:
                    hydrated_findings.append(item)
            prop.validation_findings = hydrated_findings
        return prop

    def save_proposal(self, proposal: ProposedChange) -> ProposedChange:
        """Persist or update a proposed change."""
        data_json = proposal.model_dump_json()
        now_utc = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO proposals (change_id, status, created_at, updated_at, data)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(change_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    data = excluded.data;
            """, (proposal.change_id, proposal.status, proposal.created_at, now_utc, data_json))
        return proposal

    def get_proposal(self, change_id: str) -> Optional[ProposedChange]:
        """Fetch a proposed change by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM proposals WHERE change_id = ?;", (change_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._hydrate_proposal(row)

    def list_proposals(self, status: Optional[str] = None) -> List[ProposedChange]:
        """List proposals, optionally filtered by status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT data FROM proposals WHERE status = ? ORDER BY rowid ASC;", (status,))
            else:
                cursor.execute("SELECT data FROM proposals ORDER BY rowid ASC;")
            rows = cursor.fetchall()
            return [self._hydrate_proposal(row) for row in rows]

    def delete_proposal(self, change_id: str) -> bool:
        """Delete a proposal by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM proposals WHERE change_id = ?;", (change_id,))
            return cursor.rowcount > 0

    def clear_proposals(self) -> None:
        """Remove all proposals."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM proposals;")

    # =========================================================================
    # APPROVED REPORTS PERSISTENCE
    # =========================================================================

    def _hydrate_report(self, row: sqlite3.Row) -> ApprovedChangeReport:
        """Deserialize and hydrate an approved change report."""
        report = ApprovedChangeReport.model_validate_json(row["data"])
        for p in report.changes:
            if isinstance(p.impact_analysis, dict):
                try:
                    p.impact_analysis = ChangeImpact.model_validate(p.impact_analysis)
                except Exception:
                    pass
        return report

    def save_report(self, report: ApprovedChangeReport) -> ApprovedChangeReport:
        """Persist or update an authorized audit report."""
        data_json = report.model_dump_json()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO approved_reports (report_id, created_at, data)
                VALUES (?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    data = excluded.data;
            """, (report.report_id, report.generated_at, data_json))
        return report

    def get_report(self, report_id: str) -> Optional[ApprovedChangeReport]:
        """Fetch an approved change report by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM approved_reports WHERE report_id = ?;", (report_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._hydrate_report(row)

    def get_latest_report(self) -> Optional[ApprovedChangeReport]:
        """Retrieve most recently generated report."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM approved_reports ORDER BY rowid DESC LIMIT 1;")
            row = cursor.fetchone()
            if not row:
                return None
            return self._hydrate_report(row)

    def list_reports(self) -> List[ApprovedChangeReport]:
        """List all approved change reports."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM approved_reports ORDER BY rowid ASC;")
            rows = cursor.fetchall()
            return [self._hydrate_report(row) for row in rows]

    def delete_report(self, report_id: str) -> bool:
        """Delete an approved report by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM approved_reports WHERE report_id = ?;", (report_id,))
            return cursor.rowcount > 0

    def clear_reports(self) -> None:
        """Remove all approved reports."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM approved_reports;")

    # =========================================================================
    # AUDIT TRAIL PERSISTENCE (PHASE 4 STEP 5)
    # =========================================================================

    def _hydrate_audit_event(self, row: sqlite3.Row) -> AuditEvent:
        """Deserialize database row into AuditEvent."""
        details = json.loads(row["details"]) if row["details"] else {}
        prev_state = json.loads(row["previous_state"]) if row["previous_state"] else None
        new_state = json.loads(row["new_state"]) if row["new_state"] else None
        return AuditEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            occurred_at=row["occurred_at"],
            change_id=row["change_id"],
            decision_id=row["decision_id"],
            report_id=row["report_id"],
            reviewer_name=row["reviewer_name"],
            previous_status=row["previous_status"],
            new_status=row["new_status"],
            details=details,
            previous_state=prev_state,
            new_state=new_state,
            previous_event_hash=row["previous_event_hash"],
            event_hash=row["event_hash"],
        )

    def append_audit_event(
        self,
        event_type: str,
        change_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        report_id: Optional[str] = None,
        reviewer_name: Optional[str] = None,
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        new_state: Optional[Dict[str, Any]] = None,
        occurred_at: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> AuditEvent:
        """Append an audit event with sequential SHA-256 hash chaining inside a single transaction."""
        from uuid import uuid4

        event_id = event_id or f"evt_{uuid4().hex[:12]}"
        occurred_at = occurred_at or datetime.now(timezone.utc).isoformat()
        details_dict = details or {}

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Fetch latest event's hash for hash chaining
            cursor.execute("SELECT event_hash FROM audit_events ORDER BY rowid DESC LIMIT 1;")
            last_row = cursor.fetchone()
            previous_event_hash = last_row["event_hash"] if last_row else None

            event_hash = compute_event_hash(
                event_id=event_id,
                event_type=event_type,
                occurred_at=occurred_at,
                change_id=change_id,
                decision_id=decision_id,
                report_id=report_id,
                reviewer_name=reviewer_name,
                previous_status=previous_status,
                new_status=new_status,
                details=details_dict,
                previous_state=previous_state,
                new_state=new_state,
                previous_event_hash=previous_event_hash,
            )

            event = AuditEvent(
                event_id=event_id,
                event_type=event_type,
                occurred_at=occurred_at,
                change_id=change_id,
                decision_id=decision_id,
                report_id=report_id,
                reviewer_name=reviewer_name,
                previous_status=previous_status,
                new_status=new_status,
                details=details_dict,
                previous_state=previous_state,
                new_state=new_state,
                previous_event_hash=previous_event_hash,
                event_hash=event_hash,
            )

            details_json = json.dumps(details_dict, sort_keys=True, separators=(",", ":"))
            prev_state_json = (
                json.dumps(previous_state, sort_keys=True, separators=(",", ":"))
                if previous_state is not None
                else None
            )
            new_state_json = (
                json.dumps(new_state, sort_keys=True, separators=(",", ":"))
                if new_state is not None
                else None
            )

            cursor.execute("""
                INSERT INTO audit_events (
                    event_id, event_type, occurred_at, change_id, decision_id, report_id,
                    reviewer_name, previous_status, new_status, details, previous_state,
                    new_state, previous_event_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                event.event_id,
                event.event_type,
                event.occurred_at,
                event.change_id,
                event.decision_id,
                event.report_id,
                event.reviewer_name,
                event.previous_status,
                event.new_status,
                details_json,
                prev_state_json,
                new_state_json,
                event.previous_event_hash,
                event.event_hash,
            ))
            return event

    def record_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Directly insert a constructed AuditEvent (used in tamper simulation tests)."""
        details_json = json.dumps(event.details or {}, sort_keys=True, separators=(",", ":"))
        prev_state_json = (
            json.dumps(event.previous_state, sort_keys=True, separators=(",", ":"))
            if event.previous_state is not None
            else None
        )
        new_state_json = (
            json.dumps(event.new_state, sort_keys=True, separators=(",", ":"))
            if event.new_state is not None
            else None
        )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_events (
                    event_id, event_type, occurred_at, change_id, decision_id, report_id,
                    reviewer_name, previous_status, new_status, details, previous_state,
                    new_state, previous_event_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                event.event_id,
                event.event_type,
                event.occurred_at,
                event.change_id,
                event.decision_id,
                event.report_id,
                event.reviewer_name,
                event.previous_status,
                event.new_status,
                details_json,
                prev_state_json,
                new_state_json,
                event.previous_event_hash,
                event.event_hash,
            ))
        return event

    def get_audit_event(self, event_id: str) -> Optional[AuditEvent]:
        """Fetch a single audit event by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_events WHERE event_id = ?;", (event_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._hydrate_audit_event(row)

    def list_audit_events(self, limit: Optional[int] = None) -> List[AuditEvent]:
        """List audit events in chronological append order."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if limit and limit > 0:
                cursor.execute("SELECT * FROM audit_events ORDER BY rowid ASC LIMIT ?;", (limit,))
            else:
                cursor.execute("SELECT * FROM audit_events ORDER BY rowid ASC;")
            rows = cursor.fetchall()
            return [self._hydrate_audit_event(row) for row in rows]

    def list_audit_events_by_change(self, change_id: str) -> List[AuditEvent]:
        """List audit events related to a specific change proposal ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM audit_events WHERE change_id = ? ORDER BY rowid ASC;",
                (change_id,),
            )
            rows = cursor.fetchall()
            return [self._hydrate_audit_event(row) for row in rows]

    def get_latest_audit_event(self) -> Optional[AuditEvent]:
        """Fetch the most recent audit event in the chain."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_events ORDER BY rowid DESC LIMIT 1;")
            row = cursor.fetchone()
            if not row:
                return None
            return self._hydrate_audit_event(row)

    def verify_hash_chain(self) -> AuditVerificationResult:
        """Verify append-only hash chain integrity across all audit events.

        Detects:
        - modified event contents
        - modified event_hash
        - broken previous_event_hash linkage
        - missing, deleted, or reordered events
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_events ORDER BY rowid ASC;")
            rows = cursor.fetchall()

        if not rows:
            return AuditVerificationResult(
                valid=True,
                checked_event_count=0,
                first_invalid_event_id=None,
                reason=None,
            )

        events = [self._hydrate_audit_event(row) for row in rows]
        for idx, event in enumerate(events):
            # 1. Verify previous_event_hash linkage
            if idx == 0:
                if event.previous_event_hash is not None and event.previous_event_hash != "":
                    return AuditVerificationResult(
                        valid=False,
                        checked_event_count=0,
                        first_invalid_event_id=event.event_id,
                        reason="Genesis event has non-empty previous_event_hash.",
                    )
            else:
                expected_prev_hash = events[idx - 1].event_hash
                if event.previous_event_hash != expected_prev_hash:
                    return AuditVerificationResult(
                        valid=False,
                        checked_event_count=idx,
                        first_invalid_event_id=event.event_id,
                        reason=(
                            f"Broken hash chain link at event '{event.event_id}'. "
                            f"Expected previous_event_hash='{expected_prev_hash}', got '{event.previous_event_hash}'."
                        ),
                    )

            # 2. Recompute and verify event_hash against canonical event content
            computed_hash = compute_event_hash(
                event_id=event.event_id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                change_id=event.change_id,
                decision_id=event.decision_id,
                report_id=event.report_id,
                reviewer_name=event.reviewer_name,
                previous_status=event.previous_status,
                new_status=event.new_status,
                details=event.details,
                previous_state=event.previous_state,
                new_state=event.new_state,
                previous_event_hash=event.previous_event_hash,
            )
            if event.event_hash != computed_hash:
                return AuditVerificationResult(
                    valid=False,
                    checked_event_count=idx,
                    first_invalid_event_id=event.event_id,
                    reason=(
                        f"Tampered event payload or hash at event '{event.event_id}'. "
                        f"Stored hash '{event.event_hash}' does not match computed hash '{computed_hash}'."
                    ),
                )

        return AuditVerificationResult(
            valid=True,
            checked_event_count=len(events),
            first_invalid_event_id=None,
            reason=None,
        )

    # =========================================================================
    # SESSION RESET
    # =========================================================================

    def clear_all(self, include_audit: bool = True) -> None:
        """Reset all workflow tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM decisions;")
            cursor.execute("DELETE FROM proposals;")
            cursor.execute("DELETE FROM approved_reports;")
            if include_audit:
                cursor.execute("DELETE FROM audit_events;")
