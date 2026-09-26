# Phase 4 Handover — Regulatory Content Reuse Finder

## 1. Project Overview & Core Purpose
* **Project Name:** Regulatory Content Reuse Finder (GPR)
* **Domain:** Life Sciences — Regulatory Affairs
* **Core Purpose:** AI-assisted regulatory content reuse decision support for regulatory affairs professionals. The application assists in discovering potentially reusable content from live authoritative sources (NLM DailyMed and openFDA), performing 6-dimensional comparative analysis against draft texts, highlighting terminology/dosage differences, tracking cross-section occurrences, and formulating controlled change proposals.
* **Core Principle:** *"Complex inside, simple outside."* The human regulatory professional remains the sole, final decision-maker throughout the workflow. The application strictly operates as decision support and never makes autonomous regulatory decisions or unilaterally mutates regulatory dossiers.

---

## 2. System Architecture

```
Draft Document (Internal / Uploaded)
       │
       ▼
Universal Ingestion & Structure-Preserving Chunking (PDF, DOCX, TXT, MD, JSON, XML, HTML)
       │
       ▼
Agent 1: Regulatory Content Analysis Agent ────► Live Queries (NLM DailyMed & openFDA)
       │                                                │
       ├────────────────────────────────────────────────┘
       ▼
6-Dimensional Candidate Comparison & Difference Detection
(Meaning, Template, Context, Structure, Format, Key Information)
       │
       ▼
Human Regulatory Review Gateway
[ REUSE | ADAPT | REJECT ]
       │
       ▼
Agent 2: Regulatory Document Change Agent
(Controlled Change Formulation & Cross-Section Occurrence Detection)
       │
       ▼
Human Occurrence Confirmation Gate
[ CONFIRMED | EXCLUDED | PENDING ]
       │
       ▼
Section-Level Impact Analysis (Confirmed Occurrences Only)
       │
       ▼
Deterministic Regulatory Validation Engine (REG-VAL-001 through REG-VAL-006)
       │
       ▼
Human Approval Gate (Explicit Authorization Required)
       │
       ▼
Approved Change Report
       │
       ├─────────────────────────────────────────┐
       ▼                                         ▼
Tamper-Evident Cryptographic Audit Trail    ReportLab PDF Generation & Export
(SHA-256 Back-Linked Hash Chain)            (Audit-Ready Human-Readable Document)
       │                                         │
       ▼                                         ▼
SQLite Workflow Persistence                 Frontend Browser Download
(backend/data/gpr_workflow.db)              (Download PDF Action)
```

### Technology Stack
* **Backend:** Python 3.10+, FastAPI, Uvicorn, Pydantic v2, Pydantic Settings, HTTPX, SQLite3, ReportLab, Pytest
* **Frontend:** React 19, Vite 8, Vanilla CSS Design System, Lucide React Icons
* **AI / LLM Integration:** OpenAI API (backend-only; API keys are never exposed to the client)
* **Authoritative External Sources:** NLM DailyMed REST API v2 & openFDA Drug Labeling API

---

## 3. Completed Phase 4 Capabilities

### 1. Occurrence Confirmation Workflow
* **Occurrence States:** Related cross-section occurrences within target documents support three states: `PENDING`, `CONFIRMED`, and `EXCLUDED`.
* **Governance Gate (REG-VAL-006):** Proposal approval is strictly blocked as long as any related occurrence remains in `PENDING` status.
* **Impact Analysis Scoping:** Only `CONFIRMED` occurrences contribute to affected-section counts and impact severity calculations; `EXCLUDED` occurrences are omitted from impact metrics.
* **Human Decision Control:** Human regulatory reviewers must explicitly confirm or exclude each occurrence before advancing to approval.

