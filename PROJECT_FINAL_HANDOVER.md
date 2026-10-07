# Project Final Handover: Regulatory Content Reuse Finder (GPR)

**Document Version:** 1.0.0  
**Phase:** Phase 8C — Final Project Handover Documentation  
**Current Baseline Commit:** `bf04196`  
**Repository Branch:** `main`  
**Date of Handover:** October 2026  
**Audience:** Project Leadership, Regulatory Affairs Reviewers, Engineering Maintainers, Demonstration Teams, and Solution Architects  

---

## 1. Project Identity

- **Project Name:** Regulatory Content Reuse Finder
- **Project Short Name:** GPR (Global Provenance & Regulatory Reuse)
- **Domain:** Life Sciences / Regulatory Affairs / Clinical Documentation
- **Core Purpose:**  
  The Regulatory Content Reuse Finder (GPR) is an AI-assisted, strictly governed decision-support platform designed for Life Sciences regulatory affairs professionals. It assists in authoring, reviewing, and maintaining regulatory dossiers—such as clinical study protocols, investigator brochures, package inserts, and structured product labels (SPL)—by identifying precedent regulatory language from authoritative sources (NLM DailyMed and US FDA openFDA), evaluating candidate alignment across six dimensions, identifying explicit clinical differences, tracking cross-section occurrences, and generating deterministic corrected documents while enforcing human authorization, tamper-evident auditability, and original source immutability.

---

## 2. Problem Statement

In Life Sciences regulatory operations, drafting and updating submissions is highly repetitive, heavily regulated, and prone to costly human errors:

1. **Repeated Regulatory Content Across Dossiers:**  
   Standardized regulatory text—such as dosing regimens, adverse reaction warnings, contraindications, and storage conditions—is repeatedly authored across multiple documents and submissions.
2. **Difficulty Finding Precedent Language:**  
   Regulatory writers often lack rapid, structured access to approved, precedent wording from authoritative regulatory drug labels, resulting in ad-hoc copy-pasting or unnecessary re-authoring.
3. **Unidentified Clinical Discrepancies:**  
   Subtle differences in numerical dosages (e.g., `10 mg` vs `20 mg`), administration frequencies (e.g., `once daily` vs `twice daily`), or patient demographics across sections often go unnoticed during manual review, triggering critical FDA Complete Response Letters (CRLs) or inspection findings.
4. **Uncoordinated Downstream Occurrences:**  
   When a regulatory statement is updated in one section (e.g., "Dosage and Administration"), corresponding mentions in related sections (e.g., "Highlights", "Patient Counseling", "Clinical Pharmacology") frequently remain unupdated or inconsistent.
5. **Need for Controlled Adaptation:**  
   Regulatory text rarely transfers 100% verbatim; it frequently requires controlled adaptation (e.g., adapting an adult indication to a pediatric formulation) accompanied by a mandatory clinical rationale.
6. **Mandatory Human Approval and Traceability:**  
   Regulatory submissions require compliance with FDA 21 CFR Part 11 and GxP standards. Black-box autonomous AI agents cannot legally approve regulatory dossiers. Every change must require human authorization, verifiable external provenance, and a tamper-evident audit ledger.

> [!NOTE]
> **Strict Decision Support:** GPR does not replace regulatory professionals or autonomously alter regulatory filings. It provides transparent, evidence-backed decision support where human professionals retain sole authority.

---

## 3. Solution Overview

GPR provides a strictly governed, unidirectional review pipeline that connects internal draft documents with authoritative regulatory repositories.

```
Source Document (DOCX, PDF, TXT, MD, DOC)
       │
       ▼
Universal Ingestion & Structure-Preserving Chunking
       │
       ▼
Agent 1: Regulatory Content Analysis Agent ────► External Queries (NLM DailyMed & openFDA)
       │                                                 │
       ├─────────────────────────────────────────────────┘
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
(Controlled Proposal Formulation & Cross-Section Occurrence Detection)
       │
       ▼
[HUMAN GATE 2: Occurrence Confirmation Gate]
[ CONFIRMED | EXCLUDED | PENDING ]
       │
       ▼
Section-Level Coordinated Impact Analysis (Confirmed Occurrences Only)
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
Approved Change Report
       │
       ├─────────────────────────────────────────┬─────────────────────────────────────────┐
       ▼                                         ▼                                         ▼
Tamper-Evident Audit Trail              ReportLab PDF Export                    Deterministic Corrected Document
(SHA-256 Back-Linked Hash Chain)        (Executive Summary PDF)                 (DOCX / TXT / MD Only)
       │                                         │                                         │
       ▼                                         ▼                                         ▼
SQLite Workflow Persistence             Browser PDF Download                    Browser Document Download
(backend/data/gpr_workflow.db)          (Audit-Ready Report)                    (PDF In-Place Editing Blocked)
```

---

## 4. Architecture

