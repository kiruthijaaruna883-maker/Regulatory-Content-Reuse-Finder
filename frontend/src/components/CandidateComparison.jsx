import React, { useState } from 'react';
import { GitCompare, ExternalLink, AlertCircle, CheckCircle, ArrowRight, Shield } from 'lucide-react';
import { api } from '../services/api';

export default function CandidateComparison({
  targetSection,
  candidateItem,
  onProceedToDecision,
}) {
  const [targetText, setTargetText] = useState(
    targetSection?.text || 'Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours with water. Do not exceed 6 tablets within 24 hours.'
  );
  const [candidateText, setCandidateText] = useState(
    candidateItem?.text || 'Adults: Take 1 to 2 tablets (500 mg) orally every 4 to 6 hours as needed. Maximum dosage: 8 tablets in 24 hours.'
  );
  const [differences, setDifferences] = useState([]);
  const [comparing, setComparing] = useState(false);

  async function handleRunComparison() {
    setComparing(true);
    try {
      const diffs = await api.compareTexts(targetText, candidateText);
      setDifferences(diffs);
    } catch (err) {
      alert(`Comparison failed: ${err.message}`);
    } finally {
      setComparing(false);
    }
  }

  return (
    <div>
      <div className="screen-header">
        <div>
          <h2>Candidate Comparison & Difference Detection</h2>
          <p>Side-by-side evaluation of current internal draft against live external regulatory precedent</p>
        </div>
        <button
          onClick={handleRunComparison}
          className="btn btn-primary"
          style={{ fontSize: '0.82rem', padding: '0.4rem 0.9rem' }}
          disabled={comparing}
        >
          <GitCompare size={14} /> {comparing ? 'Comparing...' : 'Compute Differences'}
        </button>
      </div>

      {/* Side-by-Side Comparison Columns */}
      <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
        {/* Current Content Column */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              Current Draft Content
            </span>
            <span className="badge badge-section">
              {targetSection?.section || 'Internal Section'}
            </span>
          </div>
          <div style={{ marginBottom: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            Document: <strong>{targetSection?.document_name || 'Draft Label v1.0'}</strong>
          </div>
          <textarea
            className="input-text"
            rows={8}
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem' }}
          />
        </div>

        {/* Candidate Regulatory Precedent Column */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              Regulatory Candidate Reference
            </span>
            <span className={`badge ${candidateItem?.source === 'DailyMed' ? 'badge-dailymed' : 'badge-openfda'}`}>
              {candidateItem?.source || 'DailyMed'}
            </span>
          </div>
          <div style={{ marginBottom: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between' }}>
            <span>Precedent: <strong>{candidateItem?.document_name || candidateItem?.product || 'Approved Reference'}</strong></span>
            {candidateItem?.source_identifier && (
              <span>ID: <code>{candidateItem.source_identifier}</code></span>
            )}
          </div>
          <textarea
            className="input-text"
            rows={8}
            value={candidateText}
            onChange={(e) => setCandidateText(e.target.value)}
            style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem' }}
          />
          {candidateItem?.source_url && (
            <div style={{ marginTop: '0.5rem' }}>
              <a href={candidateItem.source_url} target="_blank" rel="noopener noreferrer" className="trace-link">
                <ExternalLink size={12} /> Trace to Official Source
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Detected Differences & Evidence Traceability */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <AlertCircle size={16} color="var(--color-warning)" /> Detected Differences & Key Distinctions ({differences.length})
          </span>
          {onProceedToDecision && (
            <button
              onClick={() => onProceedToDecision({
                targetText,
                candidateText,
                differences,
                candidateItem
              })}
              className="btn btn-primary"
              style={{ fontSize: '0.82rem', padding: '0.4rem 0.8rem' }}
            >
              Proceed to Decision Panel <ArrowRight size={13} />
            </button>
          )}
        </div>

        {differences.length === 0 ? (
          <div className="empty-state">
            <p>Click <strong>"Compute Differences"</strong> to execute difference detection across key dosage metrics, structure, and clinical phrasing.</p>
          </div>
        ) : (
          <div>
            {differences.map((diff, idx) => (
              <div key={diff.difference_id || idx} className="result-item">
                <div className="result-title">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ textTransform: 'capitalize' }}>{diff.aspect.replace('_', ' ')} distinction</span>
                    <span className="badge" style={{
                      background: diff.regulatory_impact === 'MAJOR' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.15)',
                      color: diff.regulatory_impact === 'MAJOR' ? 'var(--color-danger)' : 'var(--color-warning)',
                    }}>
                      {diff.regulatory_impact} IMPACT
                    </span>
                  </div>
                  <span className="badge badge-section">{diff.difference_type}</span>
                </div>

                <p style={{ fontSize: '0.85rem', color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                  {diff.explanation}
                </p>

                <div className="grid-2" style={{ gap: '0.5rem' }}>
                  {diff.current_value && (
                    <div style={{ background: 'rgba(239, 68, 68, 0.08)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                      <span style={{ fontSize: '0.72rem', color: '#f87171', display: 'block' }}>Current Value</span>
                      <code style={{ fontSize: '0.8rem', color: '#fff' }}>{diff.current_value}</code>
                    </div>
                  )}
                  {diff.candidate_value && (
                    <div style={{ background: 'rgba(16, 185, 129, 0.08)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                      <span style={{ fontSize: '0.72rem', color: '#34d399', display: 'block' }}>Candidate Value</span>
                      <code style={{ fontSize: '0.8rem', color: '#fff' }}>{diff.candidate_value}</code>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
