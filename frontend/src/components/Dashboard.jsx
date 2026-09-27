import React, { useState, useEffect } from 'react';
import {
  Activity,
  Database,
  ShieldCheck,
  AlertTriangle,
  Layers,
  FileText,
  GitCompare,
  CheckSquare,
  GitPullRequest,
  FileCheck2,
  ArrowRight
} from 'lucide-react';
import { api } from '../services/api';

export default function Dashboard({ onNavigateTab }) {
  const [sourcesStatus, setSourcesStatus] = useState(null);
  const [loadingSources, setLoadingSources] = useState(true);
  const [sourcesError, setSourcesError] = useState(null);

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

  const workflowSteps = [
    {
      id: 'review',
      step: '01',
      title: 'Document Review',
      description: 'Select draft submission sections and analyze target text for regulatory reuse candidates.',
      icon: FileText,
      color: 'var(--color-brand)',
    },
    {
      id: 'comparison',
      step: '02',
      title: 'Candidate Comparison',
      description: 'Discover matching passages from DailyMed & openFDA and evaluate with 6D comparison matrix.',
      icon: GitCompare,
      color: 'var(--color-dailymed)',
    },
    {
      id: 'decision',
      step: '03',
      title: 'Decision Panel',
      description: 'Record human reviewer decisions (Accept, Reject, Modify) with mandatory regulatory rationale.',
      icon: CheckSquare,
      color: 'var(--color-warning)',
    },
    {
      id: 'changes',
      step: '04',
      title: 'Change Review',
      description: 'Detect cross-section occurrences, enforce validation rules, and review proposed changes.',
      icon: GitPullRequest,
      color: 'var(--color-brand-teal)',
    },
    {
      id: 'report',
      step: '05',
      title: 'Approved Change Report',
      description: 'Generate approved change manifest and independently verify the SHA-256 cryptographic audit trail.',
      icon: FileCheck2,
      color: 'var(--color-success)',
    },
  ];

  return (
    <div>
      {/* Screen Header */}
      <div className="screen-header" style={{ marginBottom: '1.75rem' }}>
        <div>
          <h2>Regulatory Domain Dashboard</h2>
          <p style={{ maxWidth: '820px', lineHeight: '1.5' }}>
            Regulatory Content Reuse Finder (GPR) assists regulatory affairs teams in discovering,
            comparing, and governing content reuse across approved drug product labels and submission documents.
          </p>
        </div>
        <button
          onClick={loadSourcesStatus}
          className="btn btn-secondary"
          style={{ fontSize: '0.8rem', padding: '0.45rem 0.85rem' }}
          disabled={loadingSources}
        >
          <Activity size={14} /> {loadingSources ? 'Checking...' : 'Refresh Health'}
        </button>
      </div>

      {sourcesError && (
        <div style={{ marginBottom: '1.5rem', padding: '0.75rem 1rem', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#fca5a5', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <AlertTriangle size={16} />
          <span>Status fetch warning: {sourcesError}</span>
        </div>
      )}

      {/* Live Regulatory Data Sources Section */}
      <div style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: '600', color: 'var(--text-primary)', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={16} color="var(--color-brand)" /> Live Regulatory Sources
          </h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Authoritative external health authority service connectivity
          </span>
        </div>

        {/* 2-Column Symmetrical Grid for Live Sources */}
        <div className="grid-2">
          {/* DailyMed Live Source Card */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div className="card-header">
                <span className="card-title">
                  <Database size={16} color="var(--color-dailymed)" /> NLM DailyMed Live
                </span>
                <span className="badge badge-dailymed">Public Web Service</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem' }}>
                <div>
                  <div style={{ fontSize: '1.25rem', fontWeight: '700', color: 'var(--text-primary)' }}>
                    {dailymedCard.label}
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    {dailymedCard.subtitle}
                  </div>
                </div>
                {dailymedCard.pill}
              </div>
            </div>
            <div style={{ marginTop: '1rem', fontSize: '0.78rem', color: 'var(--text-muted)', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)' }}>
              Retrieves authoritative FDA-approved drug labels and structured SPL XML sections on-demand.
            </div>
          </div>

          {/* openFDA Live Source Card */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div className="card-header">
                <span className="card-title">
                  <ShieldCheck size={16} color="var(--color-openfda)" /> FDA / openFDA Live
                </span>
                <span className="badge badge-openfda">Official FDA API</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem' }}>
                <div>
                  <div style={{ fontSize: '1.25rem', fontWeight: '700', color: 'var(--text-primary)' }}>
                    {openfdaCard.label}
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    {openfdaCard.subtitle}
                  </div>
                </div>
                {openfdaCard.pill}
              </div>
            </div>
            <div style={{ marginTop: '1rem', fontSize: '0.78rem', color: 'var(--text-muted)', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)' }}>
              Provides structured NDC directories, approved indications, dosage forms, and labeling metadata.
            </div>
          </div>
        </div>
      </div>

      {/* Main Regulatory Workflow Navigation Section */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Layers size={16} color="var(--color-brand)" /> Regulatory Workflow Lifecycle
          </span>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            Sequential Human-in-the-Loop Pipeline
          </span>
        </div>

        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '1.25rem', lineHeight: '1.5' }}>
          Follow the five-stage regulatory lifecycle from draft document review to final cryptographic audit verification:
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
                  padding: '1rem',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  cursor: onNavigateTab ? 'pointer' : 'default',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'var(--color-brand)';
                  e.currentTarget.style.background = '#ffffff';
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(13, 148, 136, 0.15)';
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
                      <strong style={{ fontSize: '0.86rem', color: 'var(--text-primary)' }}>{wf.title}</strong>
                    </div>
                    <span style={{ fontSize: '0.7rem', fontWeight: '700', color: 'var(--text-muted)' }}>
                      {wf.step}
                    </span>
                  </div>
                  <p style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', lineHeight: '1.45', margin: 0 }}>
                    {wf.description}
                  </p>
                </div>

                {onNavigateTab && (
                  <div style={{ marginTop: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.74rem', color: wf.color, fontWeight: '600' }}>
                    <span>Launch Stage</span> <ArrowRight size={12} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