The system follows a modular architecture separating analytical reasoning from controlled document mutation, strictly governed by human approval checkpoints.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   TWO-AGENT ARCHITECTURE                               │
├───────────────────────────────────────────┬────────────────────────────────────────────┤
│  Agent 1: RegulatoryContentAnalysisAgent  │   Agent 2: RegulatoryDocumentChangeAgent   │
│  (backend/app/agents/                     │   (backend/app/agents/                     │
│   content_analysis_agent.py)              │    document_change_agent.py)               │
├───────────────────────────────────────────┼────────────────────────────────────────────┤
│ • Ingestion & section tree parsing        │ • Formulates proposals bound to decisions  │
│ • RAG retrieval across DailyMed & openFDA │ • Cross-section occurrence detection       │
│ • 6-dimensional comparative analysis      │ • 6D occurrence evidence & recommendations │
│ • Deterministic clinical diff detection   │ • Coordinated impact calculation           │
│ • False-match discrepancy protection      │ • Executes validation (REG-VAL-001 - 006)  │
│ • Advisory recommendations & rationale    │ • Compiles ApprovedChangeReport            │
│                                           │                                            │
│ CONSTRAINT: Purely analytical support.    │ CONSTRAINT: Purely operational executor.   │
│ Cannot approve regulatory text.           │ Cannot approve without human authorization.│
└───────────────────────────────────────────┴────────────────────────────────────────────┘
```

### Key Architectural Components

1. **Exactly Two Specialized Agents:**
   - **`RegulatoryContentAnalysisAgent`** (`backend/app/agents/content_analysis_agent.py`): Performs content ingestion, live retrieval, 6D comparison, deterministic difference analysis, and advisory recommendation generation.
   - **`RegulatoryDocumentChangeAgent`** (`backend/app/agents/document_change_agent.py`): Formulates change proposals bound to human decisions, scans documents for related occurrences across 4 detection layers, evaluates occurrence evidence, computes impact, and validates proposals.
   - *No third agent or autonomous orchestrator exists.*
2. **FastAPI Backend (`backend/app/main.py`):**
   - High-performance asynchronous REST API in Python 3.10+.
   - Modular routers: `candidate_discovery.py`, `comparison.py`, `document_review.py`, `regulatory.py`, `audit.py`.
   - Global exception handling preventing sensitive data or secret leakage.
3. **React 19 / Vite Frontend (`frontend/src/`):**
   - 5-stage unified regulatory workflow interface.
   - Vanilla CSS custom design system (no Tailwind dependencies).
   - High-contrast regulatory status badges, scorecards, and radar visualizations.
4. **SQLite Workflow & Audit Persistence (`backend/app/persistence/sqlite_store.py`):**
   - File-based SQLite persistence (`backend/data/gpr_workflow.db`, `user_version = 2`).
   - Append-only cryptographic ledger with SHA-256 back-linked hash chaining.
5. **Retained Source Storage (`backend/app/services/candidate_store.py`):**
   - `IngestedDocumentCandidateStore` retains original source document bytes in memory/runtime storage to enable deterministic downstream correction without modifying original inputs.
6. **Deterministic Document Generation Services:**
   - `CorrectedDocumentGenerator`: Run-level DOCX and span-level TXT text replacement.
   - `PDFReportGenerator`: ReportLab executive PDF summary export.
7. **External Regulatory Integrations:**
   - **NLM DailyMed REST API v2:** Structured Product Labeling (SPL) XML retrieval and drug label search.
   - **US FDA openFDA Drug Labeling API:** Regulatory labeling JSON queries.

---

## 5. Detailed Workflow

The end-to-end workflow consists of 13 clearly defined stages:

1. **Upload:**  
   The user uploads an internal draft regulatory document (DOCX, PDF, TXT, MD, or legacy DOC) via the frontend or API (`POST /documents/upload` or `POST /documents/ingest`).
2. **Ingestion & Parsing:**  
   The backend extracts plain text, identifies section headings, constructs a hierarchical section tree, and caches the raw source bytes in `IngestedDocumentCandidateStore` under a unique `document_id`.
3. **Candidate Discovery:**  
   The user or system triggers candidate search (`POST /candidates/search` or `POST /regulatory/search`). Agent 1 queries ingested document stores and live DailyMed/openFDA endpoints to retrieve matching regulatory precedents.
4. **6-Dimensional Comparison:**  
   Agent 1 evaluates candidate alignment across six dimensions (Meaning, Template, Context, Structure, Format, Key Information), extracts deterministic clinical differences (dosages, frequencies, entities), protects against false matches, and presents an advisory recommendation with rationale.
5. **Human Decision (Gate 1):**  
   The human regulatory professional reviews the candidate and records an explicit decision (`POST /review/decision`): `REUSE`, `ADAPT` (with mandatory adaptation instructions), or `REJECT`. If `REJECT` is selected, proposal formulation is blocked.
6. **Agent 2 Change Analysis:**  
   Agent 2 formulates a formal `ProposedChange` linked to the human `decision_id` (`POST /changes/analyze`). For `ADAPT` decisions, Agent 2 generates advisory wording incorporating the reviewer's instructions.
7. **Occurrence Detection:**  
   Agent 2 scans the entire document dossier across 4 detection layers (`POST /changes/occurrences`) to locate all other sections containing related mentions of the target phrase.
8. **Human Occurrence Confirmation (Gate 2):**  
   Agent 2 calculates 6D occurrence evidence and advisory recommendations (`CONFIRM` vs `EXCLUDE`). The human reviewer reviews each occurrence and marks it as `CONFIRMED` or `EXCLUDED` (`POST /changes/occurrences/confirm`).
9. **Regulatory Validation Engine:**  
   The system runs deterministic validation rules `REG-VAL-001` through `REG-VAL-006` (`POST /changes/validate`). If any occurrence remains `PENDING`, rule `REG-VAL-006` fails with severity `ERROR`.
10. **Final Human Approval (Gate 3):**  
    The human approver submits authorization (`POST /changes/approve`) with `approval_confirmation: true` and a non-empty `approver_name`. The system verifies that no rejected proposals are present and all occurrences are resolved.
11. **Approved Change Report:**  
    An immutable `ApprovedChangeReport` is persisted in SQLite. The user can export an executive audit summary as a PDF (`GET /changes/report/{report_id}/pdf`).
12. **Corrected Document Generation:**  
    For eligible editable formats (DOCX, TXT, MD), the user clicks "Download Corrected Document" (`POST /changes/report/{report_id}/corrected-document`). The system applies confirmed changes onto the retained source bytes and returns a new document. PDF correction requests are cleanly rejected.
13. **Audit Trail Verification:**  
    Every action emits an append-only event into the SHA-256 hash-chained ledger. Reviewers verify chain integrity on demand (`GET /audit/verify`).

---

## 6. Human Governance

The platform enforces three mandatory human governance checkpoints:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              THREE HUMAN GOVERNANCE GATES                              │
├────────────────────────────┬────────────────────────────┬──────────────────────────────┤
│           GATE 1           │           GATE 2           │            GATE 3            │
│  Candidate Review Decision │   Occurrence Disposition   │  Final Report Authorization  │
├────────────────────────────┼────────────────────────────┼──────────────────────────────┤
│ • Reviewer selects:        │ • Reviewer marks each      │ • Explicit payload field:    │
│   - REUSE (adopt as-is)    │   detected occurrence as:  │   approval_confirmation=true │
│   - ADAPT (with notes)     │   - CONFIRMED              │   (NEVER defaults to true)   │
│   - REJECT (discard)       │   - EXCLUDED               │ • Verified human approver    │
│ • Requires reviewer name   │ • PENDING status strictly  │   identity required          │
│ • REJECT blocks proposals  │   blocks Gate 3 approval   │ • Validates REG-VAL-001 to 6 │
└────────────────────────────┴────────────────────────────┴──────────────────────────────┘
```

