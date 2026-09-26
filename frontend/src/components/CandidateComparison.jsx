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
  Layers,
  ChevronDown,
  ChevronUp,
  FileText,
  Sliders
} from 'lucide-react';
import { api } from '../services/api';

const DIMENSIONS = [
  {
    key: 'meaning',
    name: 'Meaning',
    number: '1',
    description: 'Directive intent, regulatory modality (mandatory vs permissive), and administration conditions',
  },
  {
    key: 'template',
    name: 'Template',
    number: '2',
    description: 'Regulatory slot patterns: Posology, Indication, Contraindication structure',
  },
  {
    key: 'context',
    name: 'Context',
    number: '3',
    description: 'Operational setting (Prescribing vs Study observation), specialized patient populations',
  },
  {
    key: 'structure',
    name: 'Structure',
    number: '4',
    description: 'Section hierarchy, paragraph vs table vs bullet list vs stepwise instructions',
  },
  {
    key: 'format',
    name: 'Format',
    number: '5',
    description: 'Quantitative vs qualitative, fixed dose vs titration/range, shorthand vs narrative',
  },
  {
    key: 'key_information',
    name: 'Key Information',
    number: '6',
    description: 'Exact clinical entities: drug, dose, unit, frequency, route, population, indication',
  },
];

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

  // Candidate Discovery Search State (Step 6.3 preserved)
  const [searchQuery, setSearchQuery] = useState(
    targetSection?.section || targetSection?.document_name || 'aspirin'
  );
  const [sourceFilter, setSourceFilter] = useState('all');
  const [topK, setTopK] = useState(10);
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);

  // Six-Dimensional Analysis State (Step 6.4)
  const [analysisResult, setAnalysisResult] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState(null);

  // Grouped Differences State & UI Filter
  const [differences, setDifferences] = useState([]);
  const [selectedDimensionFilter, setSelectedDimensionFilter] = useState('all');
  const [expandedFacts, setExpandedFacts] = useState({});
  const [showTraceabilityDetails, setShowTraceabilityDetails] = useState(false);

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
    setAnalysisResult(null);
    setDifferences([]);
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
    setAnalysisResult(null);
    setDifferences([]);
  }

  // Trigger candidate discovery via api.searchCandidates (Step 6.3 preserved)
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
    setAnalysisResult(null);
    setAnalysisError(null);
  }

  // Run Six-Dimensional Comparison via api.analyzeCandidates (Step 6.4)
  async function handleRunSixDimensionalComparison() {
    setAnalysisError(null);

    const cleanTarget = (targetText || '').trim();
    if (!cleanTarget) {
      setAnalysisError('Target document content is required before running comparison.');
      return;
    }

    if (!selectedCandidate) {
      setAnalysisError(
        'Please select a regulatory candidate reference before running comparison. Use the discovery search above to find and select a candidate.'
      );
      return;
    }

    setAnalyzing(true);
    try {
      const candidatePayload = {
        ...selectedCandidate,
        source: selectedCandidate.source || 'DailyMed',
        text: candidateText || selectedCandidate.text || '',
      };

      const options = {};
      if (targetSection?.content_id) options.target_content_id = targetSection.content_id;
      if (targetSection?.document_name) options.document_name = targetSection.document_name;
      if (targetSection?.document_id) options.document_id = targetSection.document_id;
      if (targetSection?.subsection) options.subsection = targetSection.subsection;
      if (targetSection?.location) options.location = targetSection.location;
      if (targetSection?.page !== undefined && targetSection?.page !== null) options.page = targetSection.page;
      if (targetSection?.content_type) options.content_type = targetSection.content_type;

      const result = await api.analyzeCandidates(
        cleanTarget,
        [candidatePayload],
        targetSection?.section || null,
        options
      );

      setAnalysisResult(result);
      const candDiffs = result?.candidates?.[0]?.differences || [];
      setDifferences(candDiffs);
    } catch (err) {
      setAnalysisError(err.message || 'Six-dimensional comparison failed.');
    } finally {
      setAnalyzing(false);
    }
  }

  function toggleFactExpansion(key) {
    setExpandedFacts((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
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

  function getStatusStyle(status) {
    const st = (status || '').toUpperCase();
    if (st === 'MATCH') {
      return {
        background: 'rgba(16, 185, 129, 0.15)',
        color: 'var(--color-success)',
        border: '1px solid rgba(16, 185, 129, 0.35)',
      };
    }
    if (st === 'PARTIAL') {
      return {
        background: 'rgba(245, 158, 11, 0.15)',
        color: 'var(--color-warning)',
        border: '1px solid rgba(245, 158, 11, 0.35)',
      };
    }
    if (st === 'MISMATCH') {
      return {
        background: 'rgba(239, 68, 68, 0.15)',
        color: 'var(--color-danger)',
        border: '1px solid rgba(239, 68, 68, 0.35)',
      };
    }
    return {
      background: 'var(--bg-surface-elevated)',
      color: 'var(--text-muted)',
      border: '1px solid var(--border-subtle)',
    };
  }

  // Derive primary candidate evaluation from analysis result
  const primaryCandidate = analysisResult?.candidates?.[0] || null;
  const matchResult = primaryCandidate?.multi_dimensional_match || null;
  const falseMatchWarning =
    primaryCandidate?.false_match_warning ||
    (analysisResult?.false_matches_detected > 0
      ? 'Critical regulatory discrepancy detected between current draft and reference.'
      : null);
  const primaryEvidence = primaryCandidate?.evidence?.[0] || null;
  const observedFacts = primaryEvidence?.observed_from_source || null;
  const targetFacts = primaryEvidence?.target_facts || null;

  // Filter differences by selected dimension tab
  const filteredDifferences = differences.filter((d) => {
    if (selectedDimensionFilter === 'all') return true;
    const dim = (d.source_dimension || '').toLowerCase();
    return dim === selectedDimensionFilter.toLowerCase();
  });

  const diffCounts = differences.reduce((acc, d) => {
    const dim = (d.source_dimension || 'other').toLowerCase();
    acc[dim] = (acc[dim] || 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      {/* Screen Header */}
      <div className="screen-header">
        <div>
          <h2>Candidate Discovery & Six-Dimensional Comparison Workspace</h2>
          <p>
            Evaluate regulatory alignment across Meaning, Template, Context, Structure, Format, and Key Information with human-in-the-loop governance
          </p>
        </div>
        <button
          onClick={handleRunSixDimensionalComparison}
          className="btn btn-primary"
          style={{ fontSize: '0.84rem', padding: '0.5rem 1rem' }}
          disabled={analyzing}
        >
          <GitCompare size={15} /> {analyzing ? 'Analyzing...' : 'Run Six-Dimensional Comparison'}
        </button>
      </div>

      {/* 1. Candidate Discovery Console (Step 6.3 preserved) */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">
          <span className="card-title">
            <Search size={16} color="var(--color-brand)" /> Search Regulatory Candidates
          </span>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            Queries candidate stores and live authorities with cross-source deduplication
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
          <div
            style={{
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
            }}
          >
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
                            <span
                              className="badge"
                              style={{
                                background: 'rgba(16, 185, 129, 0.15)',
                                color: 'var(--color-success)',
                                border: '1px solid rgba(16, 185, 129, 0.3)',
                              }}
                            >
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
      {analysisError && (
        <div
          style={{
            marginBottom: '1.25rem',
            padding: '0.75rem 1rem',
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-sm)',
            color: '#fca5a5',
            fontSize: '0.84rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <AlertCircle size={16} color="var(--color-danger)" style={{ flexShrink: 0 }} />
          <span>{analysisError}</span>
        </div>
      )}

      {/* 2. Side-by-Side Drafting & Precedent Columns */}
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
              {selectedCandidate?.source || 'No Candidate Selected'}
            </span>
          </div>

          <div style={{ marginBottom: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.4rem' }}>
            <span>Precedent: <strong>{selectedCandidate?.document_name || selectedCandidate?.product || 'Select a candidate above'}</strong></span>
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

      {/* 3. Six-Dimensional Regulatory Comparison Panel */}
      {analysisResult ? (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">
            <div>
              <span className="card-title">
                <GitCompare size={16} color="var(--color-brand)" /> Six-Dimensional Regulatory Alignment Assessment
              </span>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0 0' }}>
                Comprehensive multi-dimensional evaluation preventing reliance on raw semantic similarity
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              {primaryCandidate?.similarity_score !== undefined && primaryCandidate?.similarity_score !== null && (
                <span className="badge badge-section" style={{ fontSize: '0.75rem' }}>
                  Retrieval Similarity: {(primaryCandidate.similarity_score * 100).toFixed(0)}%
                </span>
              )}
              <span className="badge" style={{ background: 'rgba(14, 165, 233, 0.12)', color: 'var(--color-brand)', border: '1px solid rgba(14, 165, 233, 0.3)' }}>
                Session: {analysisResult.comparison_id}
              </span>
            </div>
          </div>

          {/* False Match Warning Banner */}
          {falseMatchWarning && (
            <div
              style={{
                marginBottom: '1.25rem',
                padding: '0.85rem 1.1rem',
                background: 'rgba(239, 68, 68, 0.12)',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                borderRadius: 'var(--radius-md)',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.75rem',
              }}
            >
              <ShieldAlert size={20} color="var(--color-danger)" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong style={{ color: '#fca5a5', fontSize: '0.88rem', display: 'block', marginBottom: '0.2rem' }}>
                  False Match Discrepancy Detected
                </strong>
                <p style={{ color: 'var(--text-primary)', fontSize: '0.82rem', margin: 0, lineHeight: 1.5 }}>
                  {falseMatchWarning}
                </p>
              </div>
            </div>
          )}

          {/* Overall Alignment Summary Banner */}
          <div
            style={{
              marginBottom: '1.25rem',
              padding: '0.85rem 1rem',
              background: 'var(--bg-main)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
            }}
          >
            <span style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
              Overall Multi-Dimensional Alignment Summary
            </span>
            <p style={{ fontSize: '0.86rem', color: '#fff', margin: 0, lineHeight: 1.5 }}>
              {matchResult?.overall_alignment_summary || analysisResult.summary_explanation || 'Evaluation complete across all six regulatory dimensions.'}
            </p>
          </div>

          {/* Six Dimension Cards Grid */}
          <div className="grid-3" style={{ marginBottom: '1.25rem', gap: '1rem' }}>
            {DIMENSIONS.map((dim) => {
              const evalData = matchResult?.[dim.key];
              const status = evalData?.status || 'NOT_APPLICABLE';
              const isExpanded = !!expandedFacts[dim.key];

              return (
                <div
                  key={dim.key}
                  style={{
                    background: 'var(--bg-main)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: '0.9rem',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    {/* Dimension Header & Status Badge */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.4rem', gap: '0.5rem' }}>
                      <div>
                        <strong style={{ color: '#fff', fontSize: '0.9rem' }}>
                          {dim.number}. {dim.name}
                        </strong>
                      </div>
                      <span className="badge" style={getStatusStyle(status)}>
                        {status}
                      </span>
                    </div>

                    <p style={{ fontSize: '0.73rem', color: 'var(--text-muted)', marginBottom: '0.6rem', lineHeight: 1.4 }}>
                      {dim.description}
                    </p>

                    {/* Alignment Score if present */}
                    {evalData?.score !== undefined && evalData?.score !== null && (
                      <div style={{ marginBottom: '0.6rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                          <span>Alignment Score</span>
                          <strong>{Math.round(evalData.score * 100)}%</strong>
                        </div>
                        <div style={{ height: '4px', background: 'rgba(255, 255, 255, 0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                          <div
                            style={{
                              height: '100%',
                              width: `${Math.min(Math.max(evalData.score * 100, 0), 100)}%`,
                              background:
                                evalData.score >= 0.8
                                  ? 'var(--color-success)'
                                  : evalData.score >= 0.5
                                  ? 'var(--color-warning)'
                                  : 'var(--color-danger)',
                            }}
                          />
                        </div>
                      </div>
                    )}

                    {/* Factual Analysis Details */}
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.45, marginBottom: '0.6rem' }}>
                      {evalData?.details || 'Dimension evaluated according to regulatory standards.'}
                    </p>
                  </div>

                  {/* Facts & Reasoning Expandable Section */}
                  <div>
                    {(evalData?.observed_from_source || evalData?.model_interpretation) && (
                      <div>
                        <button
                          type="button"
                          onClick={() => toggleFactExpansion(dim.key)}
                          className="btn btn-secondary"
                          style={{
                            width: '100%',
                            fontSize: '0.72rem',
                            padding: '0.3rem 0.5rem',
                            justifyContent: 'space-between',
                          }}
                        >
                          <span>{isExpanded ? 'Hide Evidence & Reasoning' : 'View Evidence & Reasoning'}</span>
                          {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                        </button>

                        {isExpanded && (
                          <div style={{ marginTop: '0.5rem', padding: '0.55rem', background: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', fontSize: '0.73rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                            {evalData?.observed_from_source && (
                              <div>
                                <span style={{ color: 'var(--color-brand)', fontWeight: '600', display: 'block', marginBottom: '0.15rem' }}>
                                  Observed from Source:
                                </span>
                                <span style={{ color: 'var(--text-secondary)' }}>{evalData.observed_from_source}</span>
                              </div>
                            )}
                            {evalData?.model_interpretation && (
                              <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.35rem' }}>
                                <span style={{ color: 'var(--color-openfda)', fontWeight: '600', display: 'block', marginBottom: '0.15rem' }}>
                                  Model Interpretation:
                                </span>
                                <span style={{ color: 'var(--text-secondary)' }}>{evalData.model_interpretation}</span>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Traceability & Audit Trail Toggle Button */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
            <button
              type="button"
              onClick={() => setShowTraceabilityDetails(!showTraceabilityDetails)}
              className="btn btn-secondary"
              style={{ fontSize: '0.76rem', padding: '0.35rem 0.75rem' }}
            >
              <Layers size={12} /> {showTraceabilityDetails ? 'Hide Audit Traceability' : 'View Audit Traceability'}
            </button>
          </div>

          {/* Expanded Audit Traceability Section */}
          {showTraceabilityDetails && (
            <div style={{ marginTop: '0.75rem', padding: '0.85rem', background: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontWeight: '600', color: '#fff', fontSize: '0.84rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <FileText size={14} color="var(--color-brand)" /> Traceable Source & Target Provenance (Two-Tier Audit Trail)
              </div>
              <div className="grid-2" style={{ gap: '0.8rem', fontSize: '0.76rem' }}>
                <div>
                  <span style={{ color: 'var(--color-brand)', fontWeight: '600', display: 'block', marginBottom: '0.3rem' }}>
                    Target Internal Draft
                  </span>
                  <div style={{ color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                    <span>Document: <strong>{targetFacts?.target_document_name || targetSection?.document_name || 'Draft Label'}</strong></span>
                    <span>Document ID: <code>{targetFacts?.target_document_id || targetSection?.document_id || 'Not specified'}</code></span>
                    <span>Content ID: <code>{targetFacts?.target_content_id || targetSection?.content_id || 'Not specified'}</code></span>
                    <span>Section: <strong>{targetFacts?.target_section || targetSection?.section || 'Not specified'}</strong></span>
                    {targetFacts?.target_subsection && <span>Subsection: {targetFacts.target_subsection}</span>}
                    {targetFacts?.target_location && <span>Location: {targetFacts.target_location}</span>}
                    {targetFacts?.target_page !== undefined && targetFacts?.target_page !== null && <span>Page: {targetFacts.target_page}</span>}
                  </div>
                </div>

                <div>
                  <span style={{ color: 'var(--color-dailymed)', fontWeight: '600', display: 'block', marginBottom: '0.3rem' }}>
                    Candidate Authoritative Source
                  </span>
                  <div style={{ color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                    <span>Source: <strong>{observedFacts?.source || selectedCandidate?.source || 'External Authority'}</strong></span>
                    <span>Document: <strong>{observedFacts?.document_name || selectedCandidate?.document_name || 'Regulatory Reference'}</strong></span>
                    <span>Source ID: <code>{observedFacts?.source_identifier || selectedCandidate?.source_identifier || 'Not specified'}</code></span>
                    <span>Content ID: <code>{observedFacts?.content_id || selectedCandidate?.content_id || 'Not specified'}</code></span>
                    <span>Section: <strong>{observedFacts?.section || selectedCandidate?.section || 'Not specified'}</strong></span>
                    {observedFacts?.location && <span>Location: {observedFacts.location}</span>}
                    {observedFacts?.page !== undefined && observedFacts?.page !== null && <span>Page: {observedFacts.page}</span>}
                    {observedFacts?.cross_sources && observedFacts.cross_sources.length > 1 && (
                      <span>Corroboration: <strong>{observedFacts.cross_sources.join(', ')}</strong></span>
                    )}
                    {(observedFacts?.source_url || selectedCandidate?.source_url) && (
                      <a
                        href={observedFacts?.source_url || selectedCandidate?.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="trace-link"
                        style={{ marginTop: '0.3rem' }}
                      >
                        <ExternalLink size={11} /> Open Authority Record
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Empty State before comparison run */
        <div className="card" style={{ marginBottom: '1.5rem', textAlign: 'center', padding: '2rem 1rem' }}>
          <Sliders size={28} color="var(--color-brand)" style={{ opacity: 0.6, marginBottom: '0.5rem' }} />
          <h3 style={{ fontSize: '1rem', color: '#fff', marginBottom: '0.25rem' }}>
            Six-Dimensional Comparison Pending
          </h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', maxWidth: '520px', margin: '0 auto 1rem auto' }}>
            Select a candidate reference above and click <strong>"Run Six-Dimensional Comparison"</strong> to evaluate alignment across Meaning, Template, Context, Structure, Format, and Key Information.
          </p>
        </div>
      )}

      {/* 4. Detected Differences & Decision Proceed Section */}
      <div className="card">
        <div className="card-header">
          <div>
            <span className="card-title">
              <AlertCircle size={16} color="var(--color-warning)" /> Detected Differences & Distinctions ({differences.length})
            </span>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginTop: '0.2rem' }}>
              Organized by regulatory dimension for rigorous human-in-the-loop review
            </span>
          </div>

          {onProceedToDecision && (
            <button
              onClick={() =>
                onProceedToDecision({
                  targetText,
                  candidateText,
                  differences,
                  candidateItem: selectedCandidate,
                  analysisResult,
                })
              }
              className="btn btn-primary"
              style={{ fontSize: '0.82rem', padding: '0.4rem 0.85rem' }}
            >
              Proceed to Decision Panel <ArrowRight size={13} />
            </button>
          )}
        </div>

        {/* Dimension Filter Tabs for Differences */}
        {differences.length > 0 && (
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
            <button
              type="button"
              onClick={() => setSelectedDimensionFilter('all')}
              className={`badge ${selectedDimensionFilter === 'all' ? 'badge-section' : ''}`}
              style={{
                cursor: 'pointer',
                border: selectedDimensionFilter === 'all' ? '1px solid var(--color-brand)' : '1px solid var(--border-subtle)',
                background: selectedDimensionFilter === 'all' ? 'var(--bg-surface-elevated)' : 'transparent',
                color: selectedDimensionFilter === 'all' ? '#fff' : 'var(--text-secondary)',
                padding: '0.3rem 0.6rem',
              }}
            >
              All ({differences.length})
            </button>

            {DIMENSIONS.map((dim) => {
              const count = diffCounts[dim.key] || 0;
              if (count === 0 && selectedDimensionFilter !== dim.key) return null;
              const isActive = selectedDimensionFilter === dim.key;

              return (
                <button
                  key={dim.key}
                  type="button"
                  onClick={() => setSelectedDimensionFilter(dim.key)}
                  className="badge"
                  style={{
                    cursor: 'pointer',
                    border: isActive ? '1px solid var(--color-brand)' : '1px solid var(--border-subtle)',
                    background: isActive ? 'var(--bg-surface-elevated)' : 'transparent',
                    color: isActive ? 'var(--color-brand)' : 'var(--text-secondary)',
                    padding: '0.3rem 0.6rem',
                  }}
                >
                  {dim.name} ({count})
                </button>
              );
            })}
          </div>
        )}

        {/* Differences List */}
        {differences.length === 0 ? (
          <div className="empty-state">
            <p>
              Click <strong>"Run Six-Dimensional Comparison"</strong> to execute difference detection across key dosage metrics, structure, and clinical phrasing.
            </p>
          </div>
        ) : filteredDifferences.length === 0 ? (
          <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            No differences found originating from the {selectedDimensionFilter} dimension.
          </div>
        ) : (
          <div>
            {filteredDifferences.map((diff, idx) => (
              <div key={diff.difference_id || idx} className="result-item">
                <div className="result-title">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <span style={{ textTransform: 'capitalize' }}>
                      {(diff.attribute || diff.aspect || 'aspect').replace('_', ' ')} distinction
                    </span>
                    {diff.source_dimension && (
                      <span className="badge badge-section" style={{ textTransform: 'capitalize', fontSize: '0.72rem' }}>
                        Dimension: {diff.source_dimension.replace('_', ' ')}
                      </span>
                    )}
                    <span
                      className="badge"
                      style={{
                        background:
                          diff.regulatory_impact === 'MAJOR'
                            ? 'rgba(239, 68, 68, 0.2)'
                            : 'rgba(245, 158, 11, 0.15)',
                        color:
                          diff.regulatory_impact === 'MAJOR'
                            ? 'var(--color-danger)'
                            : 'var(--color-warning)',
                      }}
                    >
                      {diff.regulatory_impact || 'REVIEW'} IMPACT
                    </span>
                  </div>
                  <span className="badge badge-section">{diff.difference_type || 'modification'}</span>
                </div>

                <p style={{ fontSize: '0.85rem', color: 'var(--text-primary)', marginBottom: '0.5rem', lineHeight: 1.45 }}>
                  {diff.explanation}
                </p>

                <div className="grid-2" style={{ gap: '0.5rem' }}>
                  {diff.current_value && (
                    <div
                      style={{
                        background: 'rgba(239, 68, 68, 0.08)',
                        padding: '0.5rem',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                      }}
                    >
                      <span style={{ fontSize: '0.72rem', color: '#f87171', display: 'block' }}>Current Value</span>
                      <code style={{ fontSize: '0.8rem', color: '#fff' }}>{diff.current_value}</code>
                    </div>
                  )}
                  {diff.candidate_value && (
                    <div
                      style={{
                        background: 'rgba(16, 185, 129, 0.08)',
                        padding: '0.5rem',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid rgba(16, 185, 129, 0.2)',
                      }}
                    >
                      <span style={{ fontSize: '0.72rem', color: '#34d399', display: 'block' }}>Candidate Value</span>
                      <code style={{ fontSize: '0.8rem', color: '#fff' }}>{diff.candidate_value}</code>
                    </div>
                  )}
                </div>

                {diff.reviewer_attention_required && (
                  <div style={{ marginTop: '0.4rem', fontSize: '0.73rem', color: 'var(--color-warning)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <ShieldAlert size={12} /> Human regulatory professional review required
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
