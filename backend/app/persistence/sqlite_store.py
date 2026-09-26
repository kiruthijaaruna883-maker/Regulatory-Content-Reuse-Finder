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

            if version == 0:
                cursor.execute("PRAGMA user_version = 1;")

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
    # SESSION RESET
    # =========================================================================

    def clear_all(self) -> None:
        """Reset all workflow tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM decisions;")
            cursor.execute("DELETE FROM proposals;")
            cursor.execute("DELETE FROM approved_reports;")