### Governance Principles Enforced in Code

- **No Autonomous Approvals:** Neither Agent 1 nor Agent 2 has authority to approve proposals, make regulatory decisions, or write files to disk without human authorization.
- **Pending Occurrences Block Approvals:** Under rule `REG-VAL-006`, if even a single related occurrence remains in `PENDING` status, final report approval and document correction are blocked with `HTTP 409 Conflict`.
- **Excluded Content Isolation:** Any occurrence marked `EXCLUDED` is completely omitted from change application; surrounding text remains 100% unaltered.
- **Source Byte Immutability:** Original uploaded document bytes are retained as read-only references; the application never overwrites or mutates source files.

---

## 7. Agent Details

### Agent 1: RegulatoryContentAnalysisAgent

- **Module Path:** `backend/app/agents/content_analysis_agent.py`
- **Class Name:** `RegulatoryContentAnalysisAgent`
- **Core Responsibility:**  
  Analytical decision support for ingestion, external retrieval, multi-dimensional alignment evaluation, clinical difference detection, and advisory candidate recommendations.
- **Inputs:**  
  Target section text, section metadata, search queries, candidate text snippets, and optional live source filters (`dailymed`, `openfda`).
- **Outputs:**  
  `ContentComparisonResult` containing 6D alignment scores (0.0 to 1.0), list of detected `DifferenceItem` entries (dosages, units, formulations), false-match discrepancy flags, advisory recommendation (`REUSE`, `ADAPT`, `REJECT`), and structured rationale.
- **Workflow Position:**  
  Stages 2, 3, and 4 (Document Ingestion through Candidate Comparison).
- **Governance Boundary:**  
  Advisory only. Outputs do not alter workflow state or record binding decisions.

### Agent 2: RegulatoryDocumentChangeAgent

- **Module Path:** `backend/app/agents/document_change_agent.py`
- **Class Name:** `RegulatoryDocumentChangeAgent`
- **Core Responsibility:**  
  Operational formulation of change proposals, cross-section occurrence detection across 4 layers, occurrence evidence scoring, coordinated impact calculation, regulatory validation execution, and report compilation.
- **Inputs:**  
  Recorded `ReviewerDecision`, document section tree, target phrase, occurrence confirmation dispositions, and final approval request payload.
- **Outputs:**  
  `ProposedChange` objects, list of `RelatedOccurrence` objects with 6D evidence, `ChangeImpact` assessments, `ValidationFinding` lists, and finalized `ApprovedChangeReport`.
- **Workflow Position:**  
  Stages 6, 7, 8, 9, and 10 (Proposal Formulation through Approved Change Report Assembly).
- **Governance Boundary:**  
  Operational executor only. Requires human input for decisions, occurrence dispositions, and final authorization.

---

## 8. Comparison and Occurrence Logic

### Six-Dimensional Comparison Engine

Agent 1 evaluates candidate regulatory text against internal target text across six orthogonal dimensions:

1. **Meaning (Semantic):** Evaluates clinical and pharmacological equivalence using semantic embeddings and cosine similarity.
2. **Template (Boilerplate):** Assesses structural compliance with standard regulatory boilerplate phrasing and standard headings.
3. **Context (Indication/Scope):** Analyzes patient demographics (e.g., pediatric vs adult), therapeutic indications, and clinical setting.
4. **Structure (Hierarchy):** Evaluates section hierarchy, bulleted hierarchy, and paragraph organization.
5. **Format (Styling):** Compares bulleting style, typography density, numbering conventions, and table structures.
6. **Key Information (Entities):** Analyzes critical clinical entities: active pharmaceutical ingredients (API), dosage strengths, units of measure, routes of administration, and dosing frequencies.

### Deterministic Difference Detection

The `DifferenceDetectionService` extracts and highlights explicit clinical differences:
- Numerical dosage disparities (e.g., `10 mg` vs `20 mg`)
- Frequency variations (e.g., `once daily` vs `twice daily`)
- Terminology additions and deletions
- Route and formulation differences (e.g., `oral tablet` vs `intravenous injection`)

### False-Match Protection

Protects against dangerous false-positive matches where text exhibits high superficial linguistic similarity but active ingredients, pharmacological classes, or critical warnings conflict. Such candidates are flagged with high-severity warnings and advisory `REJECT` recommendations.

### 4-Layer Occurrence Detection

Agent 2 scans document dossiers across four complementary detection layers:
1. **Layer 1 — Exact Match:** Case-sensitive and whitespace-normalized verbatim string matching.
2. **Layer 2 — Normalized Match:** Case-insensitive, punctuation-stripped lexical matching.
3. **Layer 3 — Structured Match:** Entity-aware matching targeting dosages, units, and active ingredients.
4. **Layer 4 — Semantic Match:** Vector similarity matching identifying conceptual paraphrasing across distant sections.

