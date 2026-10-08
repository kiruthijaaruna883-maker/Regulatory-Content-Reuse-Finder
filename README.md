# Regulatory Content Reuse Finder (GPR)

**Domain:** Life Sciences – Regulatory Affairs<br>
**Status:** Phase 7 Complete / Phase 8 Hardened & Verified<br>
**Current Baseline Commit:** `bf04196`<br>
**Architecture:** Strictly Governed Two-Agent Human-in-the-Loop Decision Support<br>

The **Regulatory Content Reuse Finder (GPR)** is an AI-assisted decision support platform purpose-built for Life Sciences regulatory professionals. It accelerates and hardens the authoring, review, and lifecycle maintenance of regulatory dossiers (including clinical study protocols, investigator brochures, package inserts, and labeling documents).

The platform identifies potentially reusable regulatory language from authoritative live sources (NLM DailyMed and openFDA), performs granular 6-dimensional comparative analysis against draft internal text, detects clinical and dosage discrepancies, tracks cross-section occurrences across documents, maintains a tamper-evident cryptographic audit ledger, and generates audit-ready approved change reports and deterministic corrected documents.

> [!IMPORTANT]
> **Human-in-the-Loop Governance:** The application operates strictly as decision support. It does **NOT** autonomously approve regulatory content, unilaterally mutate source regulatory documents, or propagate changes automatically. The human regulatory professional remains the sole, final decision-maker throughout the workflow. Original source documents remain 100% immutable.

---

## 1. Project Overview & Regulatory Problem

### The Challenge in Life Sciences Regulatory Affairs
Regulatory affairs teams face rigorous compliance challenges when drafting and revising clinical dossiers:
- **Discrepancy Risks:** Inconsistencies in dosing regimens, administration instructions, contraindications, or adverse reactions across document sections can trigger critical regulatory rejection (e.g., FDA Complete Response Letters).
- **Redundant Authoring:** Regulatory writers frequently re-author standardized sections that have already been vetted and approved in precedent drug labels or across dossiers.
- **Traceability Gaps:** Manual redlining across disparate documents lacks verifiable provenance, creating inspection vulnerabilities under FDA 21 CFR Part 11 and GxP standards.

### The GPR Solution
GPR provides an auditable, two-agent decision-support framework that:
1. Surfaces vetted regulatory precedents from live DailyMed and openFDA endpoints.
2. Evaluates content similarity across six independent regulatory dimensions.
3. Quantifies deterministic clinical differences (dosages, units, formulations).
4. Enforces strict human decision gates before any change can be formulated or approved.
5. Produces deterministic corrected documents (DOCX, TXT, MD, PDF) while strictly maintaining source document immutability. PDF files are supported as inputs and can produce a newly generated corrected PDF after human approval. The original source PDF remains immutable.

---

## 2. End-to-End Regulatory Workflow

The user workflow follows a transparent, unidirectional decision progression:

```
Source Regulatory Document (DOCX, PDF, TXT, MD)
       │
       ▼
Universal Ingestion & Structure-Preserving Chunking
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
[HUMAN GATE 1: Regulatory Review Decision]
[ REUSE | ADAPT | REJECT ]
       │
       ▼
Agent 2: Regulatory Document Change Agent
(Controlled Change Formulation & Cross-Section Occurrence Detection)
       │
       ▼
[HUMAN GATE 2: Occurrence Confirmation Gate]
[ CONFIRMED | EXCLUDED | PENDING ]
       │
       ▼
Section-Level Impact Analysis (Confirmed Occurrences Only)
       │
       ▼
Deterministic Regulatory Validation Engine (REG-VAL-001 through REG-VAL-006)
(Strictly blocks if any occurrence is PENDING)
       │
       ▼
[HUMAN GATE 3: Final Approval Gate]
(Explicit confirmation: approval_confirmation=true + Approver Identity)
       │
       ▼
Finalized Approved Change Report
       │
       ├─────────────────────────────────────────┬─────────────────────────────────────────┐
       ▼                                         ▼                                         ▼
Tamper-Evident Audit Trail              ReportLab PDF Export                    Deterministic Corrected Document
(SHA-256 Back-Linked Hash Chain)        (Executive Summary PDF)                 (DOCX / TXT / MD / PDF)
       │                                         │                                         │
       ▼                                         ▼                                         ▼
SQLite Workflow Persistence             Browser PDF Download                    Browser Document Download
(backend/data/gpr_workflow.db)          (Audit-Ready Report)                    (Newly Generated Corrected Artifact)
```

