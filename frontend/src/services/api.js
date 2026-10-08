/**
 * API Service Layer for Regulatory Content Reuse Finder.
 *
 * Connects frontend to the FastAPI backend.
 * Never passes or expects API keys on the frontend.
 */

const API_BASE = import.meta.env?.VITE_API_BASE ?? "";

async function handleResponse(res) {
  if (!res.ok) {
    let errorDetail = `HTTP Error ${res.status}: ${res.statusText}`;
    try {
      const data = await res.json();
      if (data.detail) errorDetail = data.detail;
      else if (data.message) errorDetail = data.message;
    } catch {
      // Non-JSON response
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export const api = {
  /**
   * Health & Source connectivity check
   */
  async getHealth() {
    const res = await fetch(`${API_BASE}/health`);
    return handleResponse(res);
  },

  /**
   * Live search across DailyMed and openFDA
   */
  async searchRegulatorySources(query, source = "all", section = null, limit = 10) {
    const params = new URLSearchParams({
      query: query.trim(),
      source,
      limit: limit.toString(),
    });
    if (section) params.append("section", section);

    const res = await fetch(`${API_BASE}/regulatory/search?${params.toString()}`);
    return handleResponse(res);
  },

  /**
   * Fetch specific document details by Set ID or Record ID
   */
  async getDocumentDetails(source, identifier) {
    const res = await fetch(`${API_BASE}/regulatory/document/${source}/${encodeURIComponent(identifier)}`);
    return handleResponse(res);
  },

  /**
   * Check live connectivity status of DailyMed and openFDA
   */
  async getSourcesStatus() {
    const res = await fetch(`${API_BASE}/regulatory/sources/status`);
    return handleResponse(res);
  },

  /**
   * Upload and segment document text into structured sections
   */
  async uploadDocument(documentName, content) {
    const res = await fetch(`${API_BASE}/documents/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_name: documentName, content }),
    });
    return handleResponse(res);
  },

  /**
   * Ingest multi-format document or pasted text into candidate store
   * Uses FormData multipart payload without manually setting Content-Type
   */
  async ingestDocument(formData) {
    const res = await fetch(`${API_BASE}/documents/ingest`, {
      method: "POST",
      body: formData,
    });
    return handleResponse(res);
  },

  /**
   * Discover candidates across candidate store and live sources (DailyMed, openFDA)
   */
  async searchCandidates({
    query,
    source_filter = "all",
    section = null,
    target_text = null,
    top_k = 10,
    exclude_document_id = null,
    document_id = null,
  }) {
    const payload = {
      query: (query || "").trim(),
      source_filter,
      top_k,
    };
    if (section) payload.section = section;
    if (target_text) payload.target_text = target_text;
    if (exclude_document_id) payload.exclude_document_id = exclude_document_id;
    if (document_id) payload.document_id = document_id;

    const res = await fetch(`${API_BASE}/candidates/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },

  /**
   * Compare candidate items with target text using Agent 1
   * Supports optional target provenance parameters for Phase 3 Step 4 traceability
   */
  async analyzeCandidates(targetText, candidates = [], sectionName = null, options = {}) {
    const payload = {
      target_text: targetText,
      section_name: sectionName,
      candidates,
    };
    if (options.target_content_id) payload.target_content_id = options.target_content_id;
    if (options.document_name) payload.document_name = options.document_name;
    if (options.document_id) payload.document_id = options.document_id;
    if (options.subsection) payload.subsection = options.subsection;
    if (options.location) payload.location = options.location;
    if (options.page !== undefined && options.page !== null) payload.page = options.page;
    if (options.content_type) payload.content_type = options.content_type;
    if (options.retrieve_live !== undefined && options.retrieve_live !== null) payload.retrieve_live = options.retrieve_live;
    if (options.source_filter) payload.source_filter = options.source_filter;
    if (options.top_k !== undefined && options.top_k !== null) payload.top_k = options.top_k;

    const res = await fetch(`${API_BASE}/content/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },

  /**
   * Detect differences between two texts
   */
  async compareTexts(currentText, candidateText) {
    const res = await fetch(`${API_BASE}/content/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_text: currentText,
        candidate_text: candidateText,
      }),
    });
    return handleResponse(res);
  },

  /**
   * Record human regulatory professional decision (Reuse, Adapt, Reject)
   */
  async recordDecision(decisionData) {
    const res = await fetch(`${API_BASE}/review/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decisionData),
    });
    return handleResponse(res);
  },

  /**
   * Formulate controlled change proposal via Agent 2
   */
  async analyzeChangeProposal(proposalData) {
    const res = await fetch(`${API_BASE}/changes/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(proposalData),
    });
    return handleResponse(res);
  },

  /**
   * Validate change proposal
   */
  async validateChange(proposal) {
    const res = await fetch(`${API_BASE}/changes/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(proposal),
    });
    return handleResponse(res);
  },

  /**
   * Detect related occurrences across document sections
   */
  async detectOccurrences(targetPhrase, documentSections, targetText = null) {
    const res = await fetch(`${API_BASE}/changes/occurrences`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_phrase: targetPhrase,
        document_sections: documentSections,
        target_text: targetText,
      }),
    });
    return handleResponse(res);
  },

  /**
   * Confirm or exclude detected occurrences for a proposed change
   */
  async confirmOccurrences(payload) {
    const res = await fetch(`${API_BASE}/changes/occurrences/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },


  /**
   * Finalize human approval and compile change report
   */
  async approveAndGenerateReport(reportData) {
    const res = await fetch(`${API_BASE}/changes/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reportData),
    });
    return handleResponse(res);
  },

  /**
   * List pending change proposals
   */
  async listProposals() {
    const res = await fetch(`${API_BASE}/changes/report`);
    return handleResponse(res);
  },

  /**
   * Get decision history
   */
  async getHistory() {
    const res = await fetch(`${API_BASE}/history`);
    return handleResponse(res);
  },

  /**
   * Retrieve chronological workflow audit trail
   */
  async getAuditTrail(limit = null) {
    const query = limit ? `?limit=${encodeURIComponent(limit)}` : "";
    const res = await fetch(`${API_BASE}/audit${query}`);
    return handleResponse(res);
  },

  /**
   * Verify SHA-256 hash-chain integrity for tamper detection
   */
  async verifyAuditTrail() {
    const res = await fetch(`${API_BASE}/audit/verify`);
    return handleResponse(res);
  },

  /**
   * Download approved change report as PDF
   * Returns { blob, filename } or throws Error
   */
  async downloadApprovedChangeReportPdf(reportId) {
    if (!reportId) {
      throw new Error("Report ID is required to download PDF.");
    }
    const res = await fetch(`${API_BASE}/changes/report/${encodeURIComponent(reportId)}/pdf`);
    if (!res.ok) {
      let errorDetail = `HTTP Error ${res.status}: ${res.statusText}`;
      try {
        const data = await res.json();
        if (data.detail) errorDetail = data.detail;
        else if (data.message) errorDetail = data.message;
      } catch {
        // Non-JSON error response
      }
      throw new Error(errorDetail);
    }

    let filename = `Approved_Change_Report_${reportId}.pdf`;
    const disposition = res.headers.get("Content-Disposition");
    if (disposition) {
      const match = disposition.match(/filename="?([^";\n]+)"?/i);
      if (match && match[1]) {
        filename = match[1].trim();
      }
    }

    const blob = await res.blob();
    return { blob, filename };
  },

  /**
   * Download corrected regulatory document generated from retained source bytes
   * Returns { blob, filename } or throws Error
   */
  async downloadCorrectedDocument(reportId) {
    if (!reportId) {
      throw new Error("Report ID is required to download corrected document.");
    }
    const res = await fetch(`${API_BASE}/changes/report/${encodeURIComponent(reportId)}/corrected-document`, {
      method: "POST",
    });
    if (!res.ok) {
      let errorDetail = `HTTP Error ${res.status}: ${res.statusText}`;
      try {
        const data = await res.json();
        if (data.detail) errorDetail = data.detail;
        else if (data.message) errorDetail = data.message;
      } catch {
        // Non-JSON error response
      }
      throw new Error(errorDetail);
    }

    let filename = `Corrected_Document_${reportId}`;
    const disposition = res.headers.get("Content-Disposition");
    if (disposition) {
      const match = disposition.match(/filename="?([^";\n]+)"?/i);
      if (match && match[1]) {
        filename = match[1].trim();
      }
    }

    const blob = await res.blob();
    return { blob, filename };
  },
};

export const downloadApprovedChangeReportPdf = api.downloadApprovedChangeReportPdf;
export const downloadCorrectedDocument = api.downloadCorrectedDocument;