### 2. SQLite Workflow Persistence
* **Database Location:** `backend/data/gpr_workflow.db` (Schema version: `user_version = 2`).
* **Persisted Entities:**
  * Reviewer decisions (`REUSE`, `ADAPT`, `REJECT`)
  * Change proposals (including justification, scope, original/candidate texts)
  * Related occurrence records and their human confirmation statuses
  * Section-level impact analysis evaluations
  * Deterministic validation findings
  * Final approved change reports
  * Complete tamper-evident audit events
* **Restart Reconstruction:** Workflow state reliably reconstructs across backend service restarts and store reloads.
* **Boundary Clarification:** SQLite persistence applies strictly to governance workflow state. Candidate document chunks, vector embeddings, and external API query caches remain ephemeral in the current V1 architecture.

### 3. Tamper-Evident Audit Trail
* **Cryptographic Architecture:** Append-only SHA-256 hash-chained ledger.
* **Chain Structure:** Each audit event computes its `event_hash` over canonical JSON containing:
  `event_id`, `change_id`, `event_type`, `timestamp`, `actor`, `action`, `previous_event_hash`, `details`, and `system_version`.
* **Audit Event Lifecycle:**
  * `REVIEWER_DECISION_RECORDED`
  * `CHANGE_PROPOSAL_CREATED`
  * `OCCURRENCES_CONFIRMED`
  * `CHANGE_VALIDATED`
  * `CHANGE_APPROVED` / `CHANGE_REJECTED`
  * `APPROVED_REPORT_CREATED`
* **Verification & Query Endpoints:**
  * `GET /audit`: Query all audit events chronologically
  * `GET /audit/{change_id}`: Retrieve audit history for a specific change proposal
  * `GET /audit/verify`: Verify the full cryptographic integrity of the audit chain
* **Tamper Sensitivity:** Any alteration to stored event data, `event_hash`, or `previous_event_hash` produces an immediate verification failure.
* **Regulatory Compliance Notice:** The tamper-evident audit trail provides structural auditability and cryptographic traceability; it does not constitute an autonomous claim of regulatory compliance or formal legal certification.

### 4. Approved Change Report PDF Export
* **Endpoint:** `GET /changes/report/{report_id}/pdf`
* **Server-Side Generation:** Implemented with ReportLab, producing standard, audit-ready `%PDF-` documents.
* **Report Sections:** Executive summary, original vs. candidate text comparison, reviewer justification and scope, confirmed related occurrences, impact analysis, validation findings, and complete audit trail table.
* **Read-Only & Hash Preservation:** The generator reads directly from stored approved change reports without mutating report data or source documents. Stored SHA-256 audit hashes are preserved identically.
* **Zero Side-Effects:** PDF generation and download do not emit additional audit events.
* **Approval Gate Enforcement:** Requests for unapproved proposals or non-existent reports return 400 Bad Request or 404 Not Found.

### 5. Frontend PDF Download UI
* **Component:** `ApprovedChangeReport.jsx` integrated with `frontend/src/services/api.js`.
* **User Experience:** Clean "Download PDF" action with loading indicator and visual feedback.
* **Governance Enforcement:** The PDF download action is enabled only when an approved report exists and is disabled during active requests.
* **Authoritative Source:** The frontend does not fabricate report PDFs client-side; the backend remains the sole authoritative source.

### 6. Phase 4 Step 8 Workflow Hardening
* **Dedicated Test Suite:** [`backend/tests/unit/test_phase4_workflow_hardening.py`](backend/tests/unit/test_phase4_workflow_hardening.py) containing 16 focused end-to-end and governance boundary tests.
* **Verified Behaviors:**
  * `REJECT` decision blocks change proposal generation
  * `REUSE` and `ADAPT` decisions create properly structured proposals
  * Unconfirmed (`PENDING`) occurrences strictly block approval
  * `EXCLUDED` occurrences are excluded from impact analysis
  * Approval strictly requires explicit human confirmation (`approved: True`)
  * Validation failures halt the approval workflow
  * Audit tampering (payload, hash, previous hash link) is detected
  * Stored SHA-256 audit hashes are exactly preserved in generated PDFs
  * PDF generation emits zero audit events
  * Full workflow state reconstructs across store restarts
  * Complete 13-stage end-to-end lifecycle verification

