import React, { useState, useEffect } from 'react';
import {
  Search,
  Activity,
  Database,
  ShieldCheck,
  ExternalLink,
  CheckCircle,
  AlertTriangle,
  FileText,
  Layers,
  ArrowRight
} from 'lucide-react';
import { api } from '../services/api';

export default function Dashboard({ onNavigateToSearch, onSelectCandidateForComparison }) {
  const [sourcesStatus, setSourcesStatus] = useState(null);
  const [loadingSources, setLoadingSources] = useState(true);
  const [sourcesError, setSourcesError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('aspirin');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);

  useEffect(() => {
    loadSourcesStatus();
  }, []);

  async function loadSourcesStatus() {
    try {
      setLoadingSources(true);
      setSourcesError(null);
      const res = await api.getSourcesStatus();
      setSourcesStatus(res);
    } catch (err) {
      console.error('Failed to load sources status:', err);
      setSourcesError(err.message || 'Unable to fetch source status');
    } finally {
      setLoadingSources(false);
    }
  }

  function getSourceCardState(sourceKey) {
    const sourceInfo = sourcesStatus?.sources?.[sourceKey];

    if (loadingSources) {
      return {
        label: 'CHECKING...',
        subtitle: 'Querying live service...',
        pill: (
          <div className="status-pill" style={{ color: 'var(--color-warning)', borderColor: 'rgba(245, 158, 11, 0.3)', background: 'rgba(245, 158, 11, 0.1)' }}>
            <span className="status-dot" style={{ background: 'var(--color-warning)', boxShadow: '0 0 8px var(--color-warning)' }} /> Checking
          </div>
        ),
      };
    }

    if (sourcesError || !sourceInfo) {
      return {
        label: 'OFFLINE',
        subtitle: sourcesError || 'No status response',
        pill: (
          <div className="status-pill" style={{ color: 'var(--color-danger)', borderColor: 'rgba(239, 68, 68, 0.3)', background: 'rgba(239, 68, 68, 0.1)' }}>
            <span className="status-dot" style={{ background: 'var(--color-danger)', boxShadow: '0 0 8px var(--color-danger)' }} /> Offline
          </div>
        ),
      };
    }

    if (sourceInfo.status === 'healthy') {
      return {
        label: 'CONNECTED',
        subtitle: `Status: ${sourceInfo.status_code || 200} OK`,
        pill: (
          <div className="status-pill">
            <span className="status-dot" /> Live
          </div>
        ),
      };
    }

    if (sourceInfo.status === 'degraded') {
      return {
        label: 'DEGRADED',
        subtitle: `Status: ${sourceInfo.status_code || 'Warning'}`,
        pill: (
          <div className="status-pill" style={{ color: 'var(--color-warning)', borderColor: 'rgba(245, 158, 11, 0.3)', background: 'rgba(245, 158, 11, 0.1)' }}>
            <span className="status-dot" style={{ background: 'var(--color-warning)', boxShadow: '0 0 8px var(--color-warning)' }} /> Degraded
          </div>
        ),
      };
    }

    return {
      label: (sourceInfo.status || 'UNREACHABLE').toUpperCase(),
      subtitle: sourceInfo.error || 'Connection issue',
      pill: (
        <div className="status-pill" style={{ color: 'var(--color-danger)', borderColor: 'rgba(239, 68, 68, 0.3)', background: 'rgba(239, 68, 68, 0.1)' }}>
          <span className="status-dot" style={{ background: 'var(--color-danger)', boxShadow: '0 0 8px var(--color-danger)' }} /> {sourceInfo.status}
        </div>
      ),
    };
  }

  const dailymedCard = getSourceCardState('dailymed');
  const openfdaCard = getSourceCardState('openfda');

  async function handleQuickSearch(e) {
    if (e) e.preventDefault();
    if (!searchQuery.trim()) return;

    setSearching(true);
    setSearchError(null);
    try {
      const data = await api.searchRegulatorySources(searchQuery, sourceFilter, null, 5);
      setSearchResults(data);
    } catch (err) {
      setSearchError(err.message);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div>
      <div className="screen-header">
        <div>
          <h2>Regulatory Domain Dashboard</h2>
          <p>Real-time live regulatory intelligence, external source health, and content reuse governance</p>
        </div>
        <button
          onClick={loadSourcesStatus}
          className="btn btn-secondary"
          style={{ fontSize: '0.8rem', padding: '0.4rem 0.8rem' }}
          disabled={loadingSources}
        >
          <Activity size={14} /> {loadingSources ? 'Checking...' : 'Refresh Health'}
        </button>
      </div>

      {sourcesError && (
        <div style={{ marginBottom: '1.25rem', padding: '0.75rem', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#fca5a5' }}>
          <AlertTriangle size={16} style={{ verticalAlign: 'middle', marginRight: '0.5rem' }} />
          Status fetch warning: {sourcesError}
        </div>
      )}

      {/* Top Source Health Cards */}
      <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
        {/* DailyMed Live Source Card */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <Database size={16} color="var(--color-dailymed)" /> NLM DailyMed Live
            </span>
            <span className="badge badge-dailymed">Public Web Service</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem' }}>
            <div>
              <div style={{ fontSize: '1.25rem', fontWeight: '700', color: '#fff' }}>
                {dailymedCard.label}
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                {dailymedCard.subtitle}
              </div>
            </div>
            {dailymedCard.pill}
          </div>
          <div style={{ marginTop: '0.8rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Retrieves authoritative FDA-approved drug labels and XML sections on-demand.
          </div>
        </div>

        {/* openFDA Live Source Card */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <ShieldCheck size={16} color="var(--color-openfda)" /> FDA / openFDA Live
            </span>
            <span className="badge badge-openfda">Official FDA API</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem' }}>
            <div>
              <div style={{ fontSize: '1.25rem', fontWeight: '700', color: '#fff' }}>
                {openfdaCard.label}
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                {openfdaCard.subtitle}
              </div>
            </div>
            {openfdaCard.pill}
          </div>
          <div style={{ marginTop: '0.8rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Provides structured NDC, indications, dosing, and contraindications.
          </div>
        </div>

        {/* AI & Governance Architecture Card */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <Layers size={16} color="var(--color-brand)" /> Two-Agent Architecture
            </span>
            <span className="status-pill">Human Decision Gated</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem' }}>
            <div>
              <div style={{ fontSize: '1.25rem', fontWeight: '700', color: '#fff' }}>
                V1 FOUNDATION
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                Agent 1 & 2 Initialized
              </div>
            </div>
            <span className="badge" style={{ background: 'rgba(14, 165, 233, 0.1)', color: 'var(--color-brand)' }}>
              Compliant
            </span>
          </div>
          <div style={{ marginTop: '0.8rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Content Analysis (Agent 1) + Document Change (Agent 2) strictly governed by human approval.
          </div>
        </div>
      </div>

      {/* Live Regulatory Query Console */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">
          <span className="card-title">
            <Search size={16} /> Live Regulatory Content Search
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Searches directly against external live services
          </span>
        </div>

        <form onSubmit={handleQuickSearch} className="input-group">
          <input
            type="text"
            className="input-text"
            placeholder="Search by drug name or active ingredient (e.g. aspirin, ibuprofen, acetaminophen)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <select
            className="select-box"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          >
            <option value="all">All Sources (DailyMed + openFDA)</option>
            <option value="dailymed">DailyMed Only</option>
            <option value="openfda">openFDA Only</option>
          </select>
          <button type="submit" className="btn btn-primary" disabled={searching}>
            {searching ? 'Querying Live...' : 'Search Live Sources'}
          </button>
        </form>

        {searchError && (
          <div style={{ marginTop: '1rem', padding: '0.75rem', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#fca5a5' }}>
            <AlertTriangle size={16} style={{ verticalAlign: 'middle', marginRight: '0.5rem' }} />
            {searchError}
          </div>
        )}

        {/* Live Search Results */}
        {searchResults && (
          <div style={{ marginTop: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <span style={{ fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
                Retrieved <strong>{searchResults.total_results}</strong> candidate items for query <em>"{searchResults.query}"</em>
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Retrieved at: {new Date(searchResults.retrieved_at).toLocaleTimeString()}
              </span>
            </div>

            {searchResults.items.length === 0 ? (
              <div className="empty-state">
                <p>No regulatory records matched query "{searchResults.query}". Try a standard generic or brand name.</p>
              </div>
            ) : (
              <div>
                {searchResults.items.map((item) => (
                  <div key={item.content_id} className="result-item">
                    <div className="result-title">
                      <span>{item.document_name || item.product || 'Regulatory Content'}</span>
                      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                        <span className={`badge ${item.source === 'DailyMed' ? 'badge-dailymed' : 'badge-openfda'}`}>
                          {item.source}
                        </span>
                        {item.section && <span className="badge badge-section">{item.section}</span>}
                      </div>
                    </div>

                    <div className="result-meta">
                      {item.source_identifier && (
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          ID: <code>{item.source_identifier}</code>
                        </span>
                      )}
                      {item.version && (
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          v{item.version}
                        </span>
                      )}
                      {item.date && (
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          Date: {item.date}
                        </span>
                      )}
                    </div>

                    <div className="result-text">
                      {item.text}
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                      {item.source_url ? (
                        <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="trace-link">
                          <ExternalLink size={12} /> Official Regulatory Source Record
                        </a>
                      ) : <span />}

                      {onSelectCandidateForComparison && (
                        <button
                          onClick={() => onSelectCandidateForComparison(item)}
                          className="btn btn-secondary"
                          style={{ fontSize: '0.78rem', padding: '0.35rem 0.7rem' }}
                        >
                          Compare with Document <ArrowRight size={12} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
