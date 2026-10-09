import React, { useState, useEffect } from 'react';
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
  Info,
  Clock,
  RefreshCw,
  GitPullRequest,
  CheckCircle2,
  XCircle,
  Edit3,
  Copy,
  ChevronDown,
  ChevronUp,
  ShieldAlert
} from 'lucide-react';
import { api } from '../services/api';

export default function ApprovedChangeReport({ approvedReport }) {
  const report = approvedReport || null;

  // View toggle: 'manifest' | 'audit_trail'
  // Derived state: defaults to 'manifest' if an authentic approvedReport was passed, otherwise 'audit_trail'
  const [selectedView, setSelectedView] = useState(null);
  const activeView = selectedView ?? (report ? 'manifest' : 'audit_trail');

  // Session Decision History state (populated via api.getHistory())
  const [decisionHistory, setDecisionHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);

  // Session Proposals state (populated via api.listProposals())
  const [proposals, setProposals] = useState([]);
  const [proposalsLoading, setProposalsLoading] = useState(false);
  const [proposalsError, setProposalsError] = useState(null);

  // Cryptographic Audit Trail state (populated via api.getAuditTrail())
  const [auditEvents, setAuditEvents] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState(null);

  // Verification state (populated via api.verifyAuditTrail())
  const [verificationResult, setVerificationResult] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [verificationError, setVerificationError] = useState(null);
  const [expandedEventId, setExpandedEventId] = useState(null);
  const [copiedHash, setCopiedHash] = useState(null);
  const [showAllSessionHistory, setShowAllSessionHistory] = useState(false);

  // ---------------------------------------------------------------------------
  // PART 1-4: Report-Specific Isolation & Filtering
  // ---------------------------------------------------------------------------
  // Authoritative decision IDs linked to the current approved report
  const reportDecisionIds = new Set([
    ...(report?.decision_ids || []),
    ...(report?.changes || []).map((c) => c.decision_id).filter(Boolean),
  ]);

  // Authoritative change IDs linked to the current approved report
  const reportChangeIds = new Set(
    (report?.changes || []).map((c) => c.change_id).filter(Boolean)
  );

  // Part 2: Filter audit events - display ONLY events matching current report
  const relevantAuditEvents = report
    ? auditEvents.filter(
        (e) =>
          (e.report_id && e.report_id === report.report_id) ||
          (e.change_id && reportChangeIds.has(e.change_id)) ||
          (e.decision_id && reportDecisionIds.has(e.decision_id))
      )
    : auditEvents;

  // Part 3: Filter decision history - display ONLY decisions associated with this report
  const relevantDecisions = report
    ? decisionHistory.filter((d) => reportDecisionIds.has(d.decision_id))
    : decisionHistory;

  // Part 4: Filter proposals - display ONLY proposals belonging to this report
  const relevantProposals = report
    ? proposals.filter(
        (p) =>
          (p.change_id && reportChangeIds.has(p.change_id)) ||
          (p.decision_id && reportDecisionIds.has(p.decision_id))
      )
    : proposals;

  // Active dataset for secondary history tab (isolated by default if report exists)
  const displayedAuditEvents = report && !showAllSessionHistory ? relevantAuditEvents : auditEvents;
  const displayedDecisions = report && !showAllSessionHistory ? relevantDecisions : decisionHistory;
  const displayedProposals = report && !showAllSessionHistory ? relevantProposals : proposals;

  // Load session audit data on mount
  useEffect(() => {
    loadSessionData();
  }, []);

  async function loadSessionData() {
    loadDecisionHistory();
    loadProposals();
    loadAuditTrail();
  }

  async function loadDecisionHistory() {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const data = await api.getHistory();
      setDecisionHistory(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load session decision history:', err);
      setHistoryError(err.message || 'Unable to retrieve session decision history.');
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadProposals() {
    setProposalsLoading(true);
    setProposalsError(null);
    try {
      const data = await api.listProposals();
      setProposals(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load session change proposals:', err);
      setProposalsError(err.message || 'Unable to retrieve change proposals.');
    } finally {
      setProposalsLoading(false);
    }
  }

  async function loadAuditTrail() {
    setAuditLoading(true);
    setAuditError(null);
    try {
      const data = await api.getAuditTrail();
      setAuditEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load audit trail:', err);
      setAuditError(err.message || 'Unable to retrieve cryptographic audit trail.');
    } finally {
      setAuditLoading(false);
    }
  }

  async function handleVerifyChain() {
    setVerifying(true);
    setVerificationError(null);
    try {
      const res = await api.verifyAuditTrail();
      setVerificationResult(res);
    } catch (err) {
      console.error('Audit verification request failed:', err);
      setVerificationError(err.message || 'Audit verification request failed.');
      setVerificationResult(null);
    } finally {
      setVerifying(false);
    }
  }

  function handleCopyHash(hash) {
    if (!hash) return;
    navigator.clipboard.writeText(hash).then(() => {
      setCopiedHash(hash);
      setTimeout(() => setCopiedHash(null), 2000);
    }).catch(() => {});
  }

  function formatEventType(type) {
    const map = {
      REVIEWER_DECISION_CREATED: 'Reviewer Decision Created',
      CHANGE_PROPOSAL_CREATED: 'Change Proposal Created',
      OCCURRENCES_CONFIRMED: 'Occurrences Confirmed',
      CHANGE_VALIDATED: 'Change Validated',
      CHANGE_APPROVED: 'Change Approved',
      CHANGE_REJECTED: 'Change Rejected',
      APPROVED_REPORT_CREATED: 'Approved Report Created',
      CORRECTED_DOCUMENT_GENERATED: 'Corrected Document Generated',
    };
    return map[type] || type;
  }

  // Part 8: Human-friendly business labels for Regulatory Affairs users
  function getBusinessEventLabel(type) {
    const map = {
      REVIEWER_DECISION_CREATED: 'Decision recorded',
      CHANGE_PROPOSAL_CREATED: 'Change proposal created',
      OCCURRENCES_CONFIRMED: 'Occurrences confirmed',
      CHANGE_VALIDATED: 'Change validated',
      CHANGE_APPROVED: 'Change approved',
      CHANGE_REJECTED: 'Change rejected',
      APPROVED_REPORT_CREATED: 'Approved report created',
      CORRECTED_DOCUMENT_GENERATED: 'Corrected document generated',
    };
    return map[type] || formatEventType(type);
  }

  function getBusinessEventDescription(evt) {
    const details = evt.details || {};
    switch (evt.event_type) {
      case 'REVIEWER_DECISION_CREATED':
        return details.decision
          ? `Reviewer recorded human determination: ${details.decision}${details.target_content_id ? ` for ${details.target_content_id}` : ''}`
          : 'Human reviewer evaluated candidate and recorded determination';
      case 'CHANGE_PROPOSAL_CREATED':
        return details.section
          ? `Controlled change proposal formulated for section "${details.section}"`
          : 'Controlled change proposal formulated based on human decision';
      case 'OCCURRENCES_CONFIRMED': {
        const confirmed = details.confirmed_count ?? (details.confirmed_occurrence_ids ? details.confirmed_occurrence_ids.length : 0);
        const excluded = details.excluded_count ?? (details.excluded_occurrence_ids ? details.excluded_occurrence_ids.length : 0);
        return `Related occurrences evaluated: ${confirmed} confirmed, ${excluded} excluded`;
      }
      case 'CHANGE_VALIDATED':
        return details.validation_passed === false
          ? 'Validation findings identified requiring regulatory review'
          : 'Deterministic regulatory consistency validation passed';
      case 'CHANGE_APPROVED':
        return `Explicit human approval authorized by ${evt.reviewer_name || 'Regulatory Approver'}`;
      case 'CHANGE_REJECTED':
        return `Proposal rejected by ${evt.reviewer_name || 'Regulatory Approver'}`;
      case 'APPROVED_REPORT_CREATED':
        return 'Approved change report compiled and sealed with complete source traceability';
      case 'CORRECTED_DOCUMENT_GENERATED':
        return details.output_filename
          ? `Corrected document "${details.output_filename}" generated from retained original source bytes${details.sha256_hash ? ` (SHA-256: ${truncateHash(details.sha256_hash, 8)})` : ''}`
          : 'Corrected document generated from retained original source bytes';
      default:
        return evt.new_status ? `Status transition: ${evt.new_status}` : 'Workflow transition recorded';
    }
  }

  function truncateHash(hash, length = 12) {
    if (!hash) return '000000000000...';
    if (hash.length <= length + 4) return hash;
    return `${hash.slice(0, length)}...`;
  }

  function handlePrint() {
    window.print();
  }

  function handleExportJson() {
    // Part 5: JSON Export Isolation - export strictly report-associated data when report exists
    const exportObject =
      report
        ? {
            ...report,
            relevant_decisions: relevantDecisions,
            relevant_proposals: relevantProposals,
            cryptographic_audit_trail: relevantAuditEvents,
            audit_verification: verificationResult,
            exported_at: new Date().toISOString(),
          }
        : {
            session_audit_trail: decisionHistory,
            session_proposals: proposals,
            cryptographic_audit_trail: auditEvents,
            audit_verification: verificationResult,
            exported_at: new Date().toISOString(),
          };

    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(exportObject, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    const fileName =
      report
        ? `approved_change_report_${report.report_id || 'manifest'}.json`
        : `session_decision_audit_trail_${new Date().toISOString().slice(0, 10)}.json`;
    downloadAnchor.setAttribute('download', fileName);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  }

  // PDF Download state & action
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState(null);

  async function handleDownloadPdf() {
    if (!report?.report_id || !report?.approval_confirmation) {
      return;
    }

    setPdfLoading(true);
    setPdfError(null);

    try {
      const { blob, filename } = await api.downloadApprovedChangeReportPdf(report.report_id);
      const url = window.URL.createObjectURL(blob);
      const downloadAnchor = document.createElement('a');
      downloadAnchor.href = url;
      downloadAnchor.download = filename || `Approved_Change_Report_${report.report_id}.pdf`;
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to download PDF report:', err);
      setPdfError(err.message || 'Failed to download approved change report PDF.');
    } finally {
      setPdfLoading(false);
    }
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

  // Session governance metrics (computed strictly from displayed data adhering to report isolation)
  const totalDecisions = displayedDecisions.length;
  const reuseCount = displayedDecisions.filter((d) => d.decision === 'REUSE').length;
  const adaptCount = displayedDecisions.filter((d) => d.decision === 'ADAPT').length;
  const rejectCount = displayedDecisions.filter((d) => d.decision === 'REJECT').length;
  // "Approved Proposals" counted ONLY from proposals whose actual status is 'APPROVED'
  const approvedProposals = displayedProposals.filter((p) => p.status === 'APPROVED');
  const approvedProposalsCount = approvedProposals.length;

  return (
    <div>
      {/* Top Header & Export Controls */}
      <div className="screen-header">
        <div>
          <h2>Approved Change Report & Audit Trail</h2>
          <p>Authorized Internal Regulatory Affairs Change Record with complete source citations and session decision history</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            type="button"
            onClick={loadSessionData}
            className="btn btn-secondary"
            style={{ fontSize: '0.82rem' }}
            disabled={historyLoading || proposalsLoading}
            title="Reload session audit trail and proposals from backend"
          >
            <RefreshCw size={13} className={historyLoading || proposalsLoading ? 'animate-spin' : ''} /> Refresh Session
          </button>
          <button
            type="button"
            onClick={handlePrint}
            className="btn btn-secondary"
            style={{ fontSize: '0.82rem' }}
            disabled={activeView === 'manifest' && !report && approvedProposals.length === 0}
          >
            <Printer size={14} /> Print Audit Manifest
          </button>
          <button
            type="button"
            onClick={handleExportJson}
            className="btn btn-secondary"
            style={{ fontSize: '0.82rem' }}
          >
            <Download size={14} /> Export JSON Manifest
          </button>
          <button
            type="button"
            onClick={handleDownloadPdf}
            className="btn btn-primary"
            style={{ fontSize: '0.82rem' }}
            disabled={!report || !report.report_id || !report.approval_confirmation || pdfLoading}
            title={
              !report || !report.report_id || !report.approval_confirmation
                ? 'PDF download is only available for an approved change report'
                : 'Download approved change report as PDF'
            }
          >
            {pdfLoading ? (
              <>
                <RefreshCw size={13} className="animate-spin" /> Generating PDF...
              </>
            ) : (
              <>
                <Download size={14} /> Download Approved PDF
              </>
            )}
          </button>

        </div>
      </div>

      {/* Internal View Toggle (Approved Change Manifest vs. Session Decision Audit Trail) */}
      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          maxWidth: '920px',
          margin: '0 auto 1.25rem auto',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '0.5rem',
        }}
      >
        <button
          type="button"
          onClick={() => setSelectedView('manifest')}
          className={`nav-tab ${activeView === 'manifest' ? 'active' : ''}`}
          style={{
            fontSize: '0.84rem',
            padding: '0.45rem 0.9rem',
            borderRadius: 'var(--radius-sm)',
            border: activeView === 'manifest' ? '1px solid var(--color-brand)' : '1px solid transparent',
            background: activeView === 'manifest' ? 'var(--color-brand)' : 'transparent',
            color: activeView === 'manifest' ? '#ffffff' : 'var(--text-secondary)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
          }}
        >
          <FileCheck2 size={14} />
          <span>Approved Change Report</span>
          {report && (
            <span className="badge" style={{ fontSize: '0.68rem', background: 'rgba(21, 128, 61, 0.15)', color: 'var(--color-success)' }}>
              Authorized
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setSelectedView('audit_trail')}
          className={`nav-tab ${activeView === 'audit_trail' ? 'active' : ''}`}
          style={{
            fontSize: '0.84rem',
            padding: '0.45rem 0.9rem',
            borderRadius: 'var(--radius-sm)',
            border: activeView === 'audit_trail' ? '1px solid var(--color-brand)' : '1px solid transparent',
            background: activeView === 'audit_trail' ? 'var(--color-brand)' : 'transparent',
            color: activeView === 'audit_trail' ? '#ffffff' : 'var(--text-secondary)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
          }}
        >
          <Clock size={14} />
          <span>{report ? 'Change History' : 'Session Decision Audit Trail'}</span>
          <span
            className="badge"
            style={{
              fontSize: '0.68rem',
              background: 'var(--bg-surface-elevated)',
              color: 'var(--text-primary)',
            }}
          >
            {displayedAuditEvents.length}
          </span>
        </button>
      </div>

      {/* PDF Download Error Banner */}
      {pdfError && (
        <div
          style={{
            maxWidth: '920px',
            margin: '0 auto 1rem auto',
            padding: '0.75rem 1rem',
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-sm)',
            color: '#fca5a5',
            fontSize: '0.8rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <AlertCircle size={16} color="var(--color-danger)" />
          <span>{pdfError}</span>
        </div>
      )}

{/* ========================================================================= */}
      {/* VIEW 1: APPROVED CHANGE MANIFEST (Step 6.7 Authentic Report & Proposals) */}
      {/* ========================================================================= */}
      {activeView === 'manifest' && (
        <div>
          {proposalsError && (
            <div
              style={{
                maxWidth: '920px',
                margin: '0 auto 1rem auto',
                padding: '0.75rem 1rem',
                background: 'rgba(239, 68, 68, 0.12)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                borderRadius: 'var(--radius-sm)',
                color: '#fca5a5',
                fontSize: '0.8rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              <AlertCircle size={16} color="var(--color-danger)" />
              <span>{proposalsError}</span>
            </div>
          )}
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

              {/* 7. Business Change History (Part 7, 8, 11) */}
              <div style={{ marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.8rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Clock size={16} color="var(--color-brand)" />
                    <h4
                      style={{
                        fontFamily: 'var(--font-heading)',
                        fontSize: '0.95rem',
                        color: '#fff',
                        margin: 0,
                      }}
                    >
                      Change History ({relevantAuditEvents.length})
                    </h4>
                  </div>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    Chronological regulatory actions for this approved change
                  </span>
                </div>

                {relevantAuditEvents.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                    {relevantAuditEvents.map((evt, idx) => (
                      <div
                        key={evt.event_id || idx}
                        style={{
                          background: 'var(--bg-surface)',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '0.85rem 1rem',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <CheckCircle2 size={15} color="var(--color-brand)" />
                            <strong style={{ fontSize: '0.84rem', color: '#fff' }}>
                              {getBusinessEventLabel(evt.event_type)}
                            </strong>
                            {evt.new_status && (
                              <span className="badge" style={{ fontSize: '0.68rem', background: 'rgba(13, 148, 136, 0.15)', color: 'var(--color-brand)' }}>
                                {evt.new_status}
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <Clock size={12} />
                            <span>{formatTimestamp(evt.occurred_at)}</span>
                          </div>
                        </div>

                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                          {getBusinessEventDescription(evt)}
                        </div>

                        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          <span>Reviewer: <strong style={{ color: '#cbd5e1' }}>{evt.reviewer_name || 'Regulatory User'}</strong></span>
                          {evt.change_id && <span>Change ID: <code style={{ fontSize: '0.7rem' }}>{evt.change_id}</code></span>}
                          {evt.decision_id && <span>Decision ID: <code style={{ fontSize: '0.7rem' }}>{evt.decision_id}</code></span>}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ background: 'var(--bg-surface)', padding: '0.85rem', borderRadius: 'var(--radius-sm)', fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                    No audit history events associated with this approved change report.
                  </div>
                )}
              </div>

              {/* 8. Cryptographic Audit Verification (Part 9, 10, 11 - Secondary Expandable Section) */}
              <div style={{ marginBottom: '1.5rem' }}>
                <details
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '0.85rem 1rem',
                  }}
                >
                  <summary
                    style={{
                      cursor: 'pointer',
                      fontWeight: '600',
                      fontSize: '0.88rem',
                      color: '#fff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      userSelect: 'none',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <ShieldCheck size={16} color="var(--color-brand)" />
                      <span>Cryptographic Audit Verification</span>
                    </div>
                    <span
                      className="badge"
                      style={{
                        fontSize: '0.68rem',
                        background: 'rgba(59, 130, 246, 0.12)',
                        color: '#93c5fd',
                      }}
                    >
                      SHA-256 Tamper Evident Details ▾
                    </span>
                  </summary>

                  <div style={{ marginTop: '0.85rem', paddingTop: '0.85rem', borderTop: '1px solid var(--border-subtle)' }}>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: '0.75rem',
                        marginBottom: '1rem',
                      }}
                    >
                      <div>
                        <p style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', margin: 0 }}>
                          Tamper-evident SHA-256 back-linked hash chain covering all human decisions, proposals, validations, and approvals for this report.
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={handleVerifyChain}
                        disabled={verifying}
                        className="btn btn-primary"
                        style={{ fontSize: '0.8rem', padding: '0.4rem 0.85rem' }}
                        title="Execute SHA-256 back-link and canonical payload verification"
                      >
                        {verifying ? (
                          <>
                            <RefreshCw size={13} className="animate-spin" /> Verifying Chain...
                          </>
                        ) : (
                          <>
                            <ShieldCheck size={14} /> Verify Audit Chain
                          </>
                        )}
                      </button>
                    </div>

                    {/* Verification Result Display */}
                    {verifying && (
                      <div
                        style={{
                          padding: '0.75rem 1rem',
                          background: 'rgba(59, 130, 246, 0.1)',
                          border: '1px solid rgba(59, 130, 246, 0.3)',
                          borderRadius: 'var(--radius-sm)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.6rem',
                          fontSize: '0.78rem',
                          color: '#93c5fd',
                          marginBottom: '1rem',
                        }}
                      >
                        <RefreshCw size={16} className="animate-spin" />
                        <span>Executing cryptographic verification across audit records...</span>
                      </div>
                    )}

                    {!verifying && verificationResult && verificationResult.valid === true && (
                      <div
                        style={{
                          padding: '0.85rem 1rem',
                          background: 'rgba(21, 128, 61, 0.08)',
                          border: '1px solid rgba(21, 128, 61, 0.25)',
                          borderRadius: 'var(--radius-sm)',
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '0.65rem',
                          marginBottom: '1rem',
                        }}
                      >
                        <CheckCircle2 size={18} color="var(--color-success)" style={{ flexShrink: 0, marginTop: '2px' }} />
                        <div>
                          <div style={{ fontWeight: '600', color: 'var(--color-success)', fontSize: '0.84rem' }}>
                            ✓ Audit chain verified
                          </div>
                          <div style={{ fontSize: '0.76rem', color: '#166534', marginTop: '0.2rem' }}>
                            The recorded audit history passed SHA-256 integrity verification. All <strong>{verificationResult.checked_event_count}</strong> audit events were verified. Every canonical payload matches its stored hash, and all sequential back-links are intact.
                          </div>
                        </div>
                      </div>
                    )}

                    {!verifying && verificationResult && verificationResult.valid === false && (
                      <div
                        style={{
                          padding: '0.85rem 1rem',
                          background: 'rgba(185, 28, 28, 0.08)',
                          border: '1px solid rgba(185, 28, 28, 0.25)',
                          borderRadius: 'var(--radius-sm)',
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '0.65rem',
                          marginBottom: '1rem',
                        }}
                      >
                        <ShieldAlert size={18} color="var(--color-danger)" style={{ flexShrink: 0, marginTop: '2px' }} />
                        <div>
                          <div style={{ fontWeight: '600', color: 'var(--color-danger)', fontSize: '0.84rem' }}>
                            Audit Chain Verification Discrepancy Detected
                          </div>
                          <div style={{ fontSize: '0.76rem', color: '#991b1b', marginTop: '0.2rem' }}>
                            Checked {verificationResult.checked_event_count} events before encountering discrepancy.
                            {verificationResult.first_invalid_event_id && (
                              <span style={{ display: 'block', marginTop: '0.2rem' }}>
                                First invalid event ID: <code>{verificationResult.first_invalid_event_id}</code>
                              </span>
                            )}
                            {verificationResult.reason && (
                              <span style={{ display: 'block', marginTop: '0.2rem' }}>
                                Diagnostic reason: {verificationResult.reason}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {!verifying && verificationError && (
                      <div
                        style={{
                          padding: '0.75rem 1rem',
                          background: 'rgba(185, 28, 28, 0.08)',
                          border: '1px solid rgba(185, 28, 28, 0.25)',
                          borderRadius: 'var(--radius-sm)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.6rem',
                          fontSize: '0.8rem',
                          color: '#991b1b',
                          marginBottom: '1rem',
                        }}
                      >
                        <AlertCircle size={16} color="var(--color-danger)" />
                        <span>Verification Request Error: {verificationError}</span>
                      </div>
                    )}

                    {!verifying && !verificationResult && !verificationError && (
                      <div
                        style={{
                          padding: '0.75rem 1rem',
                          background: 'rgba(100, 116, 139, 0.08)',
                          border: '1px solid rgba(100, 116, 139, 0.2)',
                          borderRadius: 'var(--radius-sm)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.6rem',
                          fontSize: '0.78rem',
                          color: 'var(--text-secondary)',
                          marginBottom: '1rem',
                        }}
                      >
                        <Shield size={16} color="var(--text-muted)" />
                        <span>
                          <strong>Chain Status:</strong> Click <strong>Verify Audit Chain</strong> to mathematically validate SHA-256 back-links against stored canonical payloads.
                        </span>
                      </div>
                    )}

                    {/* Technical Ledger for this report */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                      {relevantAuditEvents.map((evt, idx) => {
                        const isExpanded = expandedEventId === `report_${evt.event_id}`;
                        const prevHashDisplay = evt.previous_event_hash
                          ? truncateHash(evt.previous_event_hash, 12)
                          : '[Genesis Event - No Predecessor]';
                        const eventHashDisplay = truncateHash(evt.event_hash, 12);
                        const isCopied = copiedHash === evt.event_hash;

                        return (
                          <div
                            key={evt.event_id || idx}
                            style={{
                              background: 'var(--bg-main)',
                              border: '1px solid var(--border-subtle)',
                              borderRadius: 'var(--radius-sm)',
                              padding: '0.75rem 0.9rem',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                <code style={{ fontSize: '0.68rem', color: 'var(--color-brand)' }}>{evt.event_id}</code>
                                <code style={{ fontSize: '0.68rem', background: '#edf0f5', padding: '0.1rem 0.35rem', borderRadius: '3px', color: 'var(--text-secondary)' }}>
                                  {evt.event_type}
                                </code>
                              </div>
                              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{formatTimestamp(evt.occurred_at)}</span>
                            </div>

                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.4rem', fontSize: '0.72rem' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', flexWrap: 'wrap' }}>
                                <div>
                                  <span style={{ color: 'var(--text-muted)' }}>SHA-256: </span>
                                  <code style={{ color: 'var(--color-brand)', fontWeight: '600' }}>{eventHashDisplay}</code>
                                  <button
                                    type="button"
                                    onClick={() => handleCopyHash(evt.event_hash)}
                                    style={{ background: 'transparent', border: 'none', color: isCopied ? 'var(--color-success)' : 'var(--text-muted)', cursor: 'pointer', padding: '0 0.25rem' }}
                                    title="Copy full 64-character SHA-256 hash"
                                  >
                                    <Copy size={11} />
                                  </button>
                                  {isCopied && <span style={{ fontSize: '0.65rem', color: 'var(--color-success)' }}>Copied!</span>}
                                </div>
                                <div>
                                  <span style={{ color: 'var(--text-muted)' }}>Prev Link: </span>
                                  <code style={{ color: evt.previous_event_hash ? 'var(--text-secondary)' : 'var(--color-success)' }}>{prevHashDisplay}</code>
                                </div>
                              </div>

                              <button
                                type="button"
                                onClick={() => setExpandedEventId(isExpanded ? null : `report_${evt.event_id}`)}
                                className="btn btn-secondary"
                                style={{ fontSize: '0.68rem', padding: '0.15rem 0.45rem' }}
                              >
                                {isExpanded ? <><ChevronUp size={11} /> Hide Payload</> : <><ChevronDown size={11} /> Inspect Payload</>}
                              </button>
                            </div>

                            {isExpanded && (
                              <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: '#ffffff', borderRadius: '3px', border: '1px solid var(--border-subtle)', fontSize: '0.68rem' }}>
                                <div style={{ marginBottom: '0.3rem', wordBreak: 'break-all' }}>
                                  <strong>Full SHA-256 Digest: </strong><code>{evt.event_hash}</code>
                                </div>
                                {evt.previous_event_hash && (
                                  <div style={{ marginBottom: '0.3rem', wordBreak: 'break-all' }}>
                                    <strong>Previous Hash: </strong><code>{evt.previous_event_hash}</code>
                                  </div>
                                )}
                                {evt.details && (
                                  <div>
                                    <strong>Canonical Event Details:</strong>
                                    <pre style={{ margin: '0.2rem 0 0 0', padding: '0.4rem', background: '#f8fafc', borderRadius: '3px', overflowX: 'auto', fontSize: '0.65rem' }}>
                                      {JSON.stringify(evt.details, null, 2)}
                                    </pre>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </details>
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
          ) : approvedProposals.length > 0 ? (
            /* Fallback when report prop is null after refresh but approved proposals exist in session */
            <div
              className="card"
              style={{
                maxWidth: '920px',
                margin: '0 auto',
                background: '#0b101c',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div
                style={{
                  padding: '0.75rem 1rem',
                  background: 'rgba(16, 185, 129, 0.1)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  borderRadius: 'var(--radius-sm)',
                  marginBottom: '1.25rem',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '0.5rem',
                  fontSize: '0.78rem',
                  color: '#6ee7b7',
                }}
              >
                <CheckCircle2 size={16} color="var(--color-success)" style={{ flexShrink: 0, marginTop: '2px' }} />
                <div>
                  <strong>Session Approved Proposals ({approvedProposals.length}):</strong> The following change proposals were explicitly authorized and approved during the current session. Full report compilation artifact is generated upon approval; individual approved proposals remain retrievable across the active session.
                </div>
              </div>

              <div style={{ marginBottom: '1.5rem' }}>
                <h4 style={{ fontFamily: 'var(--font-heading)', fontSize: '1rem', color: '#fff', marginBottom: '0.8rem' }}>
                  Approved Proposals ({approvedProposals.length})
                </h4>

                {approvedProposals.map((p, idx) => (
                  <div
                    key={p.change_id || idx}
                    style={{
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '1rem',
                      marginBottom: '1rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                      <div>
                        <strong style={{ color: '#fff', fontSize: '0.88rem' }}>Section: {p.section}</strong>
                        <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
                          (Proposal ID: <code>{p.change_id}</code> • Linked Decision: <code>{p.decision_id}</code>)
                        </span>
                      </div>
                      <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.2)', color: 'var(--color-success)', fontSize: '0.72rem' }}>
                        {p.status}
                      </span>
                    </div>

                    <div className="grid-2" style={{ gap: '0.75rem', marginBottom: '0.6rem' }}>
                      <div>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
                          Original Text:
                        </span>
                        <div style={{ background: 'var(--bg-main)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem', color: '#f87171' }}>
                          {p.original_text}
                        </div>
                      </div>
                      <div>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
                          Approved Replacement Text:
                        </span>
                        <div style={{ background: 'var(--bg-main)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem', color: '#34d399' }}>
                          {p.proposed_text}
                        </div>
                      </div>
                    </div>

                    <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                      <strong>Audit Rationale:</strong> {p.rationale}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="card" style={{ maxWidth: '800px', margin: '0 auto' }}>
              <div className="empty-state">
                <FileCheck2 size={36} />
                <p>No Approved Change Report has been authorized yet in this session.</p>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
                  Navigate to <strong>Change Review</strong>, review the impact analysis and validation findings, and authorize changes using the <strong>Human Regulatory Approval Gate</strong>.
                </p>
                <button
                  type="button"
                  onClick={() => setSelectedView('audit_trail')}
                  className="btn btn-secondary"
                  style={{ marginTop: '1rem', fontSize: '0.8rem' }}
                >
                  <Clock size={13} /> View Session Decision Audit Trail
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* VIEW 2: CHANGE HISTORY & AUDIT TRAIL                                      */}
      {/* ========================================================================= */}
      {activeView === 'audit_trail' && (
        <div style={{ maxWidth: '920px', margin: '0 auto' }}>
          {/* Report Isolation Status Banner (when viewing with an active approved report) */}
          {report && (
            <div
              style={{
                padding: '0.75rem 1rem',
                background: showAllSessionHistory ? 'rgba(245, 158, 11, 0.08)' : 'rgba(13, 148, 136, 0.08)',
                border: showAllSessionHistory ? '1px solid rgba(245, 158, 11, 0.25)' : '1px solid rgba(13, 148, 136, 0.25)',
                borderRadius: 'var(--radius-sm)',
                marginBottom: '1.25rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.6rem',
                fontSize: '0.78rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <ShieldCheck size={16} color="var(--color-brand)" />
                <span>
                  {showAllSessionHistory ? (
                    <span>
                      <strong>Global Session History:</strong> Viewing all activity across session documents.
                    </span>
                  ) : (
                    <span>
                      <strong>Report Isolation Active:</strong> Showing change history strictly associated with Report <code>{report.report_id}</code> ({displayedAuditEvents.length} events, {displayedDecisions.length} decisions, {displayedProposals.length} proposals).
                    </span>
                  )}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowAllSessionHistory(!showAllSessionHistory)}
                className="btn btn-secondary"
                style={{ fontSize: '0.72rem', padding: '0.25rem 0.65rem' }}
              >
                {showAllSessionHistory ? 'Isolate to This Report' : 'Show All Session Documents'}
              </button>
            </div>
          )}

          {/* 1. Governance Summary Cards */}
          <div
            className="grid-3"
            style={{
              marginBottom: '1.25rem',
              gap: '0.75rem',
            }}
          >
            <div
              className="card"
              style={{
                padding: '0.85rem 1rem',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                Total Recorded Decisions
              </span>
              <div style={{ fontSize: '1.5rem', fontWeight: '700', color: '#fff' }}>
                {historyLoading ? '...' : totalDecisions}
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                {report && !showAllSessionHistory ? 'Decisions for this report' : 'Authoritative human reviewer choices'}
              </span>
            </div>

            <div
              className="card"
              style={{
                padding: '0.85rem 1rem',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                Decision Breakdown
              </span>
              <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', marginTop: '0.2rem' }}>
                <span className="badge badge-reuse" style={{ fontSize: '0.74rem' }}>
                  REUSE: {reuseCount}
                </span>
                <span className="badge badge-adapt" style={{ fontSize: '0.74rem' }}>
                  ADAPT: {adaptCount}
                </span>
                <span className="badge badge-reject" style={{ fontSize: '0.74rem' }}>
                  REJECT: {rejectCount}
                </span>
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.35rem', display: 'block' }}>
                Human determinations across candidates
              </span>
            </div>

            <div
              className="card"
              style={{
                padding: '0.85rem 1rem',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.2rem' }}>
                Approved Proposals
              </span>
              <div style={{ fontSize: '1.5rem', fontWeight: '700', color: 'var(--color-success)' }}>
                {proposalsLoading ? '...' : approvedProposalsCount}
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                Proposals with status: <code>APPROVED</code>
              </span>
            </div>
          </div>

          {/* 2. PRIMARY VIEW: BUSINESS-FACING CHANGE HISTORY (Timeline) */}
          <div style={{ marginBottom: '1.5rem' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '0.85rem',
                flexWrap: 'wrap',
                gap: '0.5rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Clock size={16} color="var(--color-brand)" />
                <h4 style={{ fontSize: '0.95rem', fontWeight: '600', margin: 0, color: '#fff' }}>
                  Change History ({displayedAuditEvents.length})
                </h4>
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                {report && !showAllSessionHistory ? 'Chronological regulatory actions for this approved change' : 'All session workflow activity'}
              </span>
            </div>

            {auditLoading && (
              <div className="card" style={{ textAlign: 'center', padding: '1.5rem' }}>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                  Loading change history...
                </div>
              </div>
            )}

            {auditError && (
              <div
                style={{
                  padding: '0.75rem 1rem',
                  background: 'rgba(239, 68, 68, 0.12)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: 'var(--radius-sm)',
                  color: '#fca5a5',
                  fontSize: '0.8rem',
                  marginBottom: '1rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <AlertCircle size={16} color="var(--color-danger)" />
                <span>{auditError}</span>
              </div>
            )}

            {!auditLoading && !auditError && displayedAuditEvents.length === 0 && (
              <div className="card" style={{ padding: '1.5rem', textAlign: 'center' }}>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
                  No change history events recorded yet. Complete document reviews, candidate comparisons, or change authorizations to generate audit records.
                </p>
              </div>
            )}

            {!auditLoading && displayedAuditEvents.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                {displayedAuditEvents.map((evt, idx) => (
                  <div
                    key={evt.event_id || idx}
                    style={{
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '0.85rem 1rem',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '0.35rem',
                        flexWrap: 'wrap',
                        gap: '0.5rem',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <CheckCircle2 size={15} color="var(--color-brand)" />
                        <strong style={{ fontSize: '0.84rem', color: '#fff' }}>
                          {getBusinessEventLabel(evt.event_type)}
                        </strong>
                        {evt.new_status && (
                          <span className="badge" style={{ fontSize: '0.68rem', background: 'rgba(13, 148, 136, 0.15)', color: 'var(--color-brand)' }}>
                            {evt.new_status}
                          </span>
                        )}
                      </div>

                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <Clock size={12} />
                        <span>{formatTimestamp(evt.occurred_at)}</span>
                      </div>
                    </div>

                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                      {getBusinessEventDescription(evt)}
                    </div>

                    <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      <span>Reviewer: <strong style={{ color: '#cbd5e1' }}>{evt.reviewer_name || 'Regulatory User'}</strong></span>
                      {evt.change_id && <span>Change ID: <code style={{ fontSize: '0.7rem' }}>{evt.change_id}</code></span>}
                      {evt.decision_id && <span>Decision ID: <code style={{ fontSize: '0.7rem' }}>{evt.decision_id}</code></span>}
                      {evt.report_id && <span>Report ID: <code style={{ fontSize: '0.7rem' }}>{evt.report_id}</code></span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 3. HUMAN REGULATORY DECISIONS (Filtered) */}
          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.85rem' }}>
              <CheckCircle size={16} color="var(--color-brand)" />
              <h4 style={{ fontSize: '0.92rem', fontWeight: '600', margin: 0, color: '#fff' }}>
                Human Regulatory Decisions ({displayedDecisions.length} recorded)
              </h4>
            </div>

            {historyLoading && (
              <div className="card" style={{ textAlign: 'center', padding: '1.5rem' }}>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                  Loading reviewer decisions...
                </div>
              </div>
            )}

            {historyError && (
              <div
                style={{
                  padding: '0.75rem 1rem',
                  background: 'rgba(239, 68, 68, 0.12)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: 'var(--radius-sm)',
                  color: '#fca5a5',
                  fontSize: '0.8rem',
                  marginBottom: '1rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <AlertCircle size={16} color="var(--color-danger)" />
                <span>{historyError}</span>
              </div>
            )}

            {!historyLoading && !historyError && displayedDecisions.length === 0 && (
              <div className="card">
                <div className="empty-state">
                  <Clock size={36} />
                  <p>No regulatory decisions associated with this report.</p>
                </div>
              </div>
            )}

            {!historyLoading && displayedDecisions.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                {displayedDecisions.map((d, idx) => {
                  const isReuse = d.decision === 'REUSE';
                  const isAdapt = d.decision === 'ADAPT';
                  const isReject = d.decision === 'REJECT';

                  return (
                    <div
                      key={d.decision_id || idx}
                      style={{
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '1rem',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginBottom: '0.65rem',
                          flexWrap: 'wrap',
                          gap: '0.5rem',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span
                            className={`badge badge-${d.decision.toLowerCase()}`}
                            style={{
                              fontSize: '0.74rem',
                              padding: '0.25rem 0.6rem',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.35rem',
                            }}
                          >
                            {isReuse && <CheckCircle2 size={12} />}
                            {isAdapt && <Edit3 size={12} />}
                            {isReject && <XCircle size={12} />}
                            {d.decision}
                          </span>

                          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                            Decision ID: <code>{d.decision_id || 'Not available'}</code>
                          </span>
                        </div>

                        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                          <Clock size={12} />
                          <span>Decided: {formatTimestamp(d.decided_at)}</span>
                        </div>
                      </div>

                      <div
                        className="grid-3"
                        style={{
                          background: 'var(--bg-main)',
                          padding: '0.65rem 0.85rem',
                          borderRadius: 'var(--radius-sm)',
                          marginBottom: '0.75rem',
                          gap: '0.5rem',
                          fontSize: '0.75rem',
                        }}
                      >
                        <div>
                          <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.68rem', textTransform: 'uppercase' }}>
                            Reviewer Attribution
                          </span>
                          <strong style={{ color: '#fff' }}>{d.reviewer_name || 'Not available in returned data'}</strong>
                        </div>

                        <div>
                          <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.68rem', textTransform: 'uppercase' }}>
                            Target Content ID
                          </span>
                          <code>{d.target_content_id || 'Not available'}</code>
                        </div>

                        <div>
                          <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.68rem', textTransform: 'uppercase' }}>
                            Candidate ID
                          </span>
                          <code>{d.candidate_id || 'None / Not specified'}</code>
                        </div>
                      </div>

                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: isAdapt && d.adaptation_instructions ? '0.5rem' : '0' }}>
                        <strong style={{ color: 'var(--text-muted)' }}>Reviewer Notes / Clinical Justification: </strong>
                        <span style={{ color: '#e2e8f0' }}>{d.reviewer_notes || 'No notes recorded'}</span>
                      </div>

                      {isAdapt && d.adaptation_instructions && (
                        <div
                          style={{
                            marginTop: '0.5rem',
                            padding: '0.5rem 0.75rem',
                            background: 'rgba(147, 51, 234, 0.08)',
                            borderLeft: '2px solid #a855f7',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.75rem',
                          }}
                        >
                          <strong style={{ color: '#c084fc', display: 'block', marginBottom: '0.2rem' }}>
                            Human Adaptation Instructions:
                          </strong>
                          <span style={{ color: '#e2e8f0' }}>{d.adaptation_instructions}</span>
                        </div>
                      )}

                      {isReject && (
                        <div
                          style={{
                            marginTop: '0.5rem',
                            padding: '0.5rem 0.75rem',
                            background: 'rgba(239, 68, 68, 0.08)',
                            borderLeft: '2px solid #ef4444',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.73rem',
                            color: '#fca5a5',
                          }}
                        >
                          <strong>Rejection Safeguard:</strong> This candidate was declined by the human reviewer. Downstream change proposal formulation was blocked, no changes were compiled, and original draft content remains strictly preserved.
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 4. PROPOSALS LIFECYCLE (Filtered) */}
          {displayedProposals.length > 0 && (
            <div style={{ marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.75rem' }}>
                <GitPullRequest size={16} color="var(--color-brand)" />
                <h4 style={{ fontFamily: 'var(--font-heading)', fontSize: '0.95rem', color: '#fff', margin: 0 }}>
                  Change Proposals Lifecycle ({displayedProposals.length})
                </h4>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {displayedProposals.map((p, idx) => (
                  <div
                    key={p.change_id || idx}
                    style={{
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '0.75rem 1rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '0.5rem',
                      fontSize: '0.76rem',
                    }}
                  >
                    <div>
                      <strong style={{ color: '#fff' }}>Section: {p.section}</strong>
                      <span style={{ color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
                        Proposal ID: <code>{p.change_id}</code>
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span className={`badge badge-${(p.decision_type || 'reuse').toLowerCase()}`} style={{ fontSize: '0.68rem' }}>
                        {p.decision_type}
                      </span>
                      <span
                        className="badge"
                        style={{
                          fontSize: '0.68rem',
                          background:
                            p.status === 'APPROVED'
                              ? 'rgba(16, 185, 129, 0.2)'
                              : p.status === 'REJECTED'
                              ? 'rgba(239, 68, 68, 0.2)'
                              : 'rgba(245, 158, 11, 0.15)',
                          color:
                            p.status === 'APPROVED'
                              ? 'var(--color-success)'
                              : p.status === 'REJECTED'
                              ? 'var(--color-danger)'
                              : 'var(--color-warning)',
                        }}
                      >
                        STATUS: {p.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 5. SECONDARY EXPANDABLE: CRYPTOGRAPHIC AUDIT VERIFICATION */}
          <div style={{ marginBottom: '2rem' }}>
            <details
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '1rem',
              }}
            >
              <summary
                style={{
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '0.92rem',
                  color: '#fff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  userSelect: 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <ShieldCheck size={18} color="var(--color-brand)" />
                  <span>Cryptographic Audit Verification</span>
                </div>
                <span
                  className="badge"
                  style={{
                    fontSize: '0.7rem',
                    background: 'rgba(59, 130, 246, 0.12)',
                    color: '#93c5fd',
                  }}
                >
                  SHA-256 Tamper Evident Details ▾
                </span>
              </summary>

              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
                {/* Verification Control & Action */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: '0.75rem',
                    marginBottom: '1rem',
                  }}
                >
                  <div>
                    <p style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', margin: 0 }}>
                      Tamper-evident SHA-256 back-linked hash chain covering all human decisions, proposals, validations, and authorizations.
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={handleVerifyChain}
                    disabled={verifying}
                    className="btn btn-primary"
                    style={{ fontSize: '0.82rem', padding: '0.45rem 0.9rem' }}
                    title="Execute SHA-256 back-link and canonical payload verification via GET /audit/verify"
                  >
                    {verifying ? (
                      <>
                        <RefreshCw size={13} className="animate-spin" /> Verifying Chain...
                      </>
                    ) : (
                      <>
                        <ShieldCheck size={14} /> Verify Audit Chain
                      </>
                    )}
                  </button>
                </div>

                {/* Verification Status Display */}
                {verifying && (
                  <div
                    style={{
                      padding: '0.75rem 1rem',
                      background: 'rgba(59, 130, 246, 0.1)',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      borderRadius: 'var(--radius-sm)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.6rem',
                      fontSize: '0.8rem',
                      color: '#93c5fd',
                      marginBottom: '1rem',
                    }}
                  >
                    <RefreshCw size={16} className="animate-spin" />
                    <span>Executing cryptographic verification across all audit records...</span>
                  </div>
                )}

                {!verifying && verificationResult && verificationResult.valid === true && (
                  <div
                    style={{
                      padding: '0.85rem 1rem',
                      background: 'rgba(21, 128, 61, 0.08)',
                      border: '1px solid rgba(21, 128, 61, 0.25)',
                      borderRadius: 'var(--radius-sm)',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '0.65rem',
                      marginBottom: '1rem',
                    }}
                  >
                    <CheckCircle2 size={18} color="var(--color-success)" style={{ flexShrink: 0, marginTop: '2px' }} />
                    <div>
                      <div style={{ fontWeight: '600', color: 'var(--color-success)', fontSize: '0.84rem' }}>
                        ✓ Audit chain verified
                      </div>
                      <div style={{ fontSize: '0.76rem', color: '#166534', marginTop: '0.2rem' }}>
                        The recorded audit history passed SHA-256 integrity verification. All <strong>{verificationResult.checked_event_count}</strong> audit events were verified. Every canonical payload matches its stored hash, and all sequential back-links are intact. Zero tampering detected.
                      </div>
                    </div>
                  </div>
                )}

                {!verifying && verificationResult && verificationResult.valid === false && (
                  <div
                    style={{
                      padding: '0.85rem 1rem',
                      background: 'rgba(185, 28, 28, 0.08)',
                      border: '1px solid rgba(185, 28, 28, 0.25)',
                      borderRadius: 'var(--radius-sm)',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '0.65rem',
                      marginBottom: '1rem',
                    }}
                  >
                    <ShieldAlert size={18} color="var(--color-danger)" style={{ flexShrink: 0, marginTop: '2px' }} />
                    <div>
                      <div style={{ fontWeight: '600', color: 'var(--color-danger)', fontSize: '0.84rem' }}>
                        Audit Chain Verification Discrepancy Detected
                      </div>
                      <div style={{ fontSize: '0.76rem', color: '#991b1b', marginTop: '0.2rem' }}>
                        Checked {verificationResult.checked_event_count} events before encountering discrepancy.
                        {verificationResult.first_invalid_event_id && (
                          <span style={{ display: 'block', marginTop: '0.2rem' }}>
                            First invalid event ID: <code>{verificationResult.first_invalid_event_id}</code>
                          </span>
                        )}
                        {verificationResult.reason && (
                          <span style={{ display: 'block', marginTop: '0.2rem' }}>
                            Diagnostic reason: {verificationResult.reason}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {!verifying && verificationError && (
                  <div
                    style={{
                      padding: '0.75rem 1rem',
                      background: 'rgba(185, 28, 28, 0.08)',
                      border: '1px solid rgba(185, 28, 28, 0.25)',
                      borderRadius: 'var(--radius-sm)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.6rem',
                      fontSize: '0.8rem',
                      color: '#991b1b',
                      marginBottom: '1rem',
                    }}
                  >
                    <AlertCircle size={16} color="var(--color-danger)" />
                    <span>Verification Request Error: {verificationError}</span>
                  </div>
                )}

                {!verifying && !verificationResult && !verificationError && (
                  <div
                    style={{
                      padding: '0.75rem 1rem',
                      background: 'rgba(100, 116, 139, 0.08)',
                      border: '1px solid rgba(100, 116, 139, 0.2)',
                      borderRadius: 'var(--radius-sm)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.6rem',
                      fontSize: '0.78rem',
                      color: 'var(--text-secondary)',
                      marginBottom: '1rem',
                    }}
                  >
                    <Shield size={16} color="var(--text-muted)" />
                    <span>
                      <strong>Chain Status:</strong> Click <strong>Verify Audit Chain</strong> to mathematically validate all SHA-256 back-links against stored canonical payloads.
                    </span>
                  </div>
                )}

                {/* Technical Audit Event Ledger */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {displayedAuditEvents.map((evt, idx) => {
                    const isExpanded = expandedEventId === `session_${evt.event_id}`;
                    const prevHashDisplay = evt.previous_event_hash
                      ? truncateHash(evt.previous_event_hash, 12)
                      : '[Genesis Event - No Predecessor]';
                    const eventHashDisplay = truncateHash(evt.event_hash, 12);
                    const isCopied = copiedHash === evt.event_hash;

                    return (
                      <div
                        key={evt.event_id || idx}
                        style={{
                          background: 'var(--bg-main)',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '0.85rem 1rem',
                        }}
                      >
                        {/* Event Header */}
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                            gap: '0.5rem',
                            marginBottom: '0.5rem',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <span
                              style={{
                                fontSize: '0.72rem',
                                fontWeight: '700',
                                background: 'rgba(13, 148, 136, 0.1)',
                                color: 'var(--color-brand)',
                                padding: '0.15rem 0.45rem',
                                borderRadius: '3px',
                              }}
                            >
                              #{idx + 1}
                            </span>
                            <strong style={{ fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                              {formatEventType(evt.event_type)}
                            </strong>
                            <code
                              style={{
                                fontSize: '0.68rem',
                                background: '#edf0f5',
                                padding: '0.1rem 0.35rem',
                                borderRadius: '3px',
                                color: 'var(--text-secondary)',
                              }}
                            >
                              {evt.event_type}
                            </code>
                          </div>

                          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <Clock size={12} />
                            <span>{formatTimestamp(evt.occurred_at)}</span>
                          </div>
                        </div>

                        {/* Event Metadata Grid */}
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                            gap: '0.5rem',
                            background: '#ffffff',
                            padding: '0.5rem 0.75rem',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.74rem',
                            marginBottom: '0.5rem',
                            border: '1px solid var(--border-subtle)',
                          }}
                        >
                          <div>
                            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.68rem' }}>
                              Actor / Reviewer
                            </span>
                            <span style={{ color: 'var(--text-primary)', fontWeight: '500' }}>
                              {evt.reviewer_name || 'System / Regulatory User'}
                            </span>
                          </div>

                          <div>
                            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.68rem' }}>
                              Status Transition
                            </span>
                            <span style={{ color: 'var(--color-brand)', fontWeight: '500' }}>
                              {evt.previous_status ? `${evt.previous_status} → ` : ''}
                              {evt.new_status || 'TRANSITION'}
                            </span>
                          </div>

                          <div>
                            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.68rem' }}>
                              Linked Identifier
                            </span>
                            <code style={{ fontSize: '0.7rem' }}>
                              {evt.change_id || evt.decision_id || evt.report_id || evt.event_id}
                            </code>
                          </div>
                        </div>

                        {/* Event Hashes & Traceability */}
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                            gap: '0.5rem',
                            fontSize: '0.72rem',
                            paddingTop: '0.25rem',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                            <div>
                              <span style={{ color: 'var(--text-muted)' }}>SHA-256: </span>
                              <code
                                title={evt.event_hash}
                                style={{ color: 'var(--color-brand)', fontWeight: '600' }}
                              >
                                {eventHashDisplay}
                              </code>
                              <button
                                type="button"
                                onClick={() => handleCopyHash(evt.event_hash)}
                                style={{
                                  background: 'transparent',
                                  border: 'none',
                                  color: isCopied ? 'var(--color-success)' : 'var(--text-muted)',
                                  cursor: 'pointer',
                                  padding: '0 0.25rem',
                                  verticalAlign: 'middle',
                                }}
                                title={isCopied ? 'Copied!' : 'Copy full 64-char SHA-256 hash'}
                              >
                                <Copy size={11} />
                              </button>
                              {isCopied && (
                                <span style={{ fontSize: '0.68rem', color: 'var(--color-success)', marginLeft: '0.2rem' }}>
                                  Copied!
                                </span>
                              )}
                            </div>

                            <div>
                              <span style={{ color: 'var(--text-muted)' }}>Prev Link: </span>
                              <code
                                title={evt.previous_event_hash || 'Genesis event'}
                                style={{ color: evt.previous_event_hash ? 'var(--text-secondary)' : 'var(--color-success)' }}
                              >
                                {prevHashDisplay}
                              </code>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => setExpandedEventId(isExpanded ? null : `session_${evt.event_id}`)}
                            className="btn btn-secondary"
                            style={{ fontSize: '0.7rem', padding: '0.2rem 0.5rem' }}
                          >
                            {isExpanded ? (
                              <>
                                <ChevronUp size={11} /> Hide Payload
                              </>
                            ) : (
                              <>
                                <ChevronDown size={11} /> Inspect Details
                              </>
                            )}
                          </button>
                        </div>

                        {/* Expandable Canonical Detail */}
                        {isExpanded && (
                          <div
                            style={{
                              marginTop: '0.65rem',
                              padding: '0.65rem 0.85rem',
                              background: '#ffffff',
                              borderRadius: 'var(--radius-sm)',
                              border: '1px solid var(--border-subtle)',
                              fontSize: '0.72rem',
                            }}
                          >
                            <div style={{ marginBottom: '0.4rem' }}>
                              <strong style={{ color: 'var(--text-secondary)' }}>Event ID: </strong>
                              <code>{evt.event_id}</code>
                            </div>
                            <div style={{ marginBottom: '0.4rem', wordBreak: 'break-all' }}>
                              <strong style={{ color: 'var(--text-secondary)' }}>Full SHA-256 Digest: </strong>
                              <code style={{ color: 'var(--color-brand)', fontWeight: '600' }}>{evt.event_hash}</code>
                            </div>
                            {evt.previous_event_hash && (
                              <div style={{ marginBottom: '0.4rem', wordBreak: 'break-all' }}>
                                <strong style={{ color: 'var(--text-secondary)' }}>Previous SHA-256 Link: </strong>
                                <code style={{ color: 'var(--text-primary)' }}>{evt.previous_event_hash}</code>
                              </div>
                            )}
                            {evt.details && Object.keys(evt.details).length > 0 && (
                              <div style={{ marginTop: '0.4rem' }}>
                                <strong style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '0.2rem' }}>
                                  Canonical Event Details:
                                </strong>
                                <pre
                                  style={{
                                    background: '#f8fafc',
                                    padding: '0.5rem',
                                    borderRadius: '3px',
                                    margin: 0,
                                    fontSize: '0.68rem',
                                    color: 'var(--text-primary)',
                                    border: '1px solid var(--border-subtle)',
                                    overflowX: 'auto',
                                  }}
                                >
                                  {JSON.stringify(evt.details, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </details>
          </div>
        </div>
      )}
    </div>
  );
}