### Coordinated Impact Analysis

When occurrences are detected, the system does not automatically apply changes:
- `PENDING`: Displayed with 6D evidence radar; blocks final validation and approval.
- `CONFIRMED`: Added to `affected_sections` and scheduled for coordinated text replacement in corrected document generation.
- `EXCLUDED`: Excluded from impact metrics; preserved 100% unaltered in corrected document generation.

---

## 9. Validation Rules

The `ValidationService` (`backend/app/services/validation.py`) enforces six deterministic regulatory validation rules:

| Rule ID | Rule Name | Severity | Practical Regulatory Purpose & Deterministic Check |
|---|---|---|---|
| **`REG-VAL-001`** | Text Completeness | `ERROR` | Ensures the proposed regulatory change text is non-empty and provides substantive regulatory content (minimum 10 characters). Blocks accidental blanking of regulatory text. |
| **`REG-VAL-002`** | Rationale Presence | `ERROR` | Enforces regulatory compliance requiring documented justification for every modification (minimum 5 characters). Changes without documented rationale fail. |
| **`REG-VAL-003`** | Provenance Citation | `WARNING` | Verifies whether the change links to an external regulatory evidence trace (`EvidenceTrace` with source URL, DailyMed Set ID, or openFDA record). Emits an auditable warning if unlinked. |
| **`REG-VAL-004`** | Decision Linkage | `ERROR` | Confirms the proposed change is strictly bound to a valid human reviewer decision identifier (`decision_id`). Prevents unprompted or unanchored change formulation. |
| **`REG-VAL-005`** | Approval Gate Authorization | `ERROR` | Enforces final authorization requirements: requires explicit `approval_confirmation=true`, a non-empty human approver identity, at least one authorized proposal, and zero rejected proposals. |
| **`REG-VAL-006`** | Unresolved Related Occurrences | `ERROR` | Strictly blocks report approval and corrected document generation if any related occurrence remains in `PENDING` status. Guarantees that all cross-section mentions have been explicitly reviewed as `CONFIRMED` or `EXCLUDED`. |

---

## 10. Audit and Traceability

### Cryptographic Model & Ledger Design

- **Storage Engine:** SQLite persistence at `backend/data/gpr_workflow.db` (`user_version = 2`).
- **Ledger Architecture:** Append-only SHA-256 back-linked hash chain.
- **Canonical Hash Computation:**  
  Each event computes:  
  $$\text{event\_hash} = \text{SHA-256}(\text{canonical\_json}(\text{event\_fields} + \text{previous\_event\_hash}))$$
  Genesis event links to an initial zero hash string.
- **Tamper Detection:**  
  Modifying any historical record (reviewer identity, timestamps, proposed wording, or event hash) invalidates the hash chain from that point forward.
- **Audit Verification Endpoint:**  
  `GET /audit/verify` re-computes every cryptographic link from genesis. Any mismatch returns `verified: false` along with the exact tampering location.
- **Inspection Endpoints:**
  - `GET /audit`: Chronological stream of all regulatory workflow events.
  - `GET /audit/verify`: Cryptographic verification result.
  - `GET /audit/{change_id}`: Audit history filtered by specific change proposal.
- **Regulatory Significance:**  
  Supports FDA 21 CFR Part 11 and GxP inspection readiness by establishing non-repudiable provenance linking internal edits to official DailyMed Set IDs, SPL versions, and openFDA application numbers.

---

## 11. Document Handling

| Format | Ingestion & Parsing | Comparison & Review | Corrected Source Output | Engineering Notes |
|---|---|---|---|---|
| **DOCX** | Full Support | Full Support | **SUPPORTED** | In-memory XML paragraph and run-level traversal; preserves typography, bold, italics, tables, and section structure. |
| **TXT / MD** | Full Support | Full Support | **SUPPORTED** | Exact character span replacement with UTF-8 encoding; surrounding text remains untouched. |
| **PDF** | Full Support | Full Support | **NOT SUPPORTED (Input-Only)** | **PDF is strictly input-only.** Source PDF is parsed and reviewed, but in-place corrected PDF generation is explicitly rejected (`HTTP 400` / `UnsupportedFormatError`). |
| **DOC (Binary)** | Legacy Support | Full Support | **NOT SUPPORTED (Input-Only)** | Legacy binary DOC files are ingested for review, but binary in-place modification is not supported. |

### Critical Clarifications
1. **PDF is Input-Only:** Source PDFs can be uploaded, parsed into sections, compared against candidates, and referenced in approved reports. However, the system **never modifies source PDFs** and **never generates corrected PDFs**.
2. **Approved Change Report PDF vs Source Document:**
   - The *Approved Change Report PDF* is a separate, audit-ready summary report generated via ReportLab (`GET /changes/report/{report_id}/pdf`).
   - The *Corrected Source Document* is a modified version of the original file, supported only for editable formats (DOCX, TXT, MD).
3. **Original Source Immutability:** Retained source bytes in the candidate store are never overwritten or mutated on disk. Corrected documents are generated transactionally into new in-memory byte streams.

---

## 12. Corrected Document Generation

Implemented in `CorrectedDocumentGenerator` (`backend/app/services/corrected_document_generator.py`):

1. **Source Bytes Retention:**  
   During initial upload, raw file bytes are retained in `IngestedDocumentCandidateStore` under the document's unique `document_id`.
2. **Deterministic Execution:**  
   Document correction applies confirmed change proposals onto a fresh copy of the retained bytes. Given identical inputs, it produces byte-identical output artifacts.
