import test from 'node:test';
import assert from 'node:assert';
import {
  GPR_REVIEW_CONTEXT_STORAGE_KEY,
  serializeReviewContext,
  loadPersistedReviewContext,
  persistReviewContext,
  clearPersistedReviewContext,
} from './reviewSession.js';

class MockStorage {
  constructor(initial = {}) {
    this.store = { ...initial };
  }
  getItem(key) {
    return Object.prototype.hasOwnProperty.call(this.store, key) ? this.store[key] : null;
  }
  setItem(key, val) {
    this.store[key] = String(val);
  }
  removeItem(key) {
    delete this.store[key];
  }
  clear() {
    this.store = {};
  }
}

test('1. Restoring active document metadata after a simulated page reload', () => {
  const mockStorage = new MockStorage();

  const sourceDoc = {
    document_id: 'doc_disposable_88a',
    document_fingerprint: 'fp_disposable_99b',
    document_name: 'Investigational Dossier A',
    jurisdiction: 'US_FDA',
    document_type: 'REGULATORY_LABEL',
    sections: [
      {
        content_id: 'sec_01',
        section: '1. INDICATIONS AND USAGE',
        section_number: '1',
        document_id: 'doc_disposable_88a',
        document_fingerprint: 'fp_disposable_99b',
        // Deliberately include raw text in source object to test privacy stripping
        text: 'PROPRIETARY FORMULATION DETAILS THAT MUST NOT BE STORED IN BROWSER STORAGE',
      },
    ],
  };

  const selectedSec = {
    content_id: 'sec_01',
    section: '1. INDICATIONS AND USAGE',
    document_id: 'doc_disposable_88a',
    document_fingerprint: 'fp_disposable_99b',
    document_name: 'Investigational Dossier A',
    text: 'SENSITIVE CLINICAL TRIAL OUTCOMES BODY',
  };

  // Persist session before reload
  persistReviewContext(sourceDoc, selectedSec, mockStorage);

  // Raw storage inspection: confirm text is stripped
  const rawSaved = JSON.parse(mockStorage.getItem(GPR_REVIEW_CONTEXT_STORAGE_KEY));
  assert.strictEqual(rawSaved.version, 1);
  assert.strictEqual(rawSaved.activeSourceDocument.document_id, 'doc_disposable_88a');
  assert.strictEqual(rawSaved.activeSourceDocument.document_fingerprint, 'fp_disposable_99b');
  assert.strictEqual(rawSaved.activeSourceDocument.document_name, 'Investigational Dossier A');
  // Privacy assertion: sensitive text bodies must NOT exist in storage
  assert.strictEqual(rawSaved.activeSourceDocument.sections[0].text, undefined);
  assert.strictEqual(rawSaved.selectedSection.text, undefined);

  // Simulate page reload: load from storage
  const restored = loadPersistedReviewContext(mockStorage);
  assert.ok(restored !== null);
  assert.strictEqual(restored.activeSourceDocument.document_id, 'doc_disposable_88a');
  assert.strictEqual(restored.activeSourceDocument.document_fingerprint, 'fp_disposable_99b');
  assert.strictEqual(restored.activeSourceDocument.sections.length, 1);
  assert.strictEqual(restored.selectedSection.content_id, 'sec_01');
});

