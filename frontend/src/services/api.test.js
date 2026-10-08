import test from 'node:test';
import assert from 'node:assert';
import { api } from './api.js';

test('api.searchCandidates forwards exclude_document_id and document_id in request body', async () => {
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
    });

    assert.ok(capturedUrl.includes('/candidates/search'));
    assert.strictEqual(capturedBody.query, 'acetaminophen');
    assert.strictEqual(capturedBody.source_filter, 'all');
    assert.strictEqual(capturedBody.section, 'INDICATIONS AND USAGE');
    assert.strictEqual(capturedBody.target_text, 'Adults: Take 1 tablet');
    assert.strictEqual(capturedBody.top_k, 5);
    assert.strictEqual(capturedBody.exclude_document_id, 'doc_source_test_01');
    assert.strictEqual(capturedBody.document_id, 'doc_source_test_01');
  } finally {
    global.fetch = originalFetch;
  }
});