3. **Run-Level DOCX Traversal:**  
   Traverses `python-docx` paragraphs and table cells at the text run level, substituting target text while preserving surrounding font properties, bold, italics, bullet styles, and document hierarchy.
4. **Target Resolution Safety:**  
   If target text has 0 matches or multiple ambiguous matches in the target section, generation fails safely (`TargetResolutionError` / `HTTP 409 Conflict`) rather than corrupting the file.
5. **Preservation of Non-Targeted & Excluded Content:**  
   Occurrences marked `EXCLUDED` and all non-targeted paragraphs remain 100% unaltered.
6. **Input-Only Guards:**  
   Requests to generate corrected documents for PDF or legacy `.doc` files raise `UnsupportedFormatError` with descriptive error messages.
7. **Output Naming Convention:**  
   Returns downloadable attachments named `Corrected_<original_filename>` (e.g., `Corrected_Protocol_A.docx`).
8. **Audit Emission:**  
   Successful generation emits a `CORRECTED_DOCUMENT_GENERATED` audit event containing the SHA-256 hash of the generated artifact.

---

## 13. UI Workflow

The React 19 frontend is organized into 5 unified stages:

```
[ Stage 1: Dashboard ]
       │
       ▼
[ Stage 2: Document Review ]
       │
       ▼
[ Stage 3: Candidate Comparison & Decision ]
       │
       ▼
[ Stage 4: Change Review ]
       │
       ▼
[ Stage 5: Approved Change Report ]
```

1. **Stage 1 — Dashboard (`Dashboard.jsx`):**  
   Provides an executive operational overview: live connectivity and latency status for DailyMed and openFDA, summary counts of recent proposals, quick regulatory search bar, and recent audit activity feed.
2. **Stage 2 — Document Review (`DocumentReview.jsx`):**  
   Facilitates drag-and-drop file upload (DOCX, PDF, TXT) or text pasting. Renders the parsed section hierarchy tree, displays section text, and allows reviewers to trigger candidate searches for specific sections.
3. **Stage 3 — Candidate Comparison & Decision (`CandidateComparison.jsx`):**  
   Presents candidate regulatory precedents side-by-side with target draft text. Features 6D alignment scorecards, visual diff highlighting (dosages, units, terms), advisory recommendations with rationale, and the **Human Gate 1** decision form (`REUSE`, `ADAPT`, `REJECT`).
4. **Stage 4 — Change Review (`ChangeReview.jsx`):**  
   Displays formulated change proposals, detected cross-section occurrences across 4 layers, 6D occurrence evidence, and the **Human Gate 2** occurrence controls (`CONFIRMED`, `EXCLUDED`). Shows real-time regulatory impact metrics, the deterministic validation checklist (`REG-VAL-001` - `REG-VAL-006`), and the **Human Gate 3** approval authorization modal.
5. **Stage 5 — Approved Change Report (`ApprovedChangeReport.jsx`):**  
   Displays the finalized, authorized report with side-by-side diff previews, approver credentials, and cryptographic audit ledger. Provides two primary download actions:
   - **Download PDF Report:** Downloads the ReportLab audit summary PDF.
   - **Download Corrected Document:** Downloads the corrected DOCX or TXT file (disabled/blocked for PDF uploads).

---

## 14. Technology Stack

Only technologies actively implemented in the repository are listed:

### Backend Runtime
- **Language:** Python 3.10+
- **Web Framework:** FastAPI 0.115+, Starlette
- **ASGI Server:** Uvicorn
- **Data Contracts & Validation:** Pydantic v2, Pydantic Settings
- **HTTP Client:** HTTPX (asynchronous requests for external regulatory APIs)
- **Database:** SQLite 3 (standard library `sqlite3`, user_version = 2 schema)
- **Document Processing:** `python-docx` (DOCX parsing/generation), `pypdf` (PDF text extraction)
- **PDF Generation:** ReportLab 4.4+ (Approved Change Report PDF export)
- **Testing Framework:** Pytest 8.3+, `pytest-asyncio`

### Frontend Application
- **Language:** JavaScript (ES2022+ / JSX)
- **UI Framework:** React 19.2+, ReactDOM 19.2+
- **Build Tool:** Vite 8.3+
- **Linter & Code Quality:** Oxlint 1.81+
- **Styling:** Vanilla CSS Custom Design System (HSL tokens, glassmorphism, responsive grid)
- **Iconography:** Lucide React 1.47+

### External Regulatory Integrations
- **NLM DailyMed REST API v2:** Live drug labeling and SPL XML queries.
- **US FDA openFDA Drug Labeling API:** Live structured labeling endpoints.
- **OpenAI API:** Optional backend-only enhancement; system includes deterministic local fallbacks when unconfigured or offline.

---

## 15. API Reference

Inspection of the backend route modules confirms **22 active API endpoints**:

### Core & Health (`backend/app/main.py`)
1. `GET /health`: System health check, source connectivity status, and configuration flags.

### Regulatory Sources (`backend/app/routes/regulatory.py`)
2. `GET /regulatory/search`: Live search across DailyMed and openFDA with provenance metadata.
3. `GET /regulatory/document/{source}/{identifier}`: Detailed section retrieval for a specific Set ID or Drug Label record.
4. `GET /regulatory/sources/status`: Health and latency check of external regulatory endpoints.

### Content Analysis & Comparison (`backend/app/routes/comparison.py`)
5. `POST /content/analyze`: Evaluate candidate alignment against target section via Agent 1.
6. `POST /content/compare`: Compute structured 6D clinical differences between two text snippets.

### Document Ingestion & Candidate Discovery (`backend/app/routes/candidate_discovery.py`)
7. `POST /documents/ingest`: Multipart file or pasted text ingestion into candidate store.
8. `POST /candidates/search`: Query candidates across ingested documents and live sources.