---

## 4. Current Verification & Benchmark Results

### Automated Test Suite
* **Backend Unit & API Tests:** **326 passed, 0 failed** (pytest run time: ~17s).
* **Frontend Lint:** **0 errors, 3 warnings** (oxlint; 3 pre-existing unused variable warnings in legacy `Dashboard.jsx`).
* **Frontend Production Build:** **Passed** (`vite build` completed in 1.41s, generating production bundle).

### Static Analysis & Python Compilation
* **Pyrefly Status:** Configured under `[tool.pyrefly]` in `pyproject.toml`; the standalone CLI binary is not installed in the local environment.
* **Compilation Check:** Verified clean compilation across all backend modules using `python -m compileall backend/ -q` (0 errors).

### Core Evaluation Benchmark (`evaluation/run_evaluation.py`)
Current test evaluation results against the established baseline:
* **6-Dimensional Comparison Accuracy:** 94.4% (Baseline: 94.4%)
  * Meaning: 100.0% (3/3)
  * Template: 66.7% (2/3)
  * Context: 100.0% (3/3)
  * Structure: 100.0% (3/3)
  * Format: 100.0% (3/3)
  * Key Information: 100.0% (3/3)
* **Deterministic Difference Detection Accuracy:** 100.0% (Baseline: 100.0%)
* **False-Match Protection Accuracy:** 100.0% (Baseline: 100.0%)
* **Recall@3:** 1.0 (Baseline: 1.0)
* **Precision@3:** 0.6667 (Baseline: 0.6667)
* **Hit Rate@3:** 1.0 (Baseline: 1.0)
* **MRR:** 1.0 (Baseline: 1.0)
* **Groundedness Accuracy:** 100.0% (Baseline: 100.0%)

> [!NOTE]
> Evaluation results reflect deterministic and model-assisted performance on the evaluation dataset baseline and do not represent formal clinical or regulatory certification.

---

## 5. Human-in-the-Loop Governance Boundaries

1. **Decision Support Only:** The system serves exclusively to augment regulatory professionals by surfacing relevant precedents, highlighting differences, and organizing change proposals.
2. **Sole Human Authority:** The human regulatory professional makes all binding decisions:
   * Content decision: `REUSE`, `ADAPT`, or `REJECT`
   * Occurrence disposition: `CONFIRMED` or `EXCLUDED`
   * Final proposal approval: `APPROVED` or `REJECTED`
3. **No Autonomous Mutation:** The application never modifies source regulatory documents, never alters external regulatory dossiers, and never propagates changes autonomously.

---

## 6. Current System Boundaries & Limitations

* **Ephemeral Ingested Candidate Store:** Uploaded draft document candidates and chunks are stored in-memory in `IngestedDocumentCandidateStore` and reset on server restart.
* **Ephemeral Vector Store:** In-memory vector embeddings used for similarity search are not persisted across server restarts.
* **Ephemeral API Caches:** DailyMed and openFDA live query results and XML/JSON caches are held in memory.
* **Workflow-Only Persistence:** SQLite strictly persists governance workflow data (decisions, proposals, occurrences, impact, validation, reports, audit trail), not raw candidate documents or vector stores.
* **No Synthetic Data Generation:** The application does not generate synthetic regulatory documents or synthetic labeling data.
* **Evaluation Baseline Scope:** Evaluation metrics represent current test benchmark results and are not clinical validation guarantees.

---

## 7. Phase 4 Git Checkpoint History

* `b9baa7e`: `feat: add approved change report PDF export` (Backend ReportLab PDF generation and endpoint)
* `e551bba`: `feat: add approved change report PDF download` (Frontend PDF download action and API integration)
* `d1f4ad7`: `test: harden phase 4 end-to-end workflow` (16-test workflow hardening and evaluation verification suite)
