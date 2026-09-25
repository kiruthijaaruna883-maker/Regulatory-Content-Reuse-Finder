# Phase 3 Handover — Regulatory Content Reuse Finder

## Project Overview
* **Project Name:** Regulatory Content Reuse Finder
* **Current Frontend:** React / Vite ([http://localhost:5173/](http://localhost:5173/))
* **Current Backend:** FastAPI ([http://127.0.0.1:8000](http://127.0.0.1:8000/))

---

## Current Status

### Phase 1: Foundation Models & Data Contracts
* **Status:** Complete
* Hierarchical regulatory models established (`RegulatoryDocument`, `RegulatorySection`, `RegulatoryChunk`, `RegulatoryTable`, `RegulatoryTableRow`, `RegulatoryProvenance`).
* Backward-compatible mapping with legacy `RegulatoryContentItem`.

### Phase 2: Universal Ingestion + Custom Regulatory Chunking
* **Status:** Complete and Verified
* **Supported Formats:** TXT, Markdown, JSON, XML, HTML, PDF, and DOCX.
* **Unified Ingestion:** Accepts string, bytes, and file-like inputs via `UnifiedIngestionService`.
* **Regulatory-Aware Chunking:** Structure-aware chunking preserving section hierarchy, paragraphs (sentence splitting), tables (header-cell row mappings), bullet/list items (parent stem linkage), and structured fields with deterministic SHA-256 chunk IDs.
* **Full Traceability:** Preserves document identity, outline hierarchy, structure path, exact location, page numbers, table/row context, and source provenance.
* **Compatibility Layer:** Small, deterministic adapters (`backend/app/services/compatibility/`) bridging Phase 2 hierarchical models with legacy services (`VectorStore`, `ContentMatchingService`, `MultiDimensionalComparator`) and reverse adapters.
* **Backend Verification:** **166 tests passed, 0 failed** across all backend test suites.

---

## Phase 3 Scope & Guidelines (Next Phase)

**Phase 3 Objective:** Retrieval + Candidate Discovery + Multi-Dimensional Comparison

### Crucial Directives for Phase 3:
1. **Inspect Before Changing:** Inspect the existing implementation across `backend/app/services/` and `backend/app/models/` before making changes.
2. **Six Comparison Dimensions:**
   * **Meaning:** Semantic directive alignment.
   * **Template:** Regulatory sentence patterns (population + drug + dose + frequency).
   * **Context:** Prescribing recommendation vs. clinical trial observation vs. safety warning.
   * **Structure:** Outline level, section hierarchy, paragraph, table, or bullet context.
   * **Format:** Phrasing conventions, sentence structures, numerical specifications.
   * **Key Information:** Exact clinical parameter comparisons (drug, indication, dose, frequency, route, population).
3. **Human Decision Control:**
   * The human reviewer decision remains strictly: **Reuse / Adapt / Reject**.
   * System must **NEVER** automatically approve regulatory content reuse.
4. **Preserve External Integrations:**
   * Live integrations with **DailyMed** and **openFDA** must remain in place.
5. **No Synthetic Data Rule:**
   * Strictly **NO** synthetic regulatory data or synthetic document generation allowed.
6. **Architecture & Scope Constraints:**
   * Do not change the project name.
   * Do not add unnecessary frameworks or redundant agents.
   * Keep changes minimal, deterministic, auditable, and backward compatible.

---

## Working Tree & Version Control Notes
* This handover file is created for documentation only.
* Do not commit or push this handover file yet.
