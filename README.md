# Regulatory Content Reuse Finder

**Domain:** Life Sciences – Regulatory Affairs  
**Status:** Phase 4 Complete (Governance, Persistence, Audit Trail & PDF Export)

The **Regulatory Content Reuse Finder (GPR)** is an AI-assisted decision support application designed for Life Sciences regulatory professionals. It assists in discovering potentially reusable regulatory content from live authoritative sources (NLM DailyMed and openFDA), performing 6-dimensional comparative analysis against draft documents, detecting differences in clinical terminology and dosage, tracking cross-section occurrences across dossiers, preserving cryptographic audit trails, and generating audit-ready approved change reports.

> [!IMPORTANT]
> **Human-in-the-Loop Governance:** The application operates strictly as decision support. It does **NOT** autonomously approve regulatory content, unilaterally mutate source regulatory documents, or propagate changes automatically. The human regulatory professional remains the sole, final decision-maker throughout the workflow.

---

## 1. System Architecture

The complete system follows a strictly governed **Two-Agent Architecture** with integrated governance gates:

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

### Agent Roles

1. **Agent 1 — Regulatory Content Analysis Agent:**
   - Ingests draft regulatory documents across formats (PDF, DOCX, TXT, MD, JSON, XML, HTML).
   - Classifies regulatory document structures and performs structure-preserving chunking.
   - Coordinates live retrieval against external regulatory repositories (DailyMed, openFDA).
   - Computes 6-dimensional comparison scores (Meaning, Template, Context, Structure, Format, Key Information).
   - Detects deterministic differences (additions, deletions, numerical dosage disparities).
   - **Constraint:** Provides analytical evidence; does *not* make final regulatory reuse decisions.

2. **Agent 2 — Regulatory Document Change Agent:**
   - Formulates controlled change proposals strictly bound to human review decisions (`REUSE`, `ADAPT`, `REJECT`).
   - Identifies related cross-section occurrences across the regulatory dossier.
   - Manages occurrence lifecycle (`PENDING`, `CONFIRMED`, `EXCLUDED`).
   - Evaluates section-level impact analysis based on confirmed occurrences.
   - Runs deterministic regulatory validation checks (`REG-VAL-001` through `REG-VAL-006`).
   - Generates audit-ready approved change reports upon explicit human approval.
   - **Constraint:** Formulates controlled proposals; does *not* autonomously overwrite files or dossiers.

---

## 2. Phase 4 Capabilities

### 1. Occurrence Confirmation Workflow
- **Occurrence States:** Cross-section occurrences within target documents support `PENDING`, `CONFIRMED`, and `EXCLUDED`.
- **Governance Gate (REG-VAL-006):** Approval is strictly blocked while any occurrence remains in `PENDING` status.
- **Impact Scoping:** Only `CONFIRMED` occurrences contribute to affected-section counts and impact severity; `EXCLUDED` occurrences are omitted from impact metrics.
- **Human Decision Requirement:** Explicit human confirmation or exclusion is mandatory before advancing to approval.

### 2. SQLite Workflow Persistence
- **Storage Path:** `backend/data/gpr_workflow.db` (Schema version: `user_version = 2`).
- **Persisted Data:** Reviewer decisions, proposed changes, occurrence statuses, impact analyses, validation results, approved change reports, and tamper-evident audit events.
- **Reconstruction:** Workflow state reliably reconstructs across server restarts and service reloads.
- **Scope Boundary:** SQLite persists governance workflow state. Uploaded candidate documents, chunks, vector embeddings, and external API caches remain ephemeral in the current V1 architecture.

### 3. Tamper-Evident Audit Trail
- **Cryptographic Model:** Append-only SHA-256 hash-chained ledger.
- **Canonical Serialization:** Every event computes its SHA-256 `event_hash` over canonical JSON, linking to `previous_event_hash`.
- **Event Lifecycle:** Covers `REVIEWER_DECISION_RECORDED`, `CHANGE_PROPOSAL_CREATED`, `OCCURRENCES_CONFIRMED`, `CHANGE_VALIDATED`, `CHANGE_APPROVED` / `CHANGE_REJECTED`, and `APPROVED_REPORT_CREATED`.
- **Integrity Verification:** The `/audit/verify` endpoint verifies the mathematical validity of the complete audit chain. Any payload or hash tampering immediately triggers verification failure.
- **Notice:** The audit trail provides internal cryptographic traceability; it is not an autonomous claim of formal legal or regulatory certification.