### Document Review & Workflow Lifecycle (`backend/app/routes/document_review.py`)
9. `POST /documents/upload`: Parse document text/files into structured regulatory sections.
10. `POST /review/decision`: Record human regulatory decision (**Gate 1**: `REUSE`, `ADAPT`, `REJECT`).
11. `POST /changes/analyze`: Formulate controlled change proposal via Agent 2.
12. `POST /changes/occurrences`: Detect related occurrences across document sections across 4 layers.
13. `POST /changes/occurrences/confirm`: Record human confirmation (**Gate 2**: `CONFIRMED`, `EXCLUDED`).
14. `POST /changes/validate`: Run deterministic validation engine (`REG-VAL-001` - `REG-VAL-006`).
15. `POST /changes/approve`: Human approval gate (**Gate 3**); compiles `ApprovedChangeReport`.
16. `GET /changes/report`: List active change proposals and reports.
17. `GET /changes/report/{report_id}/pdf`: Generate and download audit-ready approved change report PDF.
18. `POST /changes/report/{report_id}/corrected-document`: Generate and download corrected document (DOCX/TXT).
19. `GET /history`: Retrieve session reviewer decision history.

### Audit Trail (`backend/app/routes/audit.py`)
20. `GET /audit`: Retrieve chronological workflow audit events.
21. `GET /audit/verify`: Verify cryptographic SHA-256 hash chain integrity.
22. `GET /audit/{change_id}`: Retrieve audit history for a specific change proposal.

---

## 16. Testing Status

The testing suite verifies all components across unit, integration, and end-to-end workflows:

- **Backend Test Suite:** **458 passed**, 0 failed (`pytest backend/tests -v`).
  - *Execution Time:* ~123 seconds.
  - *Test Coverage Areas:*
    - Ingestion parsers & section extractors (DOCX, PDF, TXT, MD, legacy DOC)
    - Structure-preserving regulatory chunking
    - Candidate store lifecycle & source byte retention
    - Cross-source deduplication & provenance preservation
    - Multi-dimensional comparator (6 dimensions)
    - Difference detection & clinical entity extraction
    - False-match protection & discrepancy detection
    - Controlled change manager & proposal formulation
    - 4-layer occurrence detection & 6D occurrence evidence
    - Advisory recommendation engines (REUSE/ADAPT/REJECT & CONFIRM/EXCLUDE)
    - Regulatory validation engine (`REG-VAL-001` through `REG-VAL-006`)
    - SQLite persistence, schema user_version 2, and restart recovery
    - Cryptographic SHA-256 hash-chain audit ledger & tamper detection
    - ReportLab executive PDF generation & hash preservation
    - Corrected document generator (DOCX typography, run replacement, table cells, TXT spans)
    - Document ID propagation across end-to-end approval workflows
    - Prompt injection resilience (untrusted text treated as passive data)
- **Frontend Code Quality:**
  - `oxlint`: **0 warnings, 0 errors** across all frontend source files (10 files, 104 rules).
  - `vite build`: Production client bundle compiles cleanly in 1.73s with **0 errors**.

---

## 17. Evaluation Results

The evaluation benchmark (`evaluation/run_evaluation.py`) executes 10 comprehensive evaluation suites:

### 1. Six-Dimensional Comparison Evaluation
- **Meaning (Semantic):** 3/3 passed (100.0%)
- **Template (Boilerplate):** 2/3 passed (66.7%)
- **Context (Indication/Scope):** 3/3 passed (100.0%)
- **Structure (Hierarchy):** 3/3 passed (100.0%)
- **Format (Styling):** 3/3 passed (100.0%)
- **Key Information (Entities):** 3/3 passed (100.0%)
- **Overall 6D Comparison Accuracy:** **94.4%**

> [!IMPORTANT]
> **No Exaggerated Accuracy Claims:** The overall multi-dimensional comparison accuracy is **94.4%**. The project must **never** be claimed to have "100% overall accuracy." The 100% metrics below represent pass rates for specific deterministic governance, cryptographic, and document generation checks.

### 2. Deterministic Difference Detection Evaluation
- **Expected Clinical Attributes:** 4
- **Detected Clinical Attributes:** 4
- **Accuracy:** **100.0%**

### 3. False-Match Protection Evaluation
- **True Positives (TP - Discrepancies blocked):** 3
- **True Negatives (TN - Valid matches passed):** 1
- **False Positives (FP):** 0
- **False Negatives (FN):** 0
- **Accuracy:** **100.0%**

### 4. RAG Retrieval & Groundedness Metrics
- **Recall@3:** **1.0**
- **Precision@3:** **0.6667**
- **Hit Rate@3:** **1.0**
- **Mean Reciprocal Rank (MRR):** **1.0**
- **Groundedness Accuracy:** **100.0%**

### 5. Governance Validation Evaluation (`REG-VAL-001` - `REG-VAL-006`)
- `REG-VAL-001` (Text Completeness): 2/2 passed (100.0%)
- `REG-VAL-002` (Rationale Presence): 2/2 passed (100.0%)
- `REG-VAL-003` (Provenance Citation): 2/2 passed (100.0%)
- `REG-VAL-004` (Decision Linkage): 2/2 passed (100.0%)
- `REG-VAL-005` (Approval Gate Authorization): 3/3 passed (100.0%)
- `REG-VAL-006` (Unresolved Occurrences Gate): 2/2 passed (100.0%)
- **Governance Validation Pass Rate:** **100.0%** (13/13 checks passed)

### 6. Pending / Approval Gate Evaluation
- Pending Occurrences Block Report Generation: Passed
- Pending Occurrences Block Document Generation: Passed
- Missing Approval Confirmation Blocked: Passed
- Missing Approver Identity Blocked: Passed
- Unapproved Report Document Generation Blocked: Passed
- Valid Explicit Approval Succeeded: Passed
- **Approval Gate Pass Rate:** **100.0%** (6/6 checks passed)

