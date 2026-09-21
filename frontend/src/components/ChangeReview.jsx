import React, { useState, useEffect } from 'react';
import {
  GitPullRequest,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  ArrowRight,
  ShieldAlert,
  Search,
  ExternalLink,
  Layers,
  FileCheck2,
  XCircle,
} from 'lucide-react';
import { api } from '../services/api';

export default function ChangeReview({ activeDecision, onNavigateToReport }) {
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [impactResults, setImpactResults] = useState({});
  const [approverName, setApproverName] = useState('Senior Regulatory Director');
  // CRITICAL REQUIREMENT: Must never default to true
  const [approvalConfirmed, setApprovalConfirmed] = useState(false);
  const [approvingId, setApprovingId] = useState(null);
  const [approvedReports, setApprovedReports] = useState({});

  useEffect(() => {
    loadProposals();
  }, []);

  async function loadProposals() {
    setLoading(true);
    try {
      const data = await api.listProposals();
      setProposals(data);
      for (const p of data) {
        handleValidate(p);
      }
    } catch (err) {
      console.error('Failed to load proposals:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleValidate(proposal) {
    try {
      const impact = await api.validateChange(proposal);
      setImpactResults((prev) => ({ ...prev, [proposal.change_id]: impact }));
    } catch (err) {
      console.error('Validation failed:', err);
    }
  }

  async function handleApproveProposal(proposal) {
    if (!approvalConfirmed) {
      alert('Explicit human approval confirmation checkbox must be checked before authorizing.');
      return;
    }
    if (!approverName.trim()) {
      alert('Valid regulatory approver identity is required.');
      return;
    }

    setApprovingId(proposal.change_id);
    try {
      const report = await api.approveAndGenerateReport({
        approver_name: approverName.trim(),
        approval_confirmation: true, // Explicitly confirmed by human
        proposal_ids: [proposal.change_id],
        document_name: proposal.document_name || null,
        document_version: proposal.document_version || null,
        audit_notes: `Authorized by ${approverName.trim()} with full source traceability verified.`,
      });
      setApprovedReports((prev) => ({ ...prev, [proposal.change_id]: report }));
      // Reload proposals to refresh status
      await loadProposals();
    } catch (err) {
      alert(`Approval authorization failed: ${err.message}`);
    } finally {
      setApprovingId(null);
    }
  }

  return (
    <div>
      <div className="screen-header">
        <div>
          <h2>Controlled Document Change Review</h2>
          <p>Controlled change proposals formulated by Agent 2 — Strict human approval gate required before report generation</p>
        </div>
        {onNavigateToReport && (
          <button onClick={onNavigateToReport} className="btn btn-primary" style={{ fontSize: '0.82rem' }}>
            View Approved Change Report <ArrowRight size={13} />
          </button>
        )}
      </div>

      {proposals.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <GitPullRequest size={36} />
            <p>No active change proposals. Record a <strong>REUSE</strong> or <strong>ADAPT</strong> decision in the Decision Panel to initiate controlled proposals.</p>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
              Note: REJECT decisions preserve original content and do not generate change proposals.
            </p>
          </div>
        </div>
      ) : (
        <div>
          {proposals.map((prop) => {
            const impact = impactResults[prop.change_id] || prop.impact_analysis;
            const approvedReport = approvedReports[prop.change_id];
            const isApproved = prop.status === 'APPROVED' || !!approvedReport;

            return (
              <div key={prop.change_id} className="card" style={{ marginBottom: '1.5rem' }}>
                {/* Header */}
                <div className="card-header">
                  <span className="card-title">
                    <GitPullRequest size={16} color="var(--color-brand)" /> Proposal <code>{prop.change_id}</code> — {prop.section}
                  </span>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <span className={`badge badge-${prop.decision_type.toLowerCase()}`}>
                      {prop.decision_type}
                    </span>
                    <span className="status-pill" style={{
                      background: isApproved ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                      color: isApproved ? 'var(--color-success)' : 'var(--color-warning)',
                      borderColor: isApproved ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)',
                    }}>
                      {isApproved ? 'AUTHORIZED / APPROVED' : 'PENDING HUMAN APPROVAL'}
                    </span>
                  </div>
                </div>

                {/* Original vs Proposed Text Grid */}
                <div className="grid-2" style={{ marginBottom: '1rem' }}>
                  <div style={{ background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '0.85rem', borderRadius: 'var(--radius-md)' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: '600', color: '#f87171', display: 'block', marginBottom: '0.3rem' }}>
                      Original Regulatory Content (Unchanged)
                    </span>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{prop.original_text}</p>
                  </div>

                  <div style={{ background: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)', padding: '0.85rem', borderRadius: 'var(--radius-md)' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: '600', color: '#34d399', display: 'block', marginBottom: '0.3rem' }}>
                      Proposed Replacement / Adapted Content
                    </span>
                    <p style={{ fontSize: '0.85rem', color: '#fff' }}>{prop.proposed_text}</p>
                  </div>
                </div>

                {/* Rationale & Provenance Traceability */}
                <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', marginBottom: '0.8rem' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>
                    Documented Regulatory Rationale:
                  </span>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                    {prop.rationale}
                  </span>
                  {prop.source_evidence && (
                    <div style={{ marginTop: '0.4rem', fontSize: '0.78rem', color: 'var(--color-brand)' }}>
                      <strong>Evidence Citation:</strong> {prop.source_evidence.source} ({prop.source_evidence.exact_quote})
                    </div>
                  )}
                </div>

                {/* 4-Layer Related Occurrences */}
                {prop.related_occurrences && prop.related_occurrences.length > 0 && (
                  <div style={{ marginBottom: '1rem', background: 'var(--bg-surface-elevated)', padding: '0.85rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                    <span style={{ fontSize: '0.8rem', fontWeight: '600', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.5rem' }}>
                      <Layers size={14} color="var(--color-brand)" /> Related Occurrences ({prop.related_occurrences.length})
                    </span>
                    {prop.related_occurrences.map((occ, idx) => (
                      <div key={idx} style={{ fontSize: '0.8rem', background: 'var(--bg-main)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', marginBottom: '0.4rem', border: '1px solid var(--border-subtle)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                          <strong>{occ.section}</strong>
                          <span className="badge badge-section" style={{ fontSize: '0.7rem' }}>
                            {occ.match_type.replace('_', ' ').toUpperCase()}
                          </span>
                        </div>
                        <p style={{ color: 'var(--text-secondary)', margin: '0.2rem 0' }}>{occ.current_text}</p>
                        {occ.reason && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                            Basis: {occ.reason}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Impact Analysis: Observed vs Potential */}
                {impact && (
                  <div style={{ marginBottom: '1rem', background: 'var(--bg-surface-elevated)', padding: '0.85rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <span style={{ fontSize: '0.8rem', fontWeight: '600', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <AlertTriangle size={14} color="var(--color-warning)" /> Regulatory Impact Assessment
                      </span>
                      <span className="badge" style={{
                        background: impact.risk_level === 'HIGH' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                        color: impact.risk_level === 'HIGH' ? 'var(--color-danger)' : 'var(--color-success)',
                      }}>
                        {impact.risk_level} RISK
                      </span>
                    </div>

                    <div className="grid-2" style={{ gap: '0.5rem', marginBottom: '0.5rem' }}>
                      <div style={{ background: 'var(--bg-main)', padding: '0.5rem', borderRadius: 'var(--radius-sm)' }}>
                        <strong style={{ fontSize: '0.75rem', color: '#34d399', display: 'block', marginBottom: '0.2rem' }}>
                          Observed Impacts (Direct)
                        </strong>
                        <ul style={{ margin: 0, paddingLeft: '1rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                          {(impact.observed_impacts || [`Direct replacement in ${prop.section}`]).map((obs, i) => (
                            <li key={i}>{obs}</li>
                          ))}
                        </ul>
                      </div>
                      <div style={{ background: 'var(--bg-main)', padding: '0.5rem', borderRadius: 'var(--radius-sm)' }}>
                        <strong style={{ fontSize: '0.75rem', color: '#fbbf24', display: 'block', marginBottom: '0.2rem' }}>
                          Potential Impacts (Reviewer Verification Required)
                        </strong>
                        <ul style={{ margin: 0, paddingLeft: '1rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                          {(impact.potential_impacts && impact.potential_impacts.length > 0) ? (
                            impact.potential_impacts.map((pot, i) => <li key={i}>{pot}</li>)
                          ) : (
                            <li>No high-risk cross-section dependencies identified.</li>
                          )}
                        </ul>
                      </div>
                    </div>

                    {/* Validation Findings */}
                    {impact.findings && (
                      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.4rem' }}>
                        {impact.findings.map((f, i) => (
                          <span key={i} className="badge" style={{
                            background: f.passed ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                            color: f.passed ? 'var(--color-success)' : 'var(--color-danger)',
                            fontSize: '0.7rem',
                          }}>
                            {f.rule_id}: {f.message}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* MANDATORY HUMAN APPROVAL GATE */}
                <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem', background: 'rgba(59, 130, 246, 0.04)', padding: '1rem', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem' }}>
                    <ShieldCheck size={18} color="var(--color-brand)" />
                    <strong style={{ fontSize: '0.85rem', color: '#fff' }}>Human Regulatory Approval Gate</strong>
                  </div>

                  {isApproved ? (
                    <div style={{ color: 'var(--color-success)', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <CheckCircle2 size={16} /> This change has been authorized and included in Approved Change Report (ID: <code>{approvedReport?.report_id || 'rep_active'}</code>).
                    </div>
                  ) : (
                    <div>
                      <div style={{ marginBottom: '0.6rem' }}>
                        <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.2rem' }}>
                          Authorizing Approver Identity
                        </label>
                        <input
                          type="text"
                          className="input-text"
                          value={approverName}
                          onChange={(e) => setApproverName(e.target.value)}
                          style={{ width: '100%', maxWidth: '400px' }}
                        />
                      </div>

                      <div style={{ marginBottom: '0.8rem' }}>
                        <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={approvalConfirmed}
                            onChange={(e) => setApprovalConfirmed(e.target.checked)}
                            style={{ marginTop: '0.2rem' }}
                          />
                          <span style={{ fontSize: '0.78rem', color: 'var(--text-primary)' }}>
                            I explicitly confirm that I have evaluated the proposed change, deterministic validation findings, and impact analysis, and authorize this change for inclusion in the Approved Change Report.
                          </span>
                        </label>
                      </div>

                      <button
                        onClick={() => handleApproveProposal(prop)}
                        className="btn btn-primary"
                        disabled={!approvalConfirmed || !approverName.trim() || approvingId === prop.change_id}
                        style={{ fontSize: '0.82rem' }}
                      >
                        <FileCheck2 size={14} /> {approvingId === prop.change_id ? 'Authorizing...' : 'Authorize & Include in Approved Report'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
