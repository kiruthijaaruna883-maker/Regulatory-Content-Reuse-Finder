# Regulatory Content Reuse Finder

**Domain:** Life Sciences – Regulatory Affairs  
**Status:** V1 Foundation (Meta Prompt 1 Complete)

The **Regulatory Content Reuse Finder** is an AI-assisted application designed for Life Sciences regulatory professionals. It assists in discovering potentially reusable regulatory content from live authoritative sources, comparing draft documents against established precedents, highlighting differences in clinical terminology and dosage, preserving complete source traceability, and providing a controlled framework for document change proposals.

> [!IMPORTANT]
> **Human-in-the-Loop Governance:** The application does **NOT** autonomously approve regulatory content or unilaterally rewrite regulatory dossiers. The human regulatory professional remains the sole, final decision-maker.

---

## 1. System Architecture

The complete system follows a strictly governed **Two-Agent Architecture**:

```
Draft Document (Internal)
      │
      ▼
Section Extraction
      │
      ▼
Agent 1: Regulatory Content Analysis Agent ────► Live Queries (NLM DailyMed & openFDA)
      │                                                │
      ├────────────────────────────────────────────────┘
      ▼
Candidate Comparison & Difference Detection
(Meaning, Structure, Format, Key Information, LOINC Codes)
      │
      ▼
Human Regulatory Review Gateway
[ REUSE | ADAPT | REJECT ]
      │
      ▼
Agent 2: Regulatory Document Change Agent
(Controlled Change Formulation & Occurrence Tracking)
      │
      ▼
Regulatory Validation Engine
      │
      ▼
Final Human Approval & Sign-Off
      │
      ▼
Approved Change Report & Audit Trail
```

### Agent Roles

1. **Agent 1 — Regulatory Content Analysis Agent:**
   - Understands regulatory document structure and classifies content into standard sections.
   - Coordinates live retrieval against external regulatory repositories.
   - Detects differences (additions, deletions, modifications, numerical dosage disparities).
   - Generates auditable evidence traces to authoritative source records.
   - **Constraint:** Does *not* make the final Reuse / Adapt / Reject decision.

2. **Agent 2 — Regulatory Document Change Agent:**
   - Formulates controlled change proposals strictly reflecting authorized human decisions.
   - Identifies related occurrences across documents and assesses impact.
   - Validates proposals against regulatory documentation integrity rules.
   - Prepares audit-ready change reports.
   - **Constraint:** Produces controlled proposals; does *not* autonomously overwrite files.

---

## 2. Live External Regulatory Sources

### NLM DailyMed Web Services V2
- **Direct Live Retrieval:** DailyMed is accessed on demand via public REST web services (`https://dailymed.nlm.nih.gov/dailymed/services/v2/`).
- **No Corpus Download:** The application does **NOT** download or bundle the massive DailyMed dataset.
- **Traceability:** Preserves official DailyMed Set IDs, SPL version numbers, publication dates, LOINC section codes, and direct lookup URLs (`https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={setid}`).

### FDA / openFDA Drug Labeling API
- **Direct Live API:** Accessed via official openFDA endpoints (`https://api.fda.gov/drug/label.json`).
- **Metadata Preserved:** Application numbers, NDC, manufacturer, routes of administration, and structured label sections (Indications, Dosage, Warnings, Contraindications).
- **Graceful Error Handling:** Handles empty queries, timeouts, and openFDA 404 ("No matches found") safely.

---

## 3. Technology Stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn, Pydantic v2, Pydantic Settings, HTTPX, Pytest
- **Frontend:** React, Vite, Vanilla CSS Design System, Lucide Icons
- **AI / LLM Integration:** OpenAI API (Strictly backend-only; API keys are never exposed to React or the client)

---

## 4. Environment Setup & Configuration

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

## 5. Running the Application

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

## 6. Testing & Quality Verification

Run the comprehensive automated test suite with pytest:

```bash
# Run unit and API tests
.\.venv\Scripts\pytest -v backend/tests/unit backend/tests/api

# Run live integration tests against DailyMed and openFDA APIs
.\.venv\Scripts\pytest -v backend/tests/integration

# Run entire test suite
.\.venv\Scripts\pytest -v backend/tests
```

### Test Coverage Highlights
- Configuration loading, default validation, and secret masking
- `RegulatoryContentItem` model serialization and metadata preservation
- DailyMed SPL XML parsing and LOINC code extraction
- openFDA response parsing and 404 empty-result handling
- Deterministic content matching and Jaccard token overlap ranking
- Difference detection across numerical dosage, structural length, and clinical phrasing
- Human reviewer decision recording and controlled change proposal formulation
- API endpoints: `/health`, `/regulatory/search`, `/documents/upload`, `/review/decision`, `/changes/*`
- Live integration queries validating real connectivity with NLM DailyMed and FDA openFDA

---

## 7. Initial Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Server status, source connectivity checks, configuration flag |
| `GET` | `/regulatory/search` | Live search across DailyMed and openFDA with traceability |
| `GET` | `/regulatory/document/{source}/{id}` | Detailed section retrieval for specific regulatory Set ID |
| `GET` | `/regulatory/sources/status` | Live latency and availability check of external sources |
| `POST` | `/documents/upload` | Parse raw document text into recognized regulatory sections |
| `POST` | `/content/analyze` | Evaluate candidates against target section with Agent 1 |
| `POST` | `/content/compare` | Compute structured differences between two regulatory texts |
| `POST` | `/review/decision` | Record human regulatory professional decision (Reuse, Adapt, Reject) |
| `POST` | `/changes/analyze` | Formulate controlled change proposal via Agent 2 |
| `POST` | `/changes/validate` | Validate change proposal compliance rules |
| `POST` | `/changes/approve` | Finalize human approval into authorized change report |
| `GET` | `/changes/report` | List active change proposals |
| `GET` | `/history` | View decision history audit trail |

---

## 8. Meta Prompt 1 Completion Notice

This release satisfies all requirements of Meta Prompt 1. Full RAG vector indexing, embedding models, autonomous draft generation, and external cloud deployment remain intentionally deferred to subsequent project phases.
