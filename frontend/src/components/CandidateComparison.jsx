import React, { useState } from 'react';
import {
  GitCompare,
  ExternalLink,
  AlertCircle,
  ArrowRight,
  Search,
  Database,
  ShieldAlert,
  CheckCircle2,
  Layers
} from 'lucide-react';
import { api } from '../services/api';

export default function CandidateComparison({
  targetSection,
  candidateItem,
  onProceedToDecision,
}) {
  // Target Content State
  const [targetText, setTargetText] = useState(
    targetSection?.text ||
      'Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours with water. Do not exceed 6 tablets within 24 hours.'
  );

  // Active Selected Candidate State (initialized from candidateItem prop)
  const [selectedCandidate, setSelectedCandidate] = useState(candidateItem || null);
  const [candidateText, setCandidateText] = useState(
    candidateItem?.text ||
      'Adults: Take 1 to 2 tablets (500 mg) orally every 4 to 6 hours as needed. Maximum dosage: 8 tablets in 24 hours.'
  );

  // Candidate Discovery Search State
  const [searchQuery, setSearchQuery] = useState(
    targetSection?.section || targetSection?.document_name || 'aspirin'
  );
  const [sourceFilter, setSourceFilter] = useState('all');
  const [topK, setTopK] = useState(10);
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);

  // Comparison State
  const [differences, setDifferences] = useState([]);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState(null);

  // Adjust state when targetSection prop changes
  const [prevTargetSection, setPrevTargetSection] = useState(targetSection);
  if (targetSection !== prevTargetSection) {
    setPrevTargetSection(targetSection);
    if (targetSection?.text) {
      setTargetText(targetSection.text);
    }
    if (targetSection?.section) {
      setSearchQuery(targetSection.section);
    }
  }

  // Adjust state when candidateItem prop changes
  const [prevCandidateItem, setPrevCandidateItem] = useState(candidateItem);
  if (candidateItem !== prevCandidateItem) {
    setPrevCandidateItem(candidateItem);
    if (candidateItem) {
      setSelectedCandidate(candidateItem);
      if (candidateItem.text) {
        setCandidateText(candidateItem.text);
      }
    }
  }

  // Trigger candidate discovery via api.searchCandidates
  async function handleDiscoverCandidates(e) {
    if (e) e.preventDefault();
    setSearchError(null);

    const queryClean = (searchQuery || '').trim();
    if (!queryClean) {
      setSearchError('Search query is required to discover regulatory candidates.');
      return;
    }

    setSearching(true);
    try {
      const response = await api.searchCandidates({
        query: queryClean,
        source_filter: sourceFilter,
        section: targetSection?.section || null,
        target_text: targetText || null,
        top_k: Number(topK),
      });

      const items = response?.items || [];
      setSearchResults(items);
    } catch (err) {
      setSearchError(err.message || 'Failed to discover regulatory candidates.');
    } finally {
      setSearching(false);
    }
  }

  // Set selected candidate and update comparison reference text
  function handleSelectCandidate(candidate) {
    setSelectedCandidate(candidate);
    setCandidateText(candidate.text || '');
    setDifferences([]);
    setCompareError(null);
  }

  // Compute differences between current draft and selected candidate
  async function handleRunComparison() {
    setComparing(true);
    setCompareError(null);
    try {
      const diffs = await api.compareTexts(targetText, candidateText);
      setDifferences(diffs || []);
    } catch (err) {
      setCompareError(err.message || 'Comparison failed.');
    } finally {
      setComparing(false);
    }
  }

  function getSourceStyle(source) {
    const s = (source || '').toLowerCase();
    if (s.includes('dailymed')) {
      return {
        background: 'rgba(56, 189, 248, 0.12)',
        color: 'var(--color-dailymed)',
        border: '1px solid rgba(56, 189, 248, 0.3)',
      };
    }
    if (s.includes('openfda')) {
      return {
        background: 'rgba(167, 139, 250, 0.12)',
        color: 'var(--color-openfda)',
        border: '1px solid rgba(167, 139, 250, 0.3)',
      };
    }
    if (s.includes('internal') || s.includes('draft') || s.includes('ingest')) {
      return {
        background: 'rgba(20, 184, 166, 0.12)',
        color: 'var(--color-brand-teal)',
        border: '1px solid rgba(20, 184, 166, 0.3)',
      };
    }
    return {
      background: 'var(--bg-surface-elevated)',
      color: 'var(--text-secondary)',
      border: '1px solid var(--border-subtle)',
    };
  }

  return (
    <div>
      {/* Header */}
      <div className="screen-header">
        <div>
          <h2>Candidate Discovery & Comparison Workspace</h2>
          <p>Discover regulatory precedents across candidate stores and live authorities, then evaluate alignment side-by-side</p>
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

      {/* 1. Candidate Discovery Console */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">
          <span className="card-title">
            <Search size={16} color="var(--color-brand)" /> Search Regulatory Candidates
          </span>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            Queries ingested documents, DailyMed, and openFDA with cross-source deduplication
          </span>
        </div>

        <form onSubmit={handleDiscoverCandidates} className="input-group" style={{ flexWrap: 'wrap', gap: '0.6rem' }}>
          <input
            type="text"
            className="input-text"
            placeholder="Search by drug name, active ingredient, or section topic (e.g. dosage, aspirin, pediatric)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ minWidth: '280px', flex: 2 }}
          />

          <select
            className="select-box"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            style={{ minWidth: '160px' }}
          >
            <option value="all">All Sources</option>
            <option value="ingested">Ingested Documents</option>
            <option value="dailymed">DailyMed</option>
            <option value="openfda">openFDA</option>
          </select>

          <select
            className="select-box"
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            style={{ width: '90px' }}
          >
            <option value={5}>Top 5</option>
            <option value={10}>Top 10</option>
            <option value={20}>Top 20</option>
            <option value={50}>Top 50</option>
          </select>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={searching}
            style={{ fontSize: '0.84rem', padding: '0.6rem 1.1rem' }}
          >
            <Database size={14} /> {searching ? 'Discovering...' : 'Discover Candidates'}
          </button>
        </form>

        {/* Discovery Inline Error Banner */}
        {searchError && (
          <div style={{
            marginTop: '1rem',
            padding: '0.75rem 1rem',
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-sm)',
            color: '#fca5a5',
            fontSize: '0.82rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}>
            <AlertCircle size={16} color="var(--color-danger)" style={{ flexShrink: 0 }} />
            <span>{searchError}</span>
          </div>
        )}

        {/* Discovered Candidate Results List */}
        {searchResults.length > 0 && (
          <div style={{ marginTop: '1.25rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <span style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', fontWeight: '500' }}>
                Discovered Candidates ({searchResults.length}):
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Click "Select for Comparison" to populate the comparison workspace
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {searchResults.map((cand) => {
                const isSelected = selectedCandidate?.content_id === cand.content_id;
                const crossSources = cand.metadata?.cross_sources;
                const duplicateProvenance = cand.metadata?.duplicate_provenance;
                const hasFalseMatch = cand.false_match_warning || cand.metadata?.false_match_warning;

                return (
                  <div
                    key={cand.content_id}
                    className="result-item"
                    style={{
                      borderColor: isSelected ? 'var(--color-brand)' : 'var(--border-subtle)',
                      background: isSelected ? 'var(--bg-surface-elevated)' : 'var(--bg-main)',
                      padding: '0.85rem',
                    }}
                  >
                    <div className="result-title" style={{ alignItems: 'flex-start' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <span style={{ fontWeight: '600', color: '#fff', fontSize: '0.9rem' }}>
                            {cand.document_name || cand.product || 'Regulatory Record'}
                          </span>
                          <span className="badge" style={getSourceStyle(cand.source)}>
                            {cand.source}
                          </span>
                          {cand.section && (
                            <span className="badge badge-section">
                              {cand.section}
                            </span>
                          )}
                          {cand.subsection && (
                            <span className="badge badge-section" style={{ opacity: 0.85 }}>
                              {cand.subsection}
                            </span>
                          )}
                          {isSelected && (
                            <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-success)', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                              <CheckCircle2 size={11} /> Active in Comparison
                            </span>
                          )}
                        </div>

                        {/* Metadata & Provenance Row */}
                        <div style={{ display: 'flex', gap: '0.8rem', flexWrap: 'wrap', marginTop: '0.35rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {cand.content_id && (
                            <span>Content ID: <code style={{ color: 'var(--color-brand)' }}>{cand.content_id}</code></span>
                          )}
                          {cand.document_id && (
                            <span>Doc ID: <code>{cand.document_id}</code></span>
                          )}
                          {cand.source_identifier && (
                            <span>Source ID: <code>{cand.source_identifier}</code></span>
                          )}
                          {cand.page !== undefined && cand.page !== null && (
                            <span>Page: <strong>{cand.page}</strong></span>
                          )}
                          {cand.location && (
                            <span>Location: <strong>{cand.location}</strong></span>
                          )}
                        </div>

                        {/* Cross-Source & Duplicate Badges */}
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.35rem' }}>
                          {crossSources && crossSources.length > 1 && (
                            <span className="badge" style={{ background: 'rgba(14, 165, 233, 0.12)', color: 'var(--color-brand)', border: '1px solid rgba(14, 165, 233, 0.25)', fontSize: '0.72rem' }}>
                              <Layers size={10} /> Corroborated by: {crossSources.join(', ')}
                            </span>
                          )}
                          {duplicateProvenance && duplicateProvenance.length > 0 && (
                            <span className="badge" style={{ background: 'rgba(245, 158, 11, 0.12)', color: 'var(--color-warning)', border: '1px solid rgba(245, 158, 11, 0.25)', fontSize: '0.72rem' }}>
                              {duplicateProvenance.length} duplicate source record(s) merged
                            </span>
                          )}
                          {hasFalseMatch && (
                            <span className="badge" style={{ background: 'rgba(239, 68, 68, 0.15)', color: 'var(--color-danger)', border: '1px solid rgba(239, 68, 68, 0.3)', fontSize: '0.72rem' }}>
                              <ShieldAlert size={11} /> Human Review Recommended
                            </span>
                          )}
                        </div>
                      </div>

                      <button
                        onClick={() => handleSelectCandidate(cand)}
                        className={`btn ${isSelected ? 'btn-secondary' : 'btn-primary'}`}
                        style={{ fontSize: '0.76rem', padding: '0.35rem 0.75rem', flexShrink: 0 }}
                      >
                        {isSelected ? 'Selected' : 'Select for Comparison'}
                      </button>
                    </div>

                    <div className="result-text" style={{ maxHeight: '75px', marginTop: '0.5rem', fontSize: '0.82rem' }}>
                      {cand.text}
                    </div>

                    {cand.source_url && (
                      <div style={{ marginTop: '0.4rem' }}>
                        <a href={cand.source_url} target="_blank" rel="noopener noreferrer" className="trace-link" style={{ fontSize: '0.75rem' }}>
                          <ExternalLink size={11} /> Trace Official Source Record
                        </a>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Empty state when query executed but returned 0 items */}
        {!searching && searchResults.length === 0 && searchQuery && (
          <div style={{ marginTop: '1rem', padding: '0.85rem', background: 'var(--bg-main)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            No regulatory candidates were found for this search. Try a broader search term or change the source filter.
          </div>
        )}
      </div>

      {/* Comparison Inline Error Banner */}
      {compareError && (
        <div style={{
          marginBottom: '1rem',
          padding: '0.75rem 1rem',
          background: 'rgba(239, 68, 68, 0.12)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 'var(--radius-sm)',
          color: '#fca5a5',
          fontSize: '0.82rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}>
          <AlertCircle size={16} color="var(--color-danger)" style={{ flexShrink: 0 }} />
          <span>{compareError}</span>
        </div>
      )}

      {/* 2. Side-by-Side Comparison Columns */}
      <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
        {/* Left: Current Draft Content Column */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              Current Draft Content
            </span>
            <span className="badge badge-section">
              {targetSection?.section || 'Internal Section'}
            </span>
          </div>

          <div style={{ marginBottom: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.4rem' }}>
            <span>Document: <strong>{targetSection?.document_name || 'Draft Label v1.0'}</strong></span>
            {targetSection?.jurisdiction && (
              <span className="badge" style={{ fontSize: '0.7rem' }}>{targetSection.jurisdiction}</span>
            )}
          </div>

          {/* Target Provenance Metadata Row */}
          {(targetSection?.document_id || targetSection?.content_id) && (
            <div style={{ marginBottom: '0.5rem', fontSize: '0.74rem', color: 'var(--text-muted)', display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
              {targetSection?.document_id && (
                <span>Doc ID: <code>{targetSection.document_id}</code></span>
              )}
              {targetSection?.content_id && (
                <span>Content ID: <code style={{ color: 'var(--color-brand)' }}>{targetSection.content_id}</code></span>
              )}
            </div>
          )}

          <textarea
            className="input-text"
            rows={8}
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem' }}
          />
        </div>

        {/* Right: Selected Candidate Regulatory Precedent Column */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              Regulatory Candidate Reference
            </span>
            <span className="badge" style={getSourceStyle(selectedCandidate?.source)}>
              {selectedCandidate?.source || 'Candidate Reference'}
            </span>
          </div>

          <div style={{ marginBottom: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.4rem' }}>
            <span>Precedent: <strong>{selectedCandidate?.document_name || selectedCandidate?.product || 'Approved Reference'}</strong></span>
            {selectedCandidate?.source_identifier && (
              <span>ID: <code>{selectedCandidate.source_identifier}</code></span>
            )}
          </div>

          {/* Selected Candidate Provenance Details */}
          {(selectedCandidate?.content_id || selectedCandidate?.document_id || selectedCandidate?.page || selectedCandidate?.location) && (
            <div style={{ marginBottom: '0.5rem', fontSize: '0.74rem', color: 'var(--text-muted)', display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
              {selectedCandidate?.content_id && (
                <span>Content ID: <code style={{ color: 'var(--color-brand)' }}>{selectedCandidate.content_id}</code></span>
              )}
              {selectedCandidate?.document_id && (
                <span>Doc ID: <code>{selectedCandidate.document_id}</code></span>
              )}
              {selectedCandidate?.page !== undefined && selectedCandidate?.page !== null && (
                <span>Page: <strong>{selectedCandidate.page}</strong></span>
              )}
              {selectedCandidate?.location && (
                <span>Loc: <strong>{selectedCandidate.location}</strong></span>
              )}
            </div>
          )}

          {/* Selected Candidate Cross-Source Badges */}
          {selectedCandidate?.metadata?.cross_sources && selectedCandidate.metadata.cross_sources.length > 1 && (
            <div style={{ marginBottom: '0.5rem' }}>
              <span className="badge" style={{ background: 'rgba(14, 165, 233, 0.12)', color: 'var(--color-brand)', border: '1px solid rgba(14, 165, 233, 0.25)', fontSize: '0.72rem' }}>
                <Layers size={10} /> Corroborated by: {selectedCandidate.metadata.cross_sources.join(', ')}
              </span>
            </div>
          )}

          <textarea
            className="input-text"
            rows={8}
            value={candidateText}
            onChange={(e) => setCandidateText(e.target.value)}
            style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem' }}
          />

          {selectedCandidate?.source_url && (
            <div style={{ marginTop: '0.5rem' }}>
              <a href={selectedCandidate.source_url} target="_blank" rel="noopener noreferrer" className="trace-link">
                <ExternalLink size={12} /> Trace to Official Source
              </a>
            </div>
          )}
        </div>
      </div>

      {/* 3. Detected Differences & Decision Proceed Section */}
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
                candidateItem: selectedCandidate,
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
                    <span style={{ textTransform: 'capitalize' }}>{(diff.attribute || diff.aspect || 'aspect').replace('_', ' ')} distinction</span>
                    <span className="badge" style={{
                      background: diff.regulatory_impact === 'MAJOR' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.15)',
                      color: diff.regulatory_impact === 'MAJOR' ? 'var(--color-danger)' : 'var(--color-warning)',
                    }}>
                      {diff.regulatory_impact || 'REVIEW'} IMPACT
                    </span>
                  </div>
                  <span className="badge badge-section">{diff.difference_type || 'modification'}</span>
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
