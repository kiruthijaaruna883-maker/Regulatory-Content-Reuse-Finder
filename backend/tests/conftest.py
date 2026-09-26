"""Pytest configuration and shared fixtures."""

import os
import sys
from pathlib import Path

# Add backend directory to sys.path so app modules import cleanly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest


@pytest.fixture(autouse=True)
def isolate_test_database(tmp_path, monkeypatch):
    """Ensure every test runs with an isolated, temporary SQLite database.

    Prevents test data from writing into developer backend/data/gpr_workflow.db
    and prevents tests from cross-contaminating each other.
    """
    test_db = str(tmp_path / "test_gpr_workflow.db")
    monkeypatch.setattr("app.config.settings.SQLITE_DB_PATH", test_db)
    from app.routes import document_review
    document_review.change_manager.store.reconnect(test_db)
    yield