---

## 3. Two-Agent Architecture

The system architecture is intentionally and strictly limited to **two specialized agents** operating across separated functional boundaries:

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   TWO-AGENT ARCHITECTURE                                │
├────────────────────────────────────────────┬────────────────────────────────────────────┤
│  Agent 1: RegulatoryContentAnalysisAgent   │   Agent 2: RegulatoryDocumentChangeAgent   │
├────────────────────────────────────────────┼────────────────────────────────────────────┤
│ • Universal ingestion & section parsing    │ • Formulates proposals bound to decisions  │
│ • Live retrieval (DailyMed & openFDA)      │ • Cross-section occurrence detection       │
│ • 6D comparative alignment evaluation      │ • 6D occurrence evidence & recommendations │
│ • Deterministic difference detection       │ • Coordinated impact calculation           │
│ • False-match discrepancy protection       │ • Deterministic validation (REG-VAL-001-6) │
│ • Advisory recommendations & rationale     │ • Final report assembly upon human approval│
│                                            │                                            │
│ CONSTRAINT: Analytical support only.       │ CONSTRAINT: Cannot approve autonomously.   │
│ Does NOT make final regulatory decisions.  │ Does NOT mutate source documents.          │
└────────────────────────────────────────────┴────────────────────────────────────────────┘
```

> [!NOTE]
> No third agent or autonomous execution broker exists in the architecture. Human regulatory professionals execute all binding determinations.

---

## 4. Human-in-the-Loop Governance Gates

Governance boundaries are enforced programmatically across every transition:

1. **Gate 1 — Reviewer Content Decision:**
   - Decisions: `REUSE` (adopt candidate as-is), `ADAPT` (adopt with modified wording), or `REJECT` (discard candidate).
   - If `REJECT` is selected, proposal formulation is strictly blocked.
   - Requires non-empty reviewer identity and clinical justification.

2. **Gate 2 — Occurrence Disposition:**
   - Reviewer marks each discovered related occurrence as `CONFIRMED` or `EXCLUDED`.
   - `CONFIRMED` occurrences are included in coordinated impact and corrected document generation.
   - `EXCLUDED` occurrences remain 100% untouched and are omitted from impact metrics.
   - **Rule REG-VAL-006:** If any occurrence remains in `PENDING` status, report approval is strictly blocked.

3. **Gate 3 — Final Approval Authorization:**
   - Final report approval requires explicit `approval_confirmation: true` (which never defaults to true) and a verified human regulatory approver name.
   - All validation rules (`REG-VAL-001` through `REG-VAL-006`) must pass.

4. **Source Document Immutability:**
   - Retained original document bytes stored in `IngestedDocumentCandidateStore` are never modified.
   - Corrected documents are generated transactionally into a new in-memory byte stream.

---

## 5. Document Support & Format Boundaries

| Format | Ingestion & Parsing | Comparison & Review | Corrected Document Generation | Design Boundary |
|---|---|---|---|---|
| **DOCX** | Full Support | Full Support | **Supported** | Run-level text replacement preserves typography, bold, italics, tables, and section headings. |
| **TXT / MD** | Full Support | Full Support | **Supported** | Section-bounded exact span replacement with UTF-8 encoding. |
| **PDF** | Full Support | Full Support | **Supported** | **Newly generated corrected PDF artifact.** PDF files are supported as inputs and can produce a newly generated corrected PDF after human approval. The original source PDF remains immutable. |
| **DOC (Binary)** | Legacy Ingestion | Full Support | **NOT SUPPORTED (Input-Only)** | Legacy binary DOC requires DOCX conversion for correction. |

### Distinction Between PDF Artifacts
- **Original Source PDF:** Stored immutably in memory (`IngestedDocumentCandidateStore`). The original source PDF bytes are never modified or mutated in-place.
- **Corrected PDF:** A newly generated output artifact (`Corrected_<OriginalName>.pdf`) produced by merging an exact coordinate overlay on copies of affected pages after all human approval gates are satisfied.
- **Approved Change Report PDF:** A separate audit/report artifact generated via ReportLab as an executive summary of the review process (`GET /changes/report/{report_id}/pdf`).

#### Corrected PDF Capabilities and Known Limitations
- **New Artifact Generation:** Corrected PDF is a completely new byte stream artifact, not an in-place mutation of the source document. Unaffected pages are copied without overlays.
- **No Automatic Multi-Page Reflow:** PDF text does not reflow across pages or paragraphs.
- **Safe Replacement Fitting:** The approved replacement text must safely fit within the resolved target region. If the replacement cannot safely fit using deterministic rendering, generation fails cleanly with a controlled error (`TargetResolutionError`) rather than overlapping unrelated text.
- **Text Coordinate Extraction:** Scanned/image-only PDFs without usable text coordinates cannot be resolved for targeted coordinate replacement.

---

## 6. Core Analysis & Comparison Engine

### 1. Six-Dimensional Comparison Engine
Agent 1 evaluates candidate alignment across six distinct regulatory dimensions:
- **Meaning (Semantic):** Evaluates medical and clinical equivalency using vector embeddings and cosine similarity.
- **Template (Boilerplate):** Detects standardized regulatory phrasing and structure compliance.
- **Context (Indication/Scope):** Analyzes patient demographics, therapeutic settings, and clinical context.
- **Structure (Hierarchy):** Evaluates section hierarchy, ordering, and document segmentation.
- **Format (Styling):** Compares bulleting, numbering, phrasing density, and typographic conventions.
- **Key Information (Entities):** Compares dosages, units of measure, active ingredients, and routes of administration.

### 2. Deterministic Difference Detection
The `DifferenceDetectionService` extracts and highlights explicit clinical differences between target and candidate texts, including:
- Numerical dosage disparities (e.g., `10 mg` vs `20 mg`)
- Frequency variations (e.g., `once daily` vs `twice daily`)
- Terminology additions and deletions

### 3. False-Match Protection
Protects against false positive matches where therapeutic wording appears similar but active ingredients or drug entities conflict (e.g., blocking reuse across disparate pharmacological classes).

### 4. Six-Dimensional Occurrence Evidence
Agent 2 scans document sections for cross-section mentions of proposed changes, computing 6-dimensional occurrence scores and offering advisory recommendations (`CONFIRM` vs `EXCLUDE`) grounded in factual rationale.

---

## 7. Deterministic Regulatory Validation Engine

The `ValidationService` applies deterministic rules (`REG-VAL-001` through `REG-VAL-006`) to ensure change proposals meet compliance standards:

| Rule Code | Rule Name | Severity | Deterministic Requirement |
|---|---|---|---|
| **`REG-VAL-001`** | Text Completeness | `ERROR` | Proposed text must not be empty and must provide meaningful regulatory content (minimum 10 characters). |
| **`REG-VAL-002`** | Rationale Presence | `ERROR` | A documented clinical/regulatory rationale is required for every proposed change (minimum 5 characters). |
| **`REG-VAL-003`** | Provenance Citation | `WARNING` | Validates citation of external regulatory evidence trace (`EvidenceTrace`). Flags warning if unlinked. |
| **`REG-VAL-004`** | Decision Linkage | `ERROR` | Proposal must be strictly linked to a valid human reviewer decision identifier (`decision_id`). |
| **`REG-VAL-005`** | Approval Gate Authorization | `ERROR` | Requires explicit human approval confirmation (`approval_confirmation=true`), non-empty approver identity, valid proposals, and absence of rejected proposals. |
| **`REG-VAL-006`** | Unresolved Related Occurrences | `ERROR` | Strictly blocks approval and document generation if any related occurrence remains in `PENDING` status. |

---

## 8. Tamper-Evident Audit Trail & Persistence

### Cryptographic Model
- **Storage:** SQLite persistence at `backend/data/gpr_workflow.db` (`user_version = 2`).
- **Ledger Model:** Append-only SHA-256 hash-chained ledger.
- **Canonical Hash:** Each event computes `event_hash = sha256(canonical_json(event_fields + previous_event_hash))`.
- **Event Lifecycle Covered:**
  - `REVIEWER_DECISION_CREATED`
  - `CHANGE_PROPOSAL_CREATED`
  - `OCCURRENCES_CONFIRMED`
  - `CHANGE_VALIDATED`
  - `CHANGE_APPROVED` / `CHANGE_REJECTED`
  - `APPROVED_REPORT_CREATED`
  - `CORRECTED_DOCUMENT_GENERATED`
- **Verification Endpoint:** `GET /audit/verify` re-computes every cryptographic link from genesis. Any modified event or hash mismatch triggers immediate verification failure.
- **Regulatory Traceability:** Preserves official DailyMed Set IDs, SPL versions, and openFDA application numbers.

---

## 9. Corrected Document Generation

Implemented in `CorrectedDocumentGenerator`:
- **Transactional Generation:** Generates output directly from in-memory retained source bytes.
- **Target Replacement Fidelity:** Run-level paragraph traversal in DOCX; exact character span matching in TXT.
- **Target Resolution Safety:** Zero matches or multiple ambiguous matches fail immediately (`TargetResolutionError`).
- **Preservation of Non-Targeted Content:** Excluded occurrences and surrounding paragraphs remain 100% unaltered.
- **PDF Correction Generation:** Generates a new corrected PDF artifact (`Corrected_<OriginalName>.pdf`) using ReportLab overlay rendering merged onto affected pages while retaining original source PDF bytes completely unmodified. Requests to correct unsupported formats (e.g., legacy `.doc`) raise `UnsupportedFormatError`.
- **Audit Emission:** Successful document generation appends a `CORRECTED_DOCUMENT_GENERATED` audit event containing the artifact's SHA-256 hash.

---

## 10. Five-Stage Frontend Workflow

The React 19 / Vite frontend is organized into 5 unified stages:

1. **Dashboard (`Dashboard.jsx`):** System status indicators for DailyMed and openFDA, key workflow metrics, recent audit preview, and quick candidate lookup.
2. **Document Review (`DocumentReview.jsx`):** Multi-format file ingestion (DOCX, PDF, TXT), section hierarchy visualization, and candidate search initiation.
3. **Candidate Comparison & Decision (`CandidateComparison.jsx`):** 6D alignment radar/scorecards, clinical difference detection, occurrence evidence, advisory recommendations, and human review decision recording (`REUSE`, `ADAPT`, `REJECT`).
4. **Change Review (`ChangeReview.jsx`):** Controlled proposal formulation, occurrence review (`CONFIRMED`, `EXCLUDED`), impact analysis metrics, validation checklist, and human approval authorization gate.
5. **Approved Change Report (`ApprovedChangeReport.jsx`):** Finalized report display, side-by-side diffs, cryptographic audit trail verification, "Download PDF Report", and "Download Corrected Document".

---

## 11. Technology Stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn, Pydantic v2, Pydantic Settings, HTTPX, SQLite3, python-docx, pypdf, ReportLab, Pytest
- **Frontend:** React 19, Vite 8, Vanilla CSS Design System, Lucide React Icons
- **AI / LLM Integration:** OpenAI API (Strictly backend-only; API keys are never exposed to the client)
- **External Data Sources:** NLM DailyMed Web Services v2 (REST), FDA openFDA Drug Labeling API (REST)

---

## 12. Complete API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Server health check, source connectivity status, configuration flags |
| `GET` | `/regulatory/search` | Live search across DailyMed and openFDA with provenance metadata |
| `GET` | `/regulatory/document/{source}/{id}` | Detailed section retrieval for a specific regulatory Set ID or Drug Label |
| `GET` | `/regulatory/sources/status` | Live availability and latency check of external regulatory endpoints |
| `POST` | `/documents/upload` | Parse raw document text/files into structured regulatory sections |
| `POST` | `/content/analyze` | Evaluate candidates against target section using Agent 1 |
| `POST` | `/content/compare` | Compute structured 6D differences between regulatory texts |
| `POST` | `/review/decision` | Record human regulatory decision (`REUSE`, `ADAPT`, `REJECT`) |
| `POST` | `/changes/analyze` | Formulate controlled change proposal via Agent 2 |
| `POST` | `/changes/occurrences` | Detect related cross-section occurrences across document dossier |
| `POST` | `/changes/occurrences/confirm` | Record human confirmation or exclusion for related occurrences |
| `POST` | `/changes/validate` | Execute deterministic validation rules (`REG-VAL-001` - `REG-VAL-006`) |
| `POST` | `/changes/approve` | Human approval gate; generates finalized `ApprovedChangeReport` |
| `GET` | `/changes/report` | List active change proposals and reports |
| `GET` | `/changes/report/{report_id}/pdf` | Generate and download audit-ready approved change report PDF |
| `POST` | `/changes/report/{report_id}/corrected-document` | Generate and download corrected regulatory document (DOCX/TXT/MD/PDF) |
| `GET` | `/history` | Retrieve session decision history |
| `GET` | `/audit` | Retrieve chronological workflow audit events |
| `GET` | `/audit/verify` | Verify cryptographic SHA-256 hash chain integrity |
| `GET` | `/audit/{change_id}` | Retrieve audit history for a specific change proposal |

---

## 13. Testing & Verification

### 1. Automated Test Suite
- **Backend Test Suite:** **458 passed**, 0 failed (`pytest backend/tests`).
  - Unit tests: models, parsers, chunking, compatibility, candidate store, controlled changes, deep comparison, audit, occurrences, PDF report, persistence, workflow hardening, occurrence evidence, advisory recommendations, corrected document generator, and document ID preservation.
  - API & Integration tests: health, regulatory endpoints, live sources.
- **Frontend Code Quality:**
  - `oxlint`: 0 warnings, 0 errors across all frontend source files.
  - `vite build`: Production client bundle compiles cleanly with 0 errors.

### 2. Phase 8A Evaluation Benchmark (`evaluation/run_evaluation.py`)
Run the standalone evaluation runner from project root:
```bash
.\.venv\Scripts\python.exe evaluation/run_evaluation.py
```

**Measured Benchmark Results:**
- **6-Dimensional Comparison Accuracy:** **94.4%** (Honest measured benchmark result)
  - Meaning: 100.0% (3/3)
  - Template: 66.7% (2/3)
  - Context: 100.0% (3/3)
  - Structure: 100.0% (3/3)
  - Format: 100.0% (3/3)
  - Key Information: 100.0% (3/3)
- **Deterministic Difference Detection Accuracy:** **100.0%** (4/4 attributes)
- **False-Match Protection Accuracy:** **100.0%** (Confusion matrix: TP: 3, TN: 1, FP: 0, FN: 0)
- **Retrieval & Groundedness Metrics:**
  - Recall@3: **1.0**
  - Precision@3: **0.6667**
  - Hit Rate@3: **1.0**
  - Mean Reciprocal Rank (MRR): **1.0**
  - Groundedness Accuracy: **100.0%**
- **Governance Validation (`REG-VAL-001` - `REG-VAL-006`):** **100.0%** (13/13 checks passed)
- **Pending / Approval Gate Enforcement:** **100.0%** (6/6 checks passed)
- **Audit Hash-Chain Integrity & Tamper Detection:** **100.0%** (3/3 checks passed)
- **Corrected Document Generation Fidelity:** **100.0%** (6/6 checks passed)
- **Source Document Immutability:** **100.0%** (2/2 checks passed; SHA-256 identical before and after)
- **PDF Corrected Document Fidelity:** **100.0%** (4/4 checks passed; valid PDF generated, replacement confirmed, source hash immutable)

---

## 14. Project Structure

```text
GPR/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── content_analysis_agent.py   # Agent 1: Regulatory analysis & retrieval
│   │   │   └── document_change_agent.py    # Agent 2: Change proposals & occurrences
│   │   ├── models/                         # Pydantic v2 data contracts
│   │   ├── persistence/
│   │   │   └── sqlite_store.py             # SQLite persistence & SHA-256 audit ledger
│   │   ├── routes/                         # FastAPI route controllers
│   │   └── services/
│   │       ├── candidate_store.py          # Retained original source storage
│   │       ├── corrected_document_generator.py # In-memory DOCX/TXT/MD/PDF correction generator
│   │       ├── multi_dimensional_comparator.py # 6D comparison service
│   │       ├── pdf_generator.py            # ReportLab approved change report PDF exporter
│   │       ├── validation.py               # REG-VAL-001 through REG-VAL-006 engine
│   │       └── ...
│   └── tests/                              # 458 automated backend tests
├── evaluation/
│   ├── datasets/                           # Ground-truth benchmark datasets (JSON)
│   ├── metrics.py                          # Mathematical evaluation metric formulas
│   └── run_evaluation.py                   # 10-section automated evaluation runner
├── frontend/
│   ├── src/
│   │   ├── components/                     # 5-stage UI workflow components
│   │   ├── services/api.js                 # Frontend API client
│   │   └── App.jsx                         # Main application container
│   ├── package.json
│   └── vite.config.js
└── README.md                               # Authoritative system documentation
```

---

## 15. Running the Application

### 1. Start the FastAPI Backend
```bash
# From workspace root
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
- API Base URL: `http://127.0.0.1:8000`
- Swagger Documentation: `http://127.0.0.1:8000/docs`
- Health Endpoint: `http://127.0.0.1:8000/health`

### 2. Start the React Frontend
```bash
# From workspace root in a separate terminal
cd frontend
npm run dev
```
- Frontend Web App: `http://localhost:5173`
