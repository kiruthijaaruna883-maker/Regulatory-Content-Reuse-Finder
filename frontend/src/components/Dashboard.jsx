import React, { useState, useEffect } from 'react';
import {
  Activity,
  Database,
  ShieldCheck,
  AlertTriangle,
  Layers,
  FileText,
  GitCompare,
  GitPullRequest,
  FileCheck2,
  ArrowRight,
  ChevronDown,
  ChevronRight
} from 'lucide-react';
import { api } from '../services/api';

export default function Dashboard({ onNavigateTab }) {
  const [sourcesStatus, setSourcesStatus] = useState(null);
  const [loadingSources, setLoadingSources] = useState(true);
  const [sourcesError, setSourcesError] = useState(null);
  const [showSourcesDetails, setShowSourcesDetails] = useState(false);

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
        label: 'Checking...',
        statusCode: null,
        statusText: 'Checking live connectivity',
        pill: (
          <div className="status-pill" style={{ color: 'var(--color-warning)', borderColor: 'rgba(245, 158, 11, 0.3)', background: 'rgba(245, 158, 11, 0.1)' }}>
            <span className="status-dot" style={{ background: 'var(--color-warning)', boxShadow: '0 0 8px var(--color-warning)' }} /> Checking
          </div>
        ),
      };
    }

    if (sourcesError || !sourceInfo) {
      return {
        label: 'Offline',
        statusCode: null,
        statusText: sourcesError || 'No status response',
        pill: (
          <div className="status-pill" style={{ color: 'var(--color-danger)', borderColor: 'rgba(239, 68, 68, 0.3)', background: 'rgba(239, 68, 68, 0.1)' }}>
            <span className="status-dot" style={{ background: 'var(--color-danger)', boxShadow: '0 0 8px var(--color-danger)' }} /> Offline
          </div>
        ),
      };
    }

    if (sourceInfo.status === 'healthy') {
      return {
        label: 'Connected',
        statusCode: sourceInfo.status_code || 200,
        statusText: 'Service operational',
        pill: (
          <div className="status-pill">
            <span className="status-dot" /> Connected
          </div>
        ),
      };
    }

    if (sourceInfo.status === 'degraded') {
      return {
        label: 'Degraded',
        statusCode: sourceInfo.status_code || 'Warning',
        statusText: 'Response latency elevated',
        pill: (
          <div className="status-pill" style={{ color: 'var(--color-warning)', borderColor: 'rgba(245, 158, 11, 0.3)', background: 'rgba(245, 158, 11, 0.1)' }}>
            <span className="status-dot" style={{ background: 'var(--color-warning)', boxShadow: '0 0 8px var(--color-warning)' }} /> Degraded
          </div>
        ),
      };
    }

    return {
      label: (sourceInfo.status || 'Unreachable'),
      statusCode: sourceInfo.status_code || null,
      statusText: sourceInfo.error || 'Connection issue',
      pill: (
        <div className="status-pill" style={{ color: 'var(--color-danger)', borderColor: 'rgba(239, 68, 68, 0.3)', background: 'rgba(239, 68, 68, 0.1)' }}>
          <span className="status-dot" style={{ background: 'var(--color-danger)', boxShadow: '0 0 8px var(--color-danger)' }} /> {sourceInfo.status}
        </div>
      ),
    };
  }

  const dailymedCard = getSourceCardState('dailymed');
  const openfdaCard = getSourceCardState('openfda');

  const workflowSteps = [
    {
      id: 'review',
      step: '01',
      title: 'Document Review',
      description: 'Upload draft submission documents, extract sections, and initiate reuse discovery.',
      icon: FileText,
      color: 'var(--color-brand)',
    },
    {
      id: 'comparison',
      step: '02',
      title: 'Candidate Comparison & Decision',
      description: 'Discover matching passages from DailyMed & openFDA, evaluate with 6D comparison matrix, and authorize human decisions.',
      icon: GitCompare,
      color: 'var(--color-dailymed)',
    },
    {
      id: 'changes',
      step: '03',
      title: 'Change Review',
      description: 'Detect cross-section occurrences, enforce validation rules, and review proposed changes.',
      icon: GitPullRequest,
      color: 'var(--color-brand-teal)',
    },
    {
      id: 'report',
      step: '04',
      title: 'Approved Change Report',
      description: 'Generate approved change manifest and independently verify the SHA-256 cryptographic audit trail.',
      icon: FileCheck2,
      color: 'var(--color-success)',
    },
  ];

  return (
    <div>
      {/* 1. Hero Section: Primary Action for Regulatory Users */}
      <div
        className="card"
        style={{
          marginBottom: '1.75rem',
          padding: '2rem 2.25rem',
          background: 'linear-gradient(135deg, #ffffff 0%, #f4f9f7 100%)',
          border: '1px solid var(--border-subtle)',
          boxShadow: '0 4px 20px -2px rgba(17, 34, 27, 0.06)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1.5rem',
        }}
      >
        <div style={{ maxWidth: '680px' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', padding: '0.2rem 0.6rem', borderRadius: '9999px', background: 'rgba(13, 148, 136, 0.08)', color: 'var(--color-brand)', fontSize: '0.78rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            <Layers size={13} /> Regulatory Affairs Content Governance
          </div>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem', letterSpacing: '-0.02em' }}>
            Regulatory Content Reuse Finder
          </h2>
          <p style={{ fontSize: '0.96rem', color: 'var(--text-secondary)', lineHeight: '1.5', margin: 0 }}>
            Find reusable regulatory content and review proposed changes across approved drug product labels and draft submissions.
          </p>
        </div>

        <div>
          <button
            onClick={() => onNavigateTab && onNavigateTab('review')}
            className="btn btn-primary"
            style={{
              fontSize: '0.98rem',
              padding: '0.8rem 1.6rem',
              fontWeight: 600,
              boxShadow: '0 4px 14px rgba(13, 148, 136, 0.35)',
            }}
          >
            <FileText size={18} />
            Start a New Review
            <ArrowRight size={16} />
          </button>
        </div>
      </div>

      {/* 2. Main Regulatory Workflow Lifecycle Section */}
      <div className="card" style={{ marginBottom: '1.75rem' }}>
        <div className="card-header">
          <span className="card-title">
            <Layers size={16} color="var(--color-brand)" /> Regulatory Workflow Lifecycle
          </span>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            Sequential Human-in-the-Loop Pipeline
          </span>
        </div>

        <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginBottom: '1.25rem', lineHeight: '1.5' }}>
          Follow the four-stage regulatory lifecycle from draft document review to final cryptographic audit verification:
        </p>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '1rem',
          }}
        >
          {workflowSteps.map((wf) => {
            const IconComponent = wf.icon;
            return (
              <div
                key={wf.id}
                onClick={() => onNavigateTab && onNavigateTab(wf.id)}
                style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: '1.1rem',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  cursor: onNavigateTab ? 'pointer' : 'default',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'var(--color-brand)';
                  e.currentTarget.style.background = '#ffffff';
                  e.currentTarget.style.boxShadow = '0 2px 10px rgba(13, 148, 136, 0.12)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border-subtle)';
                  e.currentTarget.style.background = 'var(--bg-surface-elevated)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.65rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                      <IconComponent size={17} color={wf.color} />
                      <strong style={{ fontSize: '0.88rem', color: 'var(--text-primary)' }}>{wf.title}</strong>
                    </div>
                    <span style={{ fontSize: '0.7rem', fontWeight: '700', color: 'var(--text-muted)' }}>
                      {wf.step}
                    </span>
                  </div>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: '1.45', margin: 0 }}>
                    {wf.description}
                  </p>
                </div>

                {onNavigateTab && (
                  <div style={{ marginTop: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.76rem', color: wf.color, fontWeight: '600' }}>
                    <span>Launch Stage</span> <ArrowRight size={12} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Data Source Status (Visually Secondary & Expandable) */}
      <div className="card" style={{ background: 'var(--bg-surface)' }}>
        <div
          onClick={() => setShowSourcesDetails(!showSourcesDetails)}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            cursor: 'pointer',
            userSelect: 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            {showSourcesDetails ? <ChevronDown size={17} color="var(--color-brand)" /> : <ChevronRight size={17} color="var(--color-brand)" />}
            <span style={{ fontSize: '0.92rem', fontWeight: '600', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <Activity size={16} color="var(--color-brand)" /> Data Source Status
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginLeft: '0.5rem' }}>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                DailyMed: <strong>{dailymedCard.label}</strong>
              </span>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>•</span>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                openFDA: <strong>{openfdaCard.label}</strong>
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }} onClick={(e) => e.stopPropagation()}>
            <button
              onClick={loadSourcesStatus}
              className="btn btn-secondary"
              style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
              disabled={loadingSources}
              title="Refresh source connection status"
            >
              <Activity size={13} /> {loadingSources ? 'Checking...' : 'Source Status'}
            </button>
          </div>
        </div>

        {sourcesError && (
          <div style={{ marginTop: '0.85rem', padding: '0.65rem 0.9rem', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#b91c1c', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
            <AlertTriangle size={15} />
            <span>Connection warning: {sourcesError}</span>
          </div>
        )}

        {/* Secondary Detailed Cards */}
        {showSourcesDetails && (
          <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
            <div className="grid-2">
              {/* DailyMed Card */}
              <div style={{ background: 'var(--bg-main)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.88rem', display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--text-primary)' }}>
                    <Database size={15} color="var(--color-dailymed)" /> NLM DailyMed Live
                  </span>
                  <span className="badge badge-dailymed">Public Web Service</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                  <div>
                    <div style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                      {dailymedCard.label}
                    </div>
                    <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                      {dailymedCard.statusCode ? `Technical status: HTTP ${dailymedCard.statusCode}` : dailymedCard.statusText}
                    </div>
                  </div>
                  {dailymedCard.pill}
                </div>
                <div style={{ marginTop: '0.75rem', fontSize: '0.74rem', color: 'var(--text-muted)', paddingTop: '0.5rem', borderTop: '1px solid var(--border-subtle)' }}>
                  Retrieves authoritative FDA-approved drug labels and structured SPL XML sections on-demand.
                </div>
              </div>

              {/* openFDA Card */}
              <div style={{ background: 'var(--bg-main)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.88rem', display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--text-primary)' }}>
                    <ShieldCheck size={15} color="var(--color-openfda)" /> FDA / openFDA Live
                  </span>
                  <span className="badge badge-openfda">Official FDA API</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                  <div>
                    <div style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                      {openfdaCard.label}
                    </div>
                    <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                      {openfdaCard.statusCode ? `Technical status: HTTP ${openfdaCard.statusCode}` : openfdaCard.statusText}
                    </div>
                  </div>
                  {openfdaCard.pill}
                </div>
                <div style={{ marginTop: '0.75rem', fontSize: '0.74rem', color: 'var(--text-muted)', paddingTop: '0.5rem', borderTop: '1px solid var(--border-subtle)' }}>
                  Provides structured NDC directories, approved indications, dosage forms, and labeling metadata.
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
