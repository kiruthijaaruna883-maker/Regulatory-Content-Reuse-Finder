/**
 * Review Session Storage Service for GPR.
 *
 * Provides versioned, session-scoped persistence of active regulatory source document
 * and section review context across browser reloads.
 *
 * Privacy & Security Constraints:
 * - Strictly persists metadata only (document_id, document_fingerprint, document_name, jurisdiction, section identifiers).
 * - NEVER persists source-document raw bytes, binary files, or full unencrypted document text bodies in browser storage.
 */

export const GPR_REVIEW_CONTEXT_STORAGE_KEY = 'gpr_active_review_context_v1';

/**
 * Extract safe, non-sensitive review context metadata for session persistence.
 * Strictly omits file bytes, binary data, and sensitive raw document text bodies.
 *
 * @param {Object|null} sourceDoc
 * @param {Object|null} selectedSec
 * @returns {Object|null}
 */
export function serializeReviewContext(sourceDoc, selectedSec) {
  if (!sourceDoc && !selectedSec) {
    return null;
  }

  const payload = {
    version: 1,
    savedAt: new Date().toISOString(),
  };

  if (sourceDoc && typeof sourceDoc === 'object' && sourceDoc.document_id) {
    payload.activeSourceDocument = {
      document_id: String(sourceDoc.document_id),
      document_fingerprint: sourceDoc.document_fingerprint ? String(sourceDoc.document_fingerprint) : null,
      document_name: sourceDoc.document_name ? String(sourceDoc.document_name) : null,
      jurisdiction: sourceDoc.jurisdiction ? String(sourceDoc.jurisdiction) : 'US_FDA',
      document_type: sourceDoc.document_type ? String(sourceDoc.document_type) : 'REGULATORY_LABEL',
      sections: Array.isArray(sourceDoc.sections)
        ? sourceDoc.sections.map((s) => ({
            content_id: s.content_id ? String(s.content_id) : null,
            section: s.section ? String(s.section) : null,
            section_number: s.section_number ? String(s.section_number) : null,
            subsection: s.subsection ? String(s.subsection) : null,
            location: s.location ? String(s.location) : null,
            page: typeof s.page === 'number' ? s.page : null,
            content_type: s.content_type ? String(s.content_type) : null,
            document_id: s.document_id ? String(s.document_id) : String(sourceDoc.document_id),
            document_fingerprint: s.document_fingerprint
              ? String(s.document_fingerprint)
              : (sourceDoc.document_fingerprint ? String(sourceDoc.document_fingerprint) : null),
            document_name: s.document_name
              ? String(s.document_name)
              : (sourceDoc.document_name ? String(sourceDoc.document_name) : null),
          }))
        : [],
    };
  } else {
    payload.activeSourceDocument = null;
  }

  if (selectedSec && typeof selectedSec === 'object' && (selectedSec.content_id || selectedSec.section || selectedSec.document_id)) {
    payload.selectedSection = {
      content_id: selectedSec.content_id ? String(selectedSec.content_id) : null,
      section: selectedSec.section ? String(selectedSec.section) : null,
      section_number: selectedSec.section_number ? String(selectedSec.section_number) : null,
      subsection: selectedSec.subsection ? String(selectedSec.subsection) : null,
      location: selectedSec.location ? String(selectedSec.location) : null,
      page: typeof selectedSec.page === 'number' ? selectedSec.page : null,
      content_type: selectedSec.content_type ? String(selectedSec.content_type) : null,
      document_id: selectedSec.document_id
        ? String(selectedSec.document_id)
        : (sourceDoc?.document_id ? String(sourceDoc.document_id) : null),
      document_fingerprint: selectedSec.document_fingerprint
        ? String(selectedSec.document_fingerprint)
        : (sourceDoc?.document_fingerprint ? String(sourceDoc.document_fingerprint) : null),
      document_name: selectedSec.document_name
        ? String(selectedSec.document_name)
        : (sourceDoc?.document_name ? String(sourceDoc.document_name) : null),
    };
  } else {
    payload.selectedSection = null;
  }

  return payload;
}

/**
 * Safely load persisted review context from sessionStorage or provided storage mock.
 * Validates version and schema shape; returns null on missing, malformed, or outdated data.
 *
 * @param {Storage|null} storage
 * @returns {{activeSourceDocument: Object|null, selectedSection: Object|null}|null}
 */
export function loadPersistedReviewContext(storage = (typeof window !== 'undefined' ? window.sessionStorage : null)) {
  if (!storage) {
    return null;
  }
  try {
    const raw = storage.getItem(GPR_REVIEW_CONTEXT_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }
    // Strict schema version check
    if (parsed.version !== 1) {
      storage.removeItem(GPR_REVIEW_CONTEXT_STORAGE_KEY);
      return null;
    }
    // Validate shape of activeSourceDocument if present
    const srcDoc = parsed.activeSourceDocument;
    const validSrcDoc = srcDoc && typeof srcDoc === 'object' && typeof srcDoc.document_id === 'string'
      ? srcDoc
      : null;

    // Validate shape of selectedSection if present
    const sec = parsed.selectedSection;
    const validSec = sec && typeof sec === 'object' && (typeof sec.content_id === 'string' || typeof sec.section === 'string')
      ? sec
      : null;

    if (!validSrcDoc && !validSec) {
      return null;
    }

    return {
      activeSourceDocument: validSrcDoc,
      selectedSection: validSec,
    };
  } catch {
    try {
      storage.removeItem(GPR_REVIEW_CONTEXT_STORAGE_KEY);
    } catch {
      // Ignore secondary storage removal error
    }
    return null;
  }
}

/**
 * Write review context to sessionStorage or clear if both values are null.
 *
 * @param {Object|null} sourceDoc
 * @param {Object|null} selectedSec
 * @param {Storage|null} storage
 */
export function persistReviewContext(sourceDoc, selectedSec, storage = (typeof window !== 'undefined' ? window.sessionStorage : null)) {
  if (!storage) {
    return;
  }
  try {
    const serialized = serializeReviewContext(sourceDoc, selectedSec);
    if (!serialized || (!serialized.activeSourceDocument && !serialized.selectedSection)) {
      storage.removeItem(GPR_REVIEW_CONTEXT_STORAGE_KEY);
    } else {
      storage.setItem(GPR_REVIEW_CONTEXT_STORAGE_KEY, JSON.stringify(serialized));
    }
  } catch {
    // Non-blocking catch for browser privacy modes or storage quota limits
  }
}

/**
 * Clear persisted review context from sessionStorage.
 *
 * @param {Storage|null} storage
 */
export function clearPersistedReviewContext(storage = (typeof window !== 'undefined' ? window.sessionStorage : null)) {
  if (!storage) {
    return;
  }
  try {
    storage.removeItem(GPR_REVIEW_CONTEXT_STORAGE_KEY);
  } catch {
    // Non-blocking catch
  }
}