### 4. Approved Change Report PDF Generation
- **Endpoint:** `GET /changes/report/{report_id}/pdf`
- **Server-Side Generation:** Generated using ReportLab directly from stored `ApprovedChangeReport` models.
- **Report Elements:** Document headers, executive summary, side-by-side text comparisons, reviewer justification and scope, confirmed occurrences, impact analysis, validation findings, and the full audit trail with SHA-256 hashes.
- **Read-Only Operation:** PDF generation is read-only, does not mutate reports or source documents, preserves stored audit hashes exactly, and does not emit new audit events.
- **Approval Gate:** Unapproved proposals or nonexistent reports return HTTP 400 or 404.

### 5. Frontend PDF Download
- **UI Integration:** Clean "Download PDF" action within `ApprovedChangeReport.jsx`.
- **State Handling:** Provides visual loading feedback and disables the download action when no approved report exists.
- **Authoritative Backend:** The browser downloads authentic server-generated PDFs without client-side fabrication.

### 6. Workflow Hardening & Evaluation
- **End-to-End Suite:** 16 dedicated hardening tests in `backend/tests/unit/test_phase4_workflow_hardening.py`.
- **Test Results:** 326 passed, 0 failed across all backend unit and API test suites.
- **Evaluation Baseline:** Matches all 8 core benchmark evaluation metrics (94.4% 6D comparison accuracy, 100% difference detection, 100% false-match protection, 1.0 Recall@3, 0.6667 Precision@3, 1.0 Hit Rate@3, 1.0 MRR, 100% Groundedness).

---

## 3. Live External Regulatory Sources

### NLM DailyMed Web Services V2
- **Direct Live Retrieval:** DailyMed is accessed on demand via public REST web services (`https://dailymed.nlm.nih.gov/dailymed/services/v2/`).
- **No Corpus Download:** The application does **NOT** download or bundle the massive DailyMed dataset.
- **Traceability:** Preserves official DailyMed Set IDs, SPL version numbers, publication dates, LOINC section codes, and direct lookup URLs (`https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={setid}`).

### FDA / openFDA Drug Labeling API
- **Direct Live API:** Accessed via official openFDA endpoints (`https://api.fda.gov/drug/label.json`).
- **Metadata Preserved:** Application numbers, NDC, manufacturer, routes of administration, and structured label sections (Indications, Dosage, Warnings, Contraindications).
- **Graceful Error Handling:** Handles empty queries, timeouts, and openFDA 404 ("No matches found") safely.

---

## 4. Technology Stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn, Pydantic v2, Pydantic Settings, HTTPX, SQLite3, ReportLab, Pytest
- **Frontend:** React 19, Vite 8, Vanilla CSS Design System, Lucide React Icons
- **AI / LLM Integration:** OpenAI API (Strictly backend-only; API keys are never exposed to React or the client)

---

## 5. Environment Setup & Configuration

### Prerequisites
- Python 3.10 or higher
- Node.js v18 or higher & npm

### 1. Configure Environment Variables
Create a local `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` to configure your keys (never commit `.env` to Git):

```env
# OpenAI API Key (Backend-only; never exposed to React)
OPENAI_API_KEY=your_openai_api_key_here

# openFDA API Key (Optional; functions with default rate limits without a key)
OPENFDA_API_KEY=

# LangSmith Tracing (Optional)
LANGSMITH_API_KEY=
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=regulatory-content-reuse-finder

# Server & Endpoints
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
DAILYMED_BASE_URL=https://dailymed.nlm.nih.gov/dailymed/services/v2
OPENFDA_BASE_URL=https://api.fda.gov/drug/label.json
REQUEST_TIMEOUT_SECONDS=15.0
```