### 7. Audit Trail Integrity & Tamper Detection Evaluation
- Append-Only Hash Chain Verification: Passed (4/4 events verified)
- Cryptographic Hash Linkage (SHA-256): Passed (All `previous_event_hash` links match)
- Tamper Detection (Payload Mutation): Passed (Detected immediately at tampered event)
- **Audit Integrity Pass Rate:** **100.0%** (3/3 checks passed)

### 8. Corrected Document Generation Fidelity Evaluation
- DOCX Targeted Replacement Fidelity: Passed
- Non-Targeted Content Intact (DOCX): Passed
- DOCX Structure & Section Formatting: Passed
- TXT Targeted Replacement Fidelity: Passed
- Excluded Occurrence Remains Unaltered: Passed
- Deterministic Output Artifact Generation: Passed
- **Document Correction Fidelity:** **100.0%** (6/6 checks passed)

### 9. Source Document Immutability Evaluation
- Pre-Generation Source SHA-256: `09ff261a165a150862c3dc6118012599d4076abd71c1c8ab82a277c2bdd4b6ea`
- Post-Generation Source SHA-256: `09ff261a165a150862c3dc6118012599d4076abd71c1c8ab82a277c2bdd4b6ea`
- Source Bytes Byte-for-Byte Identical to Input: Passed
- **Source Immutability Pass Rate:** **100.0%** (2/2 checks passed)

### 10. PDF Input-Only Compliance Evaluation
- PDF Correction Generation Request Rejected: Passed
- PDF Input-Only Error Message Verified: Passed
- Zero Corrected Artifact Bytes Emitted: Passed
- **PDF Input-Only Compliance:** **100.0%** (3/3 checks passed)

---

## 18. Git / Phase History

The project evolved through a disciplined, verified phase progression:

- **Phase 4 Baseline:**
  - `d1f4ad7`: `test: harden phase 4 end-to-end workflow` — End-to-end test harness hardening.
  - `5d2f069`: `docs: complete phase 4 documentation and handover` — Complete Phase 4 documentation baseline.
- **Phase 5: Governance, Audit UI & 6D Occurrence Evidence:**
  - `88f7c09`: `feat: add tamper-evident audit trail` — SHA-256 cryptographic hash-chaining engine.
  - `b9baa7e`: `feat: add approved change report PDF export` — Initial PDF report generation.
  - `e551bba`: `feat: add approved change report PDF download` — Browser download endpoint.
  - `60ead38`: `feat: complete phase 5 frontend governance and audit UI` — React governance review screens.
  - `70c6f1d`: `feat(backend): add 6-dimensional occurrence evidence to Agent 2 detection flow` — Occurrence radar scoring.
  - `98a14a6`: `feat(frontend): display 6D occurrence evidence` — Frontend radar/scorecard visualization.
- **Phase 6 / 6G: Streamlined Workflow & Advisory Decision Support:**
  - `c722bd7`: `feat: add simplified regulatory document upload and legacy doc support` — Multipart file upload.
  - `068f658`: `feat: add automatic candidate discovery and advisory recommendations` — Automated candidate ranking.
  - `745abc5`: `feat: add automatic advisory ADAPT wording and rationale` — Advisory draft generation.
  - `29b5ae1`: `feat: add advisory automatic occurrence recommendations and rationale` — Advisory occurrence triage.
  - `1637c07`: `feat: consolidate candidate comparison and decision workflow` — Consolidated comparison UI.
  - `589b9d2`: `feat: simplify regulatory review workflow UI` — Unified 5-stage UI workflow.
  - `f6f0a14`: `feat: generate corrected regulatory documents after approval` — DOCX/TXT corrected document generator.
- **Phase 7 Baseline:**
  - `bf04196`: `fix: preserve document id through approval workflow` — Resolves authoritative `document_id` propagation across browser upload, decision recording, proposal formulation, report approval, and corrected document download.
- **Phase 8A: Evaluation Benchmark Expansion (Implemented):**
  - Expanded `evaluation/run_evaluation.py` and `evaluation/metrics.py` across 10 evaluation suites covering governance rules, approval gates, audit integrity, document correction fidelity, source immutability, and PDF input-only enforcement.
- **Phase 8B: Authoritative README Update (Implemented):**
  - Updated `README.md` with 15 comprehensive technical sections, accurate numbers, and zero whitespace lint issues.
- **Phase 8C: Consolidated Final Project Handover (Current Document):**
  - Produced `PROJECT_FINAL_HANDOVER.md` as the definitive handover guide for engineering, leadership, and demonstration.

---

## 19. Current Verified State

To ensure total transparency, project status is categorized across four distinct states:

| Category | Item | Verification Status |
|---|---|---|
| **Implemented & Verified** | Exactly Two Agents (`RegulatoryContentAnalysisAgent`, `RegulatoryDocumentChangeAgent`) | Verified in code & unit tests |
| **Implemented & Verified** | 6-Dimensional Comparison & Difference Detection Engine | Verified (94.4% 6D, 100% diff detection) |
| **Implemented & Verified** | Three Human Governance Gates (`REUSE/ADAPT/REJECT`, `CONFIRMED/EXCLUDED`, Approval Gate) | Verified in unit tests & evaluation |
| **Implemented & Verified** | Validation Rules `REG-VAL-001` through `REG-VAL-006` | Verified in unit tests & evaluation |
| **Implemented & Verified** | SQLite Persistence & Cryptographic SHA-256 Hash Chain Ledger | Verified in unit tests & evaluation |
| **Implemented & Verified** | Corrected Document Generation for DOCX and TXT | Verified in unit tests & evaluation |
| **Implemented & Verified** | PDF Input-Only Boundary (In-place correction strictly rejected) | Verified in unit tests & evaluation |
| **Implemented & Verified** | Original Source Document Byte Immutability | Verified (SHA-256 identical before & after) |
| **Implemented & Verified** | 22 Active FastAPI Endpoints | Verified via route inspection & tests |
| **Implemented & Verified** | 458 Backend Automated Tests Passing | Verified via `pytest` (0 failures, 3 warnings) |
| **Implemented & Verified** | Frontend Code Quality (`oxlint` 0 errors, `vite build` clean) | Verified via `npm run lint` & `npm run build` |
| **Documentation Only** | `evaluation/metrics.py` & `evaluation/run_evaluation.py` (Phase 8A) | Implemented, verified, uncommitted |
| **Documentation Only** | `README.md` (Phase 8B) | Implemented, verified, uncommitted |
| **Documentation Only** | `PROJECT_FINAL_HANDOVER.md` (Phase 8C) | Implemented, verified, uncommitted |
| **Remaining Closeout Action** | Phase 8D Final Regression, Git Validation, Commit & Push | Pending explicit user instruction |

