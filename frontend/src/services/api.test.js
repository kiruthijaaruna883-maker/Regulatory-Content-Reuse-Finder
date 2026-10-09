import test from 'node:test';
import assert from 'node:assert';
import { api } from './api.js';

test('api.searchCandidates forwards exclude_document_id, exclude_document_fingerprint, document_id, and target_content_id', async () => {
  let capturedUrl = null;
  let capturedBody = null;

  const originalFetch = global.fetch;
  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      json: async () => ({ items: [], total_results: 0, query: capturedBody.query }),
    };
  };

  try {
    await api.searchCandidates({
      query: 'acetaminophen',
      source_filter: 'all',
      section: 'INDICATIONS AND USAGE',
      target_text: 'Adults: Take 1 tablet',
      top_k: 5,
      exclude_document_id: 'doc_source_test_01',
      document_id: 'doc_source_test_01',
      exclude_document_fingerprint: 'fp_abc123',
      target_content_id: 'cnt_001',
    });

    assert.ok(capturedUrl.includes('/candidates/search'));
    assert.strictEqual(capturedBody.query, 'acetaminophen');
    assert.strictEqual(capturedBody.source_filter, 'all');
    assert.strictEqual(capturedBody.section, 'INDICATIONS AND USAGE');
    assert.strictEqual(capturedBody.target_text, 'Adults: Take 1 tablet');
    assert.strictEqual(capturedBody.top_k, 5);
    assert.strictEqual(capturedBody.exclude_document_id, 'doc_source_test_01');
    assert.strictEqual(capturedBody.document_id, 'doc_source_test_01');
    assert.strictEqual(capturedBody.exclude_document_fingerprint, 'fp_abc123');
    assert.strictEqual(capturedBody.target_content_id, 'cnt_001');
  } finally {
    global.fetch = originalFetch;
  }
});

test('api.analyzeCandidates forwards exclude_document_id and exclude_document_fingerprint in request body', async () => {
  let capturedUrl = null;
  let capturedBody = null;

  const originalFetch = global.fetch;
  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      json: async () => ({ candidates: [] }),
    };
  };

  try {
    await api.analyzeCandidates(
      'Target clinical text for review',
      [],
      'DOSAGE AND ADMINISTRATION',
      {
        document_id: 'doc_target_42',
        exclude_document_id: 'doc_target_42',
        exclude_document_fingerprint: 'fp_xyz789',
        target_content_id: 'content_sec_1',
      }
    );

    assert.ok(capturedUrl.includes('/content/analyze'));
    assert.strictEqual(capturedBody.target_text, 'Target clinical text for review');
    assert.strictEqual(capturedBody.section_name, 'DOSAGE AND ADMINISTRATION');
    assert.strictEqual(capturedBody.document_id, 'doc_target_42');
    assert.strictEqual(capturedBody.exclude_document_id, 'doc_target_42');
    assert.strictEqual(capturedBody.exclude_document_fingerprint, 'fp_xyz789');
    assert.strictEqual(capturedBody.target_content_id, 'content_sec_1');
  } finally {
    global.fetch = originalFetch;
  }
});

test('api.searchCandidates and api.analyzeCandidates preserve backward compatibility when exclusions are omitted', async () => {
  let capturedSearchBody = null;
  let capturedAnalyzeBody = null;

  const originalFetch = global.fetch;
  global.fetch = async (url, options) => {
    if (url.includes('/candidates/search')) {
      capturedSearchBody = JSON.parse(options.body);
      return { ok: true, json: async () => ({ items: [] }) };
    }
    if (url.includes('/content/analyze')) {
      capturedAnalyzeBody = JSON.parse(options.body);
      return { ok: true, json: async () => ({ candidates: [] }) };
    }
    return { ok: true, json: async () => ({}) };
  };

  try {
    await api.searchCandidates({ query: 'aspirin' });
    assert.strictEqual(capturedSearchBody.query, 'aspirin');
    assert.strictEqual(capturedSearchBody.exclude_document_id, undefined);
    assert.strictEqual(capturedSearchBody.exclude_document_fingerprint, undefined);

    await api.analyzeCandidates('Some target text');
    assert.strictEqual(capturedAnalyzeBody.target_text, 'Some target text');
    assert.strictEqual(capturedAnalyzeBody.exclude_document_id, undefined);
    assert.strictEqual(capturedAnalyzeBody.exclude_document_fingerprint, undefined);
  } finally {
    global.fetch = originalFetch;
  }
});

test('api.getDocument requests GET /documents/{document_id}', async () => {
  let capturedUrl = null;
  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      json: async () => ({ document_id: 'doc_123', document_name: 'Test Doc', sections: [] }),
    };
  };

  try {
    const res = await api.getDocument('doc_123');
    assert.ok(capturedUrl.includes('/documents/doc_123'));
    assert.strictEqual(res.document_id, 'doc_123');
  } finally {
    global.fetch = originalFetch;
  }
});

test('api.getDocumentSection requests GET /documents/section/{content_id}', async () => {
  let capturedUrl = null;
  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      json: async () => ({ content_id: 'chk_456', text: 'Safe clinical text' }),
    };
  };

  try {
    const res = await api.getDocumentSection('chk_456');
    assert.ok(capturedUrl.includes('/documents/section/chk_456'));
    assert.strictEqual(res.text, 'Safe clinical text');
  } finally {
    global.fetch = originalFetch;
  }
});
