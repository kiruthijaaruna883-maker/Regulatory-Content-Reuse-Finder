import React from 'react';
import {
  FileCheck2,
  Printer,
  Download,
  ShieldCheck,
  CheckCircle,
  ExternalLink,
  AlertCircle,
  FileText,
  Shield,
  Layers,
  Info
} from 'lucide-react';

export default function ApprovedChangeReport({ approvedReport }) {
  const report = approvedReport || null;

  function handlePrint() {
    window.print();
  }

  function handleExportJson() {
    if (!report) return;
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(report, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `approved_change_report_${report.report_id || 'manifest'}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  }

  // Format ISO timestamp nicely if valid
  function formatTimestamp(ts) {
    if (!ts) return 'Not available in returned report';
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  }

  return (
    <div>
      {/* Top Header & Export Controls */}
      <div className="screen-header">
        <div>
          <h2>Approved Change Report & Audit Trail</h2>
          <p>Authorized Internal Regulatory Affairs Change Record with complete source citations and verification history</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            type="button"
            onClick={handlePrint}
            className="btn btn-secondary"
            style={{ fontSize: '0.82rem' }}
            disabled={!report}
          >
            <Printer size={14} /> Print Audit Manifest
          </button>
          <button
            type="button"
            onClick={handleExportJson}
            className="btn btn-primary"
            style={{ fontSize: '0.82rem' }}
            disabled={!report}
          >
            <Download size={14} /> Export JSON Manifest
          </button>
        </div>
      </div>

      {report ? (
        <div
          className="card"
          style={{
            maxWidth: '920px',
            margin: '0 auto',
            background: '#0b101c',
            border: '1px solid var(--border-subtle)',
          }}
        >
          {/* Regulatory Authority Boundary Disclaimer */}
          <div
            style={{
              padding: '0.65rem 0.9rem',
              background: 'rgba(59, 130, 246, 0.08)',
              border: '1px solid rgba(59, 130, 246, 0.25)',
              borderRadius: 'var(--radius-sm)',
              marginBottom: '1.25rem',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.5rem',
              fontSize: '0.76rem',
              color: '#93c5fd',
              lineHeight: 1.45,
            }}
          >
            <Info size={16} color="var(--color-brand)" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <strong>REGULATORY AUTHORITY BOUNDARY:</strong> This document is an{' '}
              <strong>Authorized Internal Regulatory Affairs Change Record</strong>. It represents internal review,
              justification, and authorization by authorized company personnel. It does{' '}
              <em>not</em> constitute FDA, EMA, or any other government health authority approval, clearance, or submission acceptance.
            </div>
          </div>

          {/* Official Report Title Header */}
          <div
            style={{
              borderBottom: '2px solid #1e2c45',
              paddingBottom: '1.25rem',
              marginBottom: '1.5rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              flexWrap: 'wrap',
              gap: '1rem',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                <ShieldCheck size={26} color="var(--color-brand)" />
                <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.25rem', color: '#fff' }}>
                  REGULATORY CONTENT CHANGE REPORT
                </h3>
              </div>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                Controlled Content Revision Record • Zero Autonomous Document Mutation
              </p>
            </div>
            <div style={{ textAlign: 'right' }}>
              <span
                className="badge"
                style={{
                  background: report.approval_confirmation ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                  color: report.approval_confirmation ? 'var(--color-success)' : 'var(--color-danger)',
                  fontSize: '0.78rem',
                  padding: '0.35rem 0.75rem',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                }}
              >
                {report.approval_confirmation ? (
                  <>
                    <CheckCircle size={13} /> HUMAN AUTHORIZED
                  </>
                ) : (
                  <>
                    <AlertCircle size={13} /> UNCONFIRMED
                  </>
                )}
              </span>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
                Report ID: <code>{report.report_id || 'Not available in returned report'}</code>
              </div>
            </div>
          </div>

          {/* 1. Report Identity & Subject Document Metadata */}
          <div
            className="grid-3"
            style={{
              marginBottom: '1.5rem',
              background: 'var(--bg-surface-elevated)',
              padding: '1rem',
              borderRadius: 'var(--radius-md)',
              gap: '1rem',
            }}
          >
            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                Subject Document
              </span>
              <strong style={{ fontSize: '0.86rem', color: '#fff' }}>
                {report.document_name || 'Not available in returned report'}
              </strong>
            </div>

            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                Document Version
              </span>
              <strong style={{ fontSize: '0.86rem', color: '#fff' }}>
                {report.document_version || 'Not available in returned report'}
              </strong>
            </div>

            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                Authorized Approver
              </span>
              <strong style={{ fontSize: '0.86rem', color: '#fff' }}>
                {report.author_approver || 'Not available in returned report'}
              </strong>
            </div>

            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                Report Generated
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                {formatTimestamp(report.generated_at)}
              </span>
            </div>

            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                Approval Timestamp
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                {formatTimestamp(report.approval_timestamp)}
              </span>
            </div>

            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                Human Confirmation
              </span>
              <span style={{ fontSize: '0.8rem', color: report.approval_confirmation ? 'var(--color-success)' : 'var(--color-danger)' }}>
                {report.approval_confirmation ? 'Confirmed True' : 'Not Confirmed'}
              </span>
            </div>
          </div>

          {/* 2. Authorized Decision IDs & Audit Trail Notes */}
          <div
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.9rem',
              marginBottom: '1.5rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.5rem' }}>
              <Shield size={15} color="var(--color-brand)" />
              <strong style={{ fontSize: '0.84rem', color: '#fff' }}>
                Internal Audit Information & Traceability
              </strong>
            </div>

            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Authorized Decision IDs: </span>
                {report.decision_ids && report.decision_ids.length > 0 ? (
                  report.decision_ids.map((id) => (
                    <code key={id} style={{ marginRight: '0.4rem' }}>
                      {id}
                    </code>
                  ))
                ) : (
                  <span>Not available in returned report</span>
                )}
              </div>

              <div>
                <span style={{ color: 'var(--text-muted)' }}>Audit Notes: </span>
                <span style={{ color: '#fff' }}>{report.audit_notes || 'Not available in returned report'}</span>
              </div>
            </div>
          </div>

          {/* 3. Impact Assessment Summary */}
          <div
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.9rem',
              marginBottom: '1.5rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.4rem' }}>
              <Layers size={15} color="var(--color-brand)" />
              <strong style={{ fontSize: '0.84rem', color: '#fff' }}>
                Evaluated Impact Assessment
              </strong>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: 0 }}>
              {report.impact_summary || 'Not available in returned report'}
            </p>
          </div>

          {/* 4. Validation Summary */}
          <div
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.9rem',
              marginBottom: '1.5rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.4rem' }}>
              <CheckCircle size={15} color="var(--color-success)" />
              <strong style={{ fontSize: '0.84rem', color: '#fff' }}>
                Deterministic Regulatory Validation Summary
              </strong>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: 0 }}>
              {report.validation_summary || 'Not available in returned report'}
            </p>
          </div>

          {/* 5. Approved Change Specifications */}
          <div style={{ marginBottom: '1.5rem' }}>
            <h4
              style={{
                fontFamily: 'var(--font-heading)',
                fontSize: '0.95rem',
                color: '#fff',
                marginBottom: '0.8rem',
              }}
            >
              Approved Change Specifications ({report.changes?.length || 0})
            </h4>

            {report.changes && report.changes.length > 0 ? (
              report.changes.map((change, idx) => (
                <div
                  key={change.change_id || idx}
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '1rem',
                    marginBottom: '1rem',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '0.75rem',
                      flexWrap: 'wrap',
                      gap: '0.5rem',
                    }}
                  >
                    <div>
                      <strong style={{ color: '#fff', fontSize: '0.88rem' }}>
                        Section: {change.section || 'Not available in returned report'}
                      </strong>
                      <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
                        (Proposal ID: <code>{change.change_id}</code>)
                      </span>
                    </div>
                    <span className={`badge badge-${(change.decision_type || 'reuse').toLowerCase()}`}>
                      {change.decision_type || 'APPROVED'}
                    </span>
                  </div>

                  {/* Side-by-Side Original vs Approved Replacement */}
                  <div className="grid-2" style={{ gap: '0.75rem', marginBottom: '0.75rem' }}>
                    <div>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
                        Original / Current Text:
                      </span>
                      <div
                        style={{
                          background: 'var(--bg-main)',
                          padding: '0.6rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.76rem',
                          color: '#f87171',
                          lineHeight: 1.45,
                          borderLeft: '2px solid #ef4444',
                          maxHeight: '180px',
                          overflowY: 'auto',
                        }}
                      >
                        {change.original_text || 'Not available in returned report'}
                      </div>
                    </div>

                    <div>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
                        Approved Replacement Text:
                      </span>
                      <div
                        style={{
                          background: 'var(--bg-main)',
                          padding: '0.6rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.76rem',
                          color: '#34d399',
                          lineHeight: 1.45,
                          borderLeft: '2px solid #10b981',
                          maxHeight: '180px',
                          overflowY: 'auto',
                        }}
                      >
                        {change.proposed_text || 'Not available in returned report'}
                      </div>
                    </div>
                  </div>

                  {/* Reviewer Rationale */}
                  <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                    <strong style={{ color: 'var(--text-muted)' }}>Reviewer Rationale: </strong>
                    {change.rationale || 'Not available in returned report'}
                  </div>

                  {/* Change Validation Findings (if present in change) */}
                  {change.validation_findings && change.validation_findings.length > 0 && (
                    <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px dashed var(--border-subtle)' }}>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
                        Section Validation Findings:
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                        {change.validation_findings.map((f, fIdx) => (
                          <div
                            key={fIdx}
                            style={{
                              fontSize: '0.72rem',
                              color: f.passed ? 'var(--color-success)' : '#fca5a5',
                              display: 'flex',
                              gap: '0.4rem',
                            }}
                          >
                            <span>• [{f.rule_id || 'RULE'}]: {f.message}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Related Occurrences in Change (if present in change) */}
                  {change.related_occurrences && change.related_occurrences.length > 0 && (
                    <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px dashed var(--border-subtle)' }}>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
                        Identified Related Occurrences ({change.related_occurrences.length}):
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                        {change.related_occurrences.map((occ, oIdx) => (
                          <div
                            key={occ.occurrence_id || oIdx}
                            style={{
                              background: 'var(--bg-main)',
                              padding: '0.45rem 0.6rem',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.72rem',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#fff' }}>
                              <span>
                                <strong>{occ.section}</strong> {occ.location && `• ${occ.location}`}
                              </span>
                              <span className="badge badge-section" style={{ fontSize: '0.65rem' }}>
                                {occ.match_type}
                              </span>
                            </div>
                            <div style={{ color: 'var(--text-secondary)', marginTop: '0.2rem', fontFamily: 'monospace' }}>
                              {occ.current_text}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="empty-state" style={{ padding: '1.5rem' }}>
                <p>No changes listed in returned report.</p>
              </div>
            )}
          </div>

          {/* 6. Supporting Source Evidence Traceability */}
          <div style={{ marginBottom: '1.5rem' }}>
            <h4
              style={{
                fontFamily: 'var(--font-heading)',
                fontSize: '0.95rem',
                color: '#fff',
                marginBottom: '0.8rem',
              }}
            >
              External Regulatory Source Evidence Traceability ({report.source_evidence?.length || 0})
            </h4>

            {report.source_evidence && report.source_evidence.length > 0 ? (
              report.source_evidence.map((ev, idx) => (
                <div
                  key={ev.trace_id || idx}
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '0.85rem',
                    marginBottom: '0.6rem',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '0.35rem',
                      flexWrap: 'wrap',
                      gap: '0.4rem',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <FileText size={14} color="var(--color-brand)" />
                      <strong style={{ fontSize: '0.82rem', color: '#fff' }}>
                        {ev.source || 'Regulatory Source'}
                      </strong>
                      {ev.source_identifier && (
                        <code style={{ fontSize: '0.72rem' }}>{ev.source_identifier}</code>
                      )}
                    </div>

                    {ev.source_url && (
                      <a
                        href={ev.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          fontSize: '0.72rem',
                          color: 'var(--color-brand)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                        }}
                      >
                        Source Link <ExternalLink size={11} />
                      </a>
                    )}
                  </div>

                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.35rem' }}>
                    {ev.document_name && <span>Document: {ev.document_name}</span>}
                    {ev.section && <span>Section: {ev.section}</span>}
                    {ev.location && <span>Location: {ev.location}</span>}
                    {ev.loinc_code && <span>LOINC: <code>{ev.loinc_code}</code></span>}
                  </div>

                  {ev.exact_quote && (
                    <div
                      style={{
                        background: 'var(--bg-main)',
                        padding: '0.45rem 0.65rem',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.74rem',
                        color: 'var(--text-secondary)',
                        fontStyle: 'italic',
                      }}
                    >
                      "{ev.exact_quote}"
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div
                style={{
                  background: 'var(--bg-surface)',
                  padding: '0.75rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.78rem',
                  color: 'var(--text-muted)',
                  textAlign: 'center',
                }}
              >
                No external regulatory evidence traces cited in this report.
              </div>
            )}
          </div>

          {/* Footer Sign-off / Compliance Note */}
          <div
            style={{
              borderTop: '1px solid var(--border-subtle)',
              paddingTop: '1rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '0.74rem',
              color: 'var(--text-muted)',
              flexWrap: 'wrap',
              gap: '0.5rem',
            }}
          >
            <div>
              Generated at: {formatTimestamp(report.generated_at)}
            </div>
            <div>
              Internal Audit Trail • 21 CFR Part 11 Electronic Records Ready • Zero Autonomous Mutation
            </div>
          </div>
        </div>
      ) : (
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