---

## 20. Known Limitations / Boundaries

The following design boundaries are intentionally enforced:

1. **PDF Source Correction is Unsupported (Input-Only):**  
   PDF files cannot be modified in-place. The system strictly rejects requests to generate corrected PDFs (`UnsupportedFormatError` / `HTTP 400`). Generating an *Approved Change Report PDF* is supported as an audit export, but the source PDF remains immutable.
2. **No Autonomous Approvals or Rejections:**  
   The system cannot make binding regulatory decisions. It operates strictly as decision support.
3. **Pending Occurrences Strictly Block Approval:**  
   Under rule `REG-VAL-006`, report approval and document correction cannot proceed if any related occurrence remains `PENDING`.
4. **Source Byte Immutability:**  
   The application never mutates or overwrites source files on disk. Original bytes retained in `IngestedDocumentCandidateStore` are treated as read-only.
5. **External Source Connectivity:**  
   Live retrieval from NLM DailyMed and openFDA depends on external network connectivity and public API availability. In disconnected environments, the system falls back to locally ingested candidate documents.
6. **Legacy Binary DOC (.doc) Input-Only:**  
   Legacy `.doc` binary files can be parsed and reviewed, but direct binary modification is not supported. Users must convert legacy files to `.docx` for in-place text replacement.

---

## 21. Presentation & Demonstration Story

This concise script enables presenters, product managers, or engineers to demonstrate GPR verbally:

1. **Slide 1 — The Problem:**  
   *"In regulatory affairs, updating dossiers like package inserts or clinical protocols is high-risk. A single dosing discrepancy between Section 2 and Section 12 can cause an FDA rejection. Manual cross-referencing is slow, error-prone, and lacks auditable provenance."*
2. **Slide 2 — The GPR Solution:**  
   *"GPR is an AI-assisted decision-support platform designed specifically for regulatory teams. It connects draft text to live FDA drug labeling precedents while enforcing strict human governance and cryptographic auditability."*
3. **Slide 3 — Agent 1 (Analysis & Discovery):**  
   *"The user uploads a draft document. Agent 1 parses the sections and queries NLM DailyMed and openFDA. It compares the draft against regulatory precedents across six dimensions, highlights dosage differences, flags false matches, and offers an advisory recommendation."*
4. **Slide 4 — Human Gate 1 (Reviewer Decision):**  
   *"Agent 1 cannot approve anything. The human reviewer makes the authoritative decision: REUSE, ADAPT, or REJECT. If the candidate is rejected, the process stops immediately."*
5. **Slide 5 — Agent 2 (Occurrences & Impact):**  
   *"If the reviewer selects ADAPT, Agent 2 formulates a controlled proposal and scans the entire dossier across four detection layers to find every related mention in other sections."*
6. **Slide 6 — Human Gate 2 (Occurrence Review):**  
   *"The reviewer inspects each occurrence and marks it CONFIRMED or EXCLUDED. If any occurrence is left PENDING, the system refuses to proceed."*
7. **Slide 7 — Validation & Human Gate 3 (Authorization):**  
   *"The system executes deterministic validation rules REG-VAL-001 through REG-VAL-006. The authorized approver provides explicit digital confirmation and their regulatory identity."*
8. **Slide 8 — Outputs & Cryptographic Audit:**  
   *"The system generates two deliverables: an executive audit-ready PDF summary and a corrected DOCX document with original formatting preserved. Every step is cryptographically linked in a SHA-256 append-only ledger, providing complete GxP and 21 CFR Part 11 traceability."*

---

## 22. Final Handover Checklist

- [x] **Runtime Implementation Complete:** Two-agent architecture fully implemented.
- [x] **Governance Gates Verified:** Gate 1 (`REUSE/ADAPT/REJECT`), Gate 2 (`CONFIRMED/EXCLUDED`), and Gate 3 (`approval_confirmation=true`) verified.
- [x] **Corrected Document Behavior Verified:** In-memory DOCX and TXT generation verified.
- [x] **PDF Input-Only Verified:** Rejection of in-place PDF correction verified.
- [x] **Source Immutability Verified:** Original source bytes SHA-256 match before and after generation.
- [x] **Audit Integrity Verified:** SHA-256 hash chaining and tamper detection verified.
- [x] **Evaluation Suite Expanded (Phase 8A):** All 10 evaluation suites passing cleanly.
- [x] **Authoritative README Updated (Phase 8B):** Comprehensive documentation with zero whitespace warnings.
- [x] **Consolidated Final Handover Document Created (Phase 8C):** `PROJECT_FINAL_HANDOVER.md` created.
- [ ] **Full Regression Suite Execution Pending:** Phase 8D final verification.
- [ ] **Final Git Commit Pending:** Phase 8D commit.
- [ ] **Final Push to Origin Pending:** Phase 8D push.