test('2. Missing, malformed, outdated version, and cleared browser session state', () => {
  // Case 2a: Missing storage
  assert.strictEqual(loadPersistedReviewContext(null), null);

  const mockStorage = new MockStorage();
  // Empty storage returns null
  assert.strictEqual(loadPersistedReviewContext(mockStorage), null);

  // Case 2b: Malformed non-JSON string
  mockStorage.setItem(GPR_REVIEW_CONTEXT_STORAGE_KEY, '{ invalid_json_syntax ');
  assert.strictEqual(loadPersistedReviewContext(mockStorage), null);
  // Corrupted item should be safely cleared
  assert.strictEqual(mockStorage.getItem(GPR_REVIEW_CONTEXT_STORAGE_KEY), null);

  // Case 2c: Outdated or incompatible schema version (version: 99)
  mockStorage.setItem(
    GPR_REVIEW_CONTEXT_STORAGE_KEY,
    JSON.stringify({ version: 99, activeSourceDocument: { document_id: 'doc_old' } })
  );
  assert.strictEqual(loadPersistedReviewContext(mockStorage), null);
  assert.strictEqual(mockStorage.getItem(GPR_REVIEW_CONTEXT_STORAGE_KEY), null);

  // Case 2d: Missing required document_id
  mockStorage.setItem(
    GPR_REVIEW_CONTEXT_STORAGE_KEY,
    JSON.stringify({ version: 1, activeSourceDocument: { invalid_key: true } })
  );
  assert.strictEqual(loadPersistedReviewContext(mockStorage), null);

  // Case 2e: Cleared session state
  mockStorage.setItem(
    GPR_REVIEW_CONTEXT_STORAGE_KEY,
    JSON.stringify({
      version: 1,
      activeSourceDocument: { document_id: 'doc_temp' },
      selectedSection: null,
    })
  );
  clearPersistedReviewContext(mockStorage);
  assert.strictEqual(mockStorage.getItem(GPR_REVIEW_CONTEXT_STORAGE_KEY), null);
  assert.strictEqual(loadPersistedReviewContext(mockStorage), null);
});

test('3. Privacy rule: serialization strictly omits source-document raw bytes and sensitive text bodies', () => {
  const sensitiveDoc = {
    document_id: 'doc_secure_100',
    document_fingerprint: 'fp_secure_200',
    document_name: 'Confidential Protocol',
    source_bytes: new Uint8Array([1, 2, 3, 4, 5]),
    raw_content: 'Entire 500-page proprietary dossier body...',
    sections: [
      {
        content_id: 'sec_dosage',
        section: 'DOSAGE',
        text: 'Internal dosing algorithm: take 45mg modified release formulation',
      },
    ],
  };

  const serialized = serializeReviewContext(sensitiveDoc, sensitiveDoc.sections[0]);
  assert.ok(serialized !== null);
  assert.strictEqual(serialized.version, 1);
  assert.strictEqual(serialized.activeSourceDocument.source_bytes, undefined);
  assert.strictEqual(serialized.activeSourceDocument.raw_content, undefined);
  assert.strictEqual(serialized.activeSourceDocument.sections[0].text, undefined);
  assert.strictEqual(serialized.selectedSection.text, undefined);
  assert.strictEqual(serialized.activeSourceDocument.document_id, 'doc_secure_100');
  assert.strictEqual(serialized.activeSourceDocument.document_fingerprint, 'fp_secure_200');
});

test('4. Update and reset review context lifecycle', () => {
  const mockStorage = new MockStorage();

  // Ingest Document 1
  const doc1 = { document_id: 'doc_1', document_fingerprint: 'fp_1', document_name: 'Draft v1' };
  persistReviewContext(doc1, null, mockStorage);
  let ctx = loadPersistedReviewContext(mockStorage);
  assert.strictEqual(ctx.activeSourceDocument.document_id, 'doc_1');
  assert.strictEqual(ctx.selectedSection, null);

  // Ingest Document 2 (superseding Document 1)
  const doc2 = { document_id: 'doc_2', document_fingerprint: 'fp_2', document_name: 'Draft v2' };
  persistReviewContext(doc2, null, mockStorage);
  ctx = loadPersistedReviewContext(mockStorage);
  assert.strictEqual(ctx.activeSourceDocument.document_id, 'doc_2');
  assert.strictEqual(ctx.selectedSection, null);

  // Clear context
  persistReviewContext(null, null, mockStorage);
  ctx = loadPersistedReviewContext(mockStorage);
  assert.strictEqual(ctx, null);
});
