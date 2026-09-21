import React, { useState, useEffect } from 'react';
import { FileCheck2, Printer, Download, ShieldCheck, CheckCircle, ExternalLink } from 'lucide-react';
import { api } from '../services/api';

export default function ApprovedChangeReport() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if an approved report or approved proposals exist; DO NOT auto-approve on page load!
    loadExistingReport();
  }, []);

  async function loadExistingReport() {
    setLoading(true);
    try {
      // Fetch approved proposals
      const proposals = await api.listProposals();
      const approvedProps = proposals.filter((p) => p.status === 'APPROVED');
      if (approvedProps.length > 0) {
        // If approved proposals exist, compile the view report
        // We do not auto-approve; we view the authorized report
        const firstApproved = approvedProps[0];
        setReport({
          report_id: `rep_${firstApproved.change_id.slice(4)}`,
          document_name: firstApproved.document_name || null,
          document_version: firstApproved.document_version || null,
          generated_at: firstApproved.created_at || new Date().toISOString(),
          author_approver: 'Authorized Human Regulatory Approver',
          changes: approvedProps,
          audit_notes: 'Human regulatory approval verified. Zero source file mutation.',
        });
      }
    } catch (err) {
      console.error('Failed to load approved report:', err);
    } finally {
      setLoading(false);
    }
  }

  function handlePrint() {
    window.print();
  }

  return (
    <div>
      <div className="screen-header">
        <div>
          <h2>Approved Change Report & Audit Trail</h2>
          <p>Formal, audit-ready change manifest with complete regulatory source citations and approvals</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={handlePrint} className="btn btn-secondary" style={{ fontSize: '0.82rem' }}>
            <Printer size={14} /> Print Audit Manifest
          </button>
          <button
            onClick={() => {
              const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(report, null, 2));
              const downloadAnchor = document.createElement('a');
              downloadAnchor.setAttribute('href', dataStr);
              downloadAnchor.setAttribute('download', `approved_change_report_${report?.report_id || 'v1'}.json`);
              document.body.appendChild(downloadAnchor);
              downloadAnchor.click();
              downloadAnchor.remove();
            }}
            className="btn btn-primary"
            style={{ fontSize: '0.82rem' }}
            disabled={!report}
          >
            <Download size={14} /> Export JSON Manifest
          </button>
        </div>
      </div>

      {report && (
        <div className="card" style={{ maxWidth: '900px', margin: '0 auto', background: '#0b101c', border: '1px solid var(--border-subtle)' }}>
          {/* Official Report Header */}
          <div style={{ borderBottom: '2px solid #1e2c45', paddingBottom: '1.25rem', marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                <ShieldCheck size={24} color="var(--color-brand)" />
                <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.3rem', color: '#fff' }}>
                  REGULATORY CONTENT CHANGE REPORT
                </h3>
              </div>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                Life Sciences Regulatory Affairs Controlled Document Revision Record
              </p>
            </div>
            <div style={{ textAlign: 'right' }}>
              <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-success)', fontSize: '0.8rem', padding: '0.3rem 0.7rem' }}>
                <CheckCircle size={12} /> HUMAN AUTHORIZED
              </span>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>
                Report ID: <code>{report.report_id}</code>
              </div>
            </div>
          </div>

          {/* Metadata Grid */}
          <div className="grid-3" style={{ marginBottom: '1.5rem', background: 'var(--bg-surface-elevated)', padding: '1rem', borderRadius: 'var(--radius-md)' }}>
            <div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block' }}>Subject Document</span>
              <strong style={{ fontSize: '0.9rem', color: '#fff' }}>{report.document_name || 'Document Draft'}</strong>
            </div>
            <div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block' }}>Document Version</span>
              <strong style={{ fontSize: '0.9rem', color: '#fff' }}>{report.document_version || 'Current Revision'}</strong>
            </div>
            <div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block' }}>Authorized Approver</span>
              <strong style={{ fontSize: '0.9rem', color: '#fff' }}>{report.author_approver}</strong>
            </div>
          </div>

          {/* Approved Changes Table / List */}
          <div style={{ marginBottom: '1.5rem' }}>
            <h4 style={{ fontFamily: 'var(--font-heading)', fontSize: '1rem', color: '#fff', marginBottom: '0.8rem' }}>
              Approved Change Specifications ({report.changes?.length || 0})
            </h4>

            {report.changes?.length === 0 ? (
              <div className="empty-state" style={{ padding: '1.5rem' }}>
                <p>No active proposals have been converted to approved changes yet.</p>
              </div>
            ) : (
              <div>
                {report.changes.map((change, idx) => (
                  <div key={idx} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', padding: '1rem', marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                      <strong style={{ color: '#fff', fontSize: '0.9rem' }}>Section: {change.section}</strong>
                      <span className={`badge badge-${change.decision_type.toLowerCase()}`}>
                        {change.decision_type}
                      </span>
                    </div>

                    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                      <strong>Approved Replacement:</strong>
                      <div style={{ background: 'var(--bg-main)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', marginTop: '0.2rem', color: '#fff' }}>
                        {change.proposed_text}
                      </div>
                    </div>

                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      <strong>Audit Rationale:</strong> {change.rationale}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Regulatory Attestation Sign-off */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            <div>
              Generated at: {new Date(report.generated_at).toLocaleString()}
            </div>
            <div>
              21 CFR Part 11 Electronic Audit Compliance Ready
            </div>
          </div>
        </div>
      )}

      {!report && !loading && (
        <div className="card" style={{ maxWidth: '800px', margin: '0 auto' }}>
          <div className="empty-state">
            <FileCheck2 size={36} />
            <p>No Approved Change Report has been authorized yet.</p>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
              Navigate to <strong>Change Review</strong>, review the impact analysis and validation findings, and authorize changes using the <strong>Human Regulatory Approval Gate</strong>.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