### 2. Python Environment & Dependencies
Create and activate a virtual environment, then install backend dependencies:

```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend/requirements.txt

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. Frontend Dependencies
Install React frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

---

## 6. Running the Application

### Start the FastAPI Backend
From the project root:

```bash
# Windows
.\.venv\Scripts\uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload

# Linux / macOS
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

- API Base URL: `http://127.0.0.1:8000`
- Interactive Swagger UI: `http://127.0.0.1:8000/docs`
- Health Endpoint: `http://127.0.0.1:8000/health`

### Start the React Frontend
In a separate terminal:

```bash
cd frontend
npm run dev
```

- Frontend URL: `http://localhost:5173`

---

## 7. Testing & Quality Verification

Run the comprehensive automated test suite with pytest:

```bash
# Run unit and API tests (326 tests)
.\.venv\Scripts\pytest -v backend/tests/unit backend/tests/api

# Run live integration tests against DailyMed and openFDA APIs
.\.venv\Scripts\pytest -v backend/tests/integration

# Run full test suite
.\.venv\Scripts\pytest -v backend/tests
```

### Frontend Verification
```bash
cd frontend
npm run lint
npm run build
```

### Evaluation Benchmark
```bash
.\.venv\Scripts\python evaluation/run_evaluation.py
```

---

## 8. Complete Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Server status, source connectivity checks, configuration flags |
| `GET` | `/regulatory/search` | Live search across DailyMed and openFDA with full traceability |
| `GET` | `/regulatory/document/{source}/{id}` | Detailed section retrieval for specific regulatory Set ID |
| `GET` | `/regulatory/sources/status` | Live latency and availability check of external sources |
| `POST` | `/documents/upload` | Parse raw document text/files into recognized regulatory sections |
| `POST` | `/content/analyze` | Evaluate candidates against target section with Agent 1 |
| `POST` | `/content/compare` | Compute structured 6D differences between regulatory texts |
| `POST` | `/review/decision` | Record human regulatory professional decision (`REUSE`, `ADAPT`, `REJECT`) |
| `POST` | `/changes/analyze` | Formulate controlled change proposal via Agent 2 |
| `POST` | `/changes/occurrences` | Detect related cross-section occurrences across documents |
| `POST` | `/changes/occurrences/confirm` | Record human confirmation or exclusion for related occurrences |
| `POST` | `/changes/validate` | Execute deterministic validation rules (`REG-VAL-001` - `REG-VAL-006`) |
| `POST` | `/changes/approve` | Human approval gate; generates finalized `ApprovedChangeReport` |
| `GET` | `/changes/report` | List active change proposals and reports |
| `GET` | `/changes/report/{report_id}/pdf` | Generate and download audit-ready approved change report PDF |
| `GET` | `/history` | View decision history audit trail |
| `GET` | `/audit` | Retrieve all audit events in chronological order |
| `GET` | `/audit/verify` | Verify cryptographic hash chain integrity of the audit trail |
| `GET` | `/audit/{change_id}` | Retrieve audit history for a specific change proposal |

---

## 9. Current System Limitations & Boundaries

- **Ephemeral Ingested Candidate Store:** Uploaded candidate documents and chunks are kept in memory (`IngestedDocumentCandidateStore`) and do not persist across restarts.
- **Ephemeral Vector Store:** Vector embeddings used for similarity ranking are held in-memory.
- **Ephemeral API Caches:** External DailyMed and openFDA search query caches are held in memory.
- **Workflow-Only Persistence:** SQLite persists governance workflow entities (decisions, proposals, occurrences, impact, validation, reports, audit events) rather than raw candidate corpus files.
- **No Synthetic Regulatory Data:** The application does not fabricate synthetic regulatory documents or synthetic clinical labels.
- **Evaluation Baseline Scope:** Evaluation metrics represent current test benchmark results and do not constitute formal regulatory or clinical certification claims.

---

## 10. Phase 4 Git Checkpoint History

- `b9baa7e`: `feat: add approved change report PDF export`
- `e551bba`: `feat: add approved change report PDF download`
- `d1f4ad7`: `test: harden phase 4 end-to-end workflow`
