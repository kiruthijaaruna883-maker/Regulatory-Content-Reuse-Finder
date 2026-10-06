import React, { useState, useEffect } from 'react';
import {
  GitPullRequest,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
  Layers,
  XCircle,
  AlertCircle,
  Play,
  FileText,
  Shield,
  FileCheck2,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import { api } from '../services/api';

const OCCURRENCE_DIMENSIONS = [
  {
    key: 'meaning',
    label: 'Meaning',
    number: 1,
  },
  {
    key: 'template',
    label: 'Template',
    number: 2,
  },
  {
    key: 'context',
    label: 'Context',
    number: 3,
  },
  {
    key: 'structure',
    label: 'Structure',
    number: 4,
  },
  {
    key: 'format',
    label: 'Format',
    number: 5,
  },
  {
    key: 'key_information',
    label: 'Key Information',
    number: 6,
  },
];

function getOccurrenceStatusStyle(status) {
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
    color: 'var(--text-secondary)',
    border: '1px solid var(--border-subtle)',
  };
}

function getScoreBarColor(score) {
  if (score >= 0.8) return 'var(--color-success)';
  if (score >= 0.5) return 'var(--color-warning)';
  return 'var(--color-danger)';
}

export default function ChangeReview({ activeDecision, comparisonContext, onReportApproved }) {
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [impactResults, setImpactResults] = useState({});
  const [analyzingProposal, setAnalyzingProposal] = useState(false);
  const [analysisError, setAnalysisError] = useState(null);

  // Reviewer confirmation state per related occurrence (key: occurrence_id -> 'CONFIRMED' | 'EXCLUDED')
  // CRITICAL SAFETY CONSTRAINT: Must start empty/null (NOT CONFIRMED). No occurrence starts confirmed.
  const [occurrenceSelections, setOccurrenceSelections] = useState({});

  // 6D occurrence evidence expansion state (key: occurrence_id / occKey -> boolean)
  const [expandedEvidence, setExpandedEvidence] = useState({});

  function toggleOccurrenceEvidence(key) {
    setExpandedEvidence((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  }

  // Human regulatory approval gate state (Step 6.7)
  // CRITICAL SAFETY CONSTRAINTS: Must never prefill approver identity; must never default to true!
  const [approverName, setApproverName] = useState('');
  const [approverTitle, setApproverTitle] = useState('');
  const [approvalConfirmed, setApprovalConfirmed] = useState(false);
  const [submittingApproval, setSubmittingApproval] = useState(false);
  const [approvalError, setApprovalError] = useState(null);

  // Extract contextual comparison data if available
  const targetSection = comparisonContext?.targetSection || null;
  const candidateItem = comparisonContext?.candidateItem || null;
  const targetText = comparisonContext?.targetText || targetSection?.text || null;
  const candidateText = comparisonContext?.candidateText || candidateItem?.text || null;
  const analysisResult = comparisonContext?.analysisResult || null;

  const sectionName =
    targetSection?.section ||
    analysisResult?.target_section ||
    null;

  const documentName =
    targetSection?.document_name ||
    analysisResult?.target_document_name ||
    null;

  const targetContentId =
    targetSection?.content_id ||
    analysisResult?.target_content_id ||
    activeDecision?.target_content_id ||
    null;

  const candidateId =
    candidateItem?.content_id ||
    analysisResult?.candidates?.[0]?.content_item?.content_id ||
    analysisResult?.candidates?.[0]?.candidate_id ||
    activeDecision?.candidate_id ||
    null;

  useEffect(() => {
    loadProposals();
  }, []);

  async function loadProposals() {
    setLoading(true);
    try {
      const data = await api.listProposals();
      setProposals(data);
      const initialSelections = {};
      for (const p of data) {
        if (p.related_occurrences) {
          p.related_occurrences.forEach((occ, idx) => {
            const key = occ.occurrence_id || `${p.change_id}_occ_${idx}`;
            if (occ.status === 'CONFIRMED' || occ.status === 'EXCLUDED') {
              initialSelections[key] = occ.status;
            }
          });
        }
        handleValidate(p);
      }
      setOccurrenceSelections((prev) => ({ ...initialSelections, ...prev }));
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

  // Explicit reviewer action to formulate proposal and run impact analysis
  async function handleFormulateProposal() {
    setAnalysisError(null);

    // 1. Guard against REJECT decisions (rejections must never create change proposals)
    if (activeDecision?.decision === 'REJECT') {
      setAnalysisError('Cannot formulate a change proposal for a REJECT decision. Original document content is strictly preserved.');
      return;
    }

    // 2. Validate required decision identifier
    if (!activeDecision?.decision_id) {
      setAnalysisError('Valid active human regulatory decision ID is required to formulate a change proposal.');
      return;
    }

    // 3. Validate required section and target text
    if (!sectionName || !targetText) {
      setAnalysisError(
        'Required comparison context (target section name and original text) is missing. Please select and compare content in Document Review and Candidate Comparison before formulating proposals.'
      );
      return;
    }

    setAnalyzingProposal(true);
    try {
      const payload = {
        decision_id: activeDecision.decision_id,
        section: sectionName,
        original_text: targetText,
        candidate_text: candidateText || null,
        document_name: documentName || null,
        document_version: targetSection?.document_version || null,
      };

      const newProposal = await api.analyzeChangeProposal(payload);

      // Add to proposals list if not already present (duplicate prevention)
      setProposals((prev) => {
        const exists = prev.some((p) => p.change_id === newProposal.change_id);
        return exists ? prev : [newProposal, ...prev];
      });

      // Automatically run validation and impact analysis for the formulated proposal
      await handleValidate(newProposal);
    } catch (err) {
      setAnalysisError(err.message || 'Failed to formulate change proposal.');
    } finally {
      setAnalyzingProposal(false);
    }
  }

  // Handle human confirmation toggle per related occurrence and persist to backend
  async function handleToggleOccurrenceConfirmation(prop, occKey, choice) {
    // 1. Maintain local selection behavior immediately
    setOccurrenceSelections((prev) => ({
      ...prev,
      [occKey]: choice,
    }));

    // 2. Persist reviewer occurrence decisions in backend proposal state
    try {
      const relatedOccs = prop.related_occurrences || [];
      const confirmed_ids = [];
      const excluded_ids = [];

      relatedOccs.forEach((occ, idx) => {
        const key = occ.occurrence_id || `${prop.change_id}_occ_${idx}`;
        const occStatus = key === occKey ? choice : (occurrenceSelections[key] || occ.status);
        if (occStatus === 'CONFIRMED') {
          confirmed_ids.push(occ.occurrence_id);
        } else if (occStatus === 'EXCLUDED') {
          excluded_ids.push(occ.occurrence_id);
        }
      });

      const updatedProp = await api.confirmOccurrences({
        change_id: prop.change_id,
        confirmed_occurrence_ids: confirmed_ids,
        excluded_occurrence_ids: excluded_ids,
      });

      // 3. Replace stale proposal state with returned backend state
      setProposals((prev) =>
        prev.map((p) => (p.change_id === updatedProp.change_id ? updatedProp : p))
      );

      // 4. Update impactResults with recalculated impact analysis
      if (updatedProp.impact_analysis) {
        setImpactResults((prev) => ({
          ...prev,
          [updatedProp.change_id]: updatedProp.impact_analysis,
        }));
      }
    } catch (err) {
      console.error('Failed to persist occurrence confirmation:', err);
    }
  }

  // Step 6.7: Explicit Human Regulatory Approval Handler
  async function handleAuthorizeApproval(prop, unresolvedOccurrences) {
    setApprovalError(null);

    // 1. Enforce that all related occurrences must be resolved before approval can proceed
    if (unresolvedOccurrences.length > 0) {
      setApprovalError(
        `Action Blocked: ${unresolvedOccurrences.length} related occurrence(s) remain unresolved. Please review and mark every occurrence as either Confirmed or Excluded.`
      );
      return;
    }

    // 2. Validate Approver Full Name
    const cleanName = approverName.trim();
    if (!cleanName) {
      setApprovalError('Approver full name is required for regulatory authorization.');
      return;
    }

    // 3. Validate Approver Regulatory Authority Title
    const cleanTitle = approverTitle.trim();
    if (!cleanTitle) {
      setApprovalError('Approver regulatory authority title/role is required for authorization.');
      return;
    }

    // 4. Validate Explicit Confirmation Checkbox (strictly must be checked)
    if (!approvalConfirmed) {
      setApprovalError('Explicit human authorization confirmation checkbox must be checked.');
      return;
    }

    setSubmittingApproval(true);
    try {
      const fullApproverIdentity = `${cleanName}, ${cleanTitle}`;
      const relatedOccs = prop.related_occurrences || [];
      const occSummary =
        relatedOccs.length > 0
          ? relatedOccs
              .map((occ, idx) => {
                const key = occ.occurrence_id || `${prop.change_id}_occ_${idx}`;
                const status = occurrenceSelections[key] || (occ.status !== 'PENDING' ? occ.status : undefined);
                return `[${occ.section} (${occ.match_type})]: ${
                  status === 'CONFIRMED' ? 'CONFIRMED FOR CHANGE' : 'EXCLUDED/PRESERVED'
                }`;
              })
              .join('; ')
          : 'No related occurrences identified.';

      const payload = {
        approver_name: fullApproverIdentity,
        approval_confirmation: true,
        proposal_ids: [prop.change_id],
        document_name: prop.document_name || documentName || null,
        document_version: prop.document_version || targetSection?.document_version || null,
        audit_notes: `Authorized by ${fullApproverIdentity}. Occurrence review: ${occSummary}. Rationale: ${prop.rationale}`,
      };

      const report = await api.approveAndGenerateReport(payload);

      // On successful authorization, pass authentic report to App.jsx to navigate to Approved Change Report
      if (onReportApproved) {
        onReportApproved(report);
      }
    } catch (err) {
      setApprovalError(err.message || 'Regulatory approval authorization failed.');
    } finally {
      setSubmittingApproval(false);
    }
  }

  // Check if a proposal has already been formulated for the active decision
  const existingActiveProposal = activeDecision
    ? proposals.find((p) => p.decision_id === activeDecision.decision_id)
    : null;

  return (
    <div>
      {/* Screen Header */}
      <div className="screen-header">
        <div>
          <h2>Controlled Document Change Review</h2>
          <p>Impact analysis, multi-layer occurrence review, and human regulatory authorization</p>
        </div>
      </div>

      {/* 1. DECISION SUMMARY STATION (When activeDecision is present) */}
      {activeDecision && (
        <div className="card" style={{ maxWidth: '900px', margin: '0 auto 1.5rem auto' }}>
          <div className="card-header">
            <span className="card-title">
              <Shield size={16} color="var(--color-brand)" /> Active Regulatory Decision Summary
            </span>
            <span className={`badge badge-${activeDecision.decision.toLowerCase()}`}>
              {activeDecision.decision} AUTHORIZED
            </span>
          </div>

          <div className="grid-2" style={{ gap: '1rem', marginBottom: '1rem', fontSize: '0.8rem' }}>
            {/* Decision Details */}
            <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--color-brand)', fontWeight: '600', display: 'block', marginBottom: '0.35rem' }}>
                Authorization Audit Record
              </span>
              <div style={{ color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                <span>Decision ID: <code>{activeDecision.decision_id}</code></span>
                <span>Reviewer: <strong>{activeDecision.reviewer_name}</strong></span>
                <span>Timestamp: <strong>{new Date(activeDecision.decided_at).toLocaleString()}</strong></span>
                {activeDecision.reviewer_notes && (
                  <span style={{ marginTop: '0.25rem' }}>
                    Rationale: <em style={{ color: 'var(--text-primary)' }}>{activeDecision.reviewer_notes}</em>
                  </span>
                )}
                {activeDecision.adaptation_instructions && (
                  <span style={{ marginTop: '0.25rem', color: '#fbbf24' }}>
                    Adaptation Instructions: <strong>{activeDecision.adaptation_instructions}</strong>
                  </span>
                )}
              </div>
            </div>

            {/* Target & Candidate Provenance */}
            <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--color-dailymed)', fontWeight: '600', display: 'block', marginBottom: '0.35rem' }}>
                Subject Content Provenance
              </span>
              <div style={{ color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                <span>Target Section: <strong>{sectionName || 'Not specified'}</strong></span>
                <span>Target Document: <strong>{documentName || 'Internal Draft'}</strong></span>
                <span>Target Content ID: <code>{targetContentId || 'Not assigned'}</code></span>
                <span>Candidate ID: <code>{candidateId || 'Not assigned'}</code></span>
                {candidateItem?.source && <span>Candidate Source: <strong>{candidateItem.source}</strong></span>}
                {candidateItem?.document_name && <span>Candidate Document: <strong>{candidateItem.document_name}</strong></span>}
              </div>
            </div>
          </div>

          {/* REJECT DECISION PATH: Informational and factual audit preservation notice */}
          {activeDecision.decision === 'REJECT' && (
            <div
              style={{
                padding: '1.25rem',
                background: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.35)',
                borderRadius: 'var(--radius-md)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <XCircle size={20} color="var(--color-danger)" />
                <strong style={{ color: '#fca5a5', fontSize: '0.95rem' }}>
                  Candidate Reference Standard Rejected — Original Content Preserved
                </strong>
              </div>
              <p style={{ color: 'var(--text-primary)', fontSize: '0.84rem', margin: '0 0 0.75rem 0', lineHeight: 1.5 }}>
                The regulatory reviewer has authorized a <strong>REJECT</strong> decision for this candidate standard. The candidate wording has been formally declined, and original draft content in <strong>{sectionName || 'the target section'}</strong> remains strictly unchanged.
              </p>
              <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                <strong>Strict Governance Notice:</strong> No controlled change proposal will be formulated, no impact analysis will be executed, and no change propagation will occur for this rejected decision. The original source document text is 100% preserved.
              </div>
            </div>
          )}

          {/* REUSE / ADAPT DECISION PATH: Explicit Formulation Action when not yet formulated */}
          {(activeDecision.decision === 'REUSE' || activeDecision.decision === 'ADAPT') && !existingActiveProposal && (
            <div
              style={{
                padding: '1.1rem',
                background: 'rgba(59, 130, 246, 0.06)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                borderRadius: 'var(--radius-md)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                <div>
                  <strong style={{ color: '#fff', fontSize: '0.9rem', display: 'block', marginBottom: '0.2rem' }}>
                    Formulate Controlled Change Proposal & Run Impact Analysis
                  </strong>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', margin: 0 }}>
                    Synthesize proposed replacement text, detect 4-layer related occurrences, and run deterministic validation rules.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={handleFormulateProposal}
                  className="btn btn-primary"
                  disabled={analyzingProposal || !targetText || !sectionName}
                  style={{ fontSize: '0.84rem', padding: '0.5rem 1rem' }}
                >
                  <Play size={14} /> {analyzingProposal ? 'Analyzing & Formulating...' : 'Run Impact Analysis & Formulate Proposal'}
                </button>
              </div>

              {/* Missing Context Warning */}
              {(!targetText || !sectionName) && (
                <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-warning)', fontSize: '0.78rem' }}>
                  <AlertTriangle size={14} />
                  <span>Required comparison context is incomplete in this session. Return to Candidate Comparison to establish target text and section context.</span>
                </div>
              )}

              {/* Inline Analysis Error */}
              {analysisError && (
                <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-danger)', fontSize: '0.8rem', background: 'rgba(239, 68, 68, 0.12)', padding: '0.5rem 0.75rem', borderRadius: 'var(--radius-sm)' }}>
                  <AlertCircle size={15} />
                  <span>{analysisError}</span>
                </div>
              )}
            </div>
          )}

          {/* Notice when existing proposal is already formulated for active decision */}
          {(activeDecision.decision === 'REUSE' || activeDecision.decision === 'ADAPT') && existingActiveProposal && (
            <div style={{ padding: '0.75rem 1rem', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', color: 'var(--color-success)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <CheckCircle2 size={16} />
              <span>Controlled change proposal <code>{existingActiveProposal.change_id}</code> is active for this decision. Review impact assessment, occurrences, and authorization gate below.</span>
            </div>
          )}
        </div>
      )}

      {/* 2. PROPOSALS LIST & IMPACT / OCCURRENCE REVIEW / STEP 6.7 APPROVAL */}
      {proposals.length === 0 ? (
        <div className="card" style={{ maxWidth: '900px', margin: '0 auto' }}>
          <div className="empty-state">
            <GitPullRequest size={36} />
            <p>
              {loading
                ? 'Loading change proposals...'
                : 'No active change proposals. Record a REUSE or ADAPT decision in the Decision Panel to initiate controlled proposals.'}
            </p>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
              Note: REJECT decisions preserve original content and do not generate change proposals.
            </p>
          </div>
        </div>
      ) : (
        <div style={{ maxWidth: '900px', margin: '0 auto' }}>
          {proposals.map((prop) => {
            const impact = impactResults[prop.change_id] || prop.impact_analysis;
            const relatedOccs = prop.related_occurrences || [];
            const isApproved = prop.status === 'APPROVED';

            // Calculate occurrence resolution status for Step 6.7 handoff
            const confirmedOccs = relatedOccs.filter((occ, idx) => {
              const key = occ.occurrence_id || `${prop.change_id}_occ_${idx}`;
              const sel = occurrenceSelections[key] || (occ.status !== 'PENDING' ? occ.status : undefined);
              return sel === 'CONFIRMED';
            });
            const excludedOccs = relatedOccs.filter((occ, idx) => {
              const key = occ.occurrence_id || `${prop.change_id}_occ_${idx}`;
              const sel = occurrenceSelections[key] || (occ.status !== 'PENDING' ? occ.status : undefined);
              return sel === 'EXCLUDED';
            });
            const unresolvedOccs = relatedOccs.filter((occ, idx) => {
              const key = occ.occurrence_id || `${prop.change_id}_occ_${idx}`;
              const sel = occurrenceSelections[key] || (occ.status !== 'PENDING' ? occ.status : undefined);
              return sel !== 'CONFIRMED' && sel !== 'EXCLUDED';
            });

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
                    <span
                      className="status-pill"
                      style={{
                        background: isApproved ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                        color: isApproved ? 'var(--color-success)' : 'var(--color-warning)',
                        borderColor: isApproved ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)',
                      }}
                    >
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
                    <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.45, margin: 0, fontFamily: 'monospace' }}>
                      {prop.original_text}
                    </p>
                  </div>

                  <div style={{ background: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)', padding: '0.85rem', borderRadius: 'var(--radius-md)' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: '600', color: '#34d399', display: 'block', marginBottom: '0.3rem' }}>
                      Proposed Replacement / Adapted Content
                    </span>
                    <p style={{ fontSize: '0.84rem', color: '#fff', lineHeight: 1.45, margin: 0, fontFamily: 'monospace' }}>
                      {prop.proposed_text}
                    </p>
                  </div>
                </div>

                {/* Rationale & Provenance Traceability */}
                <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', marginBottom: '0.8rem' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
                    Documented Regulatory Rationale:
                  </span>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>
                    {prop.rationale}
                  </span>
                  {prop.source_evidence && (
                    <div style={{ marginTop: '0.4rem', fontSize: '0.76rem', color: 'var(--color-brand)' }}>
                      <strong>Evidence Citation:</strong> {prop.source_evidence.source} ({prop.source_evidence.exact_quote})
                    </div>
                  )}
                </div>

                {/* 3. IMPACT ANALYSIS STATION */}
                {impact && (
                  <div style={{ marginBottom: '1.25rem', background: 'var(--bg-surface-elevated)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
                      <div>
                        <span style={{ fontSize: '0.84rem', fontWeight: '600', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <AlertTriangle size={15} color={impact.risk_level === 'HIGH' ? 'var(--color-danger)' : 'var(--color-warning)'} />
                          Regulatory Impact Assessment
                        </span>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          Assessed via deterministic regulatory validation rules; not probabilistic prediction
                        </span>
                      </div>
                      <span
                        className="badge"
                        style={{
                          background: impact.risk_level === 'HIGH' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                          color: impact.risk_level === 'HIGH' ? 'var(--color-danger)' : 'var(--color-success)',
                          fontSize: '0.76rem',
                          padding: '0.25rem 0.6rem',
                        }}
                      >
                        {impact.risk_level} RISK
                      </span>
                    </div>

                    {/* Scope Metrics Grid */}
                    <div className="grid-3" style={{ gap: '0.5rem', marginBottom: '0.75rem' }}>
                      <div style={{ background: 'var(--bg-main)', padding: '0.5rem', borderRadius: 'var(--radius-sm)' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>AFFECTED SECTIONS</span>
                        <strong style={{ fontSize: '0.82rem', color: '#fff' }}>
                          {impact.affected_sections_count || impact.affected_sections?.length || 1}
                        </strong>
                        {impact.affected_sections && impact.affected_sections.length > 0 && (
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', display: 'block', marginTop: '0.1rem' }}>
                            {impact.affected_sections.join(', ')}
                          </span>
                        )}
                      </div>

                      <div style={{ background: 'var(--bg-main)', padding: '0.5rem', borderRadius: 'var(--radius-sm)' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>AFFECTED DOCUMENTS</span>
                        <strong style={{ fontSize: '0.82rem', color: '#fff' }}>
                          {impact.affected_documents?.length || 1}
                        </strong>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', display: 'block', marginTop: '0.1rem' }}>
                          {impact.affected_documents?.join(', ') || prop.document_name || 'Subject Document'}
                        </span>
                      </div>

                      <div style={{ background: 'var(--bg-main)', padding: '0.5rem', borderRadius: 'var(--radius-sm)' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>TOTAL AFFECTED ITEMS</span>
                        <strong style={{ fontSize: '0.82rem', color: '#fff' }}>
                          {impact.affected_content_count || 1}
                        </strong>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', display: 'block', marginTop: '0.1rem' }}>
                          Target section + {relatedOccs.length} occurrences
                        </span>
                      </div>
                    </div>

                    {/* Observed vs Potential Impacts Grid */}
                    <div className="grid-2" style={{ gap: '0.6rem', marginBottom: '0.75rem' }}>
                      {/* Observed Impacts (Direct) */}
                      <div style={{ background: 'var(--bg-main)', padding: '0.65rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.3rem' }}>
                          <CheckCircle2 size={13} color="var(--color-success)" />
                          <strong style={{ fontSize: '0.76rem', color: '#34d399' }}>
                            Observed Impacts (Direct)
                          </strong>
                        </div>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem' }}>
                          Direct textual replacements verified against target draft:
                        </span>
                        <ul style={{ margin: 0, paddingLeft: '1rem', fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                          {(impact.observed_impacts || [`Direct replacement in ${prop.section}`]).map((obs, i) => (
                            <li key={i}>{obs}</li>
                          ))}
                        </ul>
                      </div>

                      {/* Potential Impacts (Reviewer Verification Required) */}
                      <div style={{ background: 'var(--bg-main)', padding: '0.65rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.3rem' }}>
                          <AlertTriangle size={13} color="var(--color-warning)" />
                          <strong style={{ fontSize: '0.76rem', color: '#fbbf24' }}>
                            Potential Impacts (Requires Verification)
                          </strong>
                        </div>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem' }}>
                          Cross-section occurrences requiring professional evaluation:
                        </span>
                        <ul style={{ margin: 0, paddingLeft: '1rem', fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                          {impact.potential_impacts && impact.potential_impacts.length > 0 ? (
                            impact.potential_impacts.map((pot, i) => <li key={i}>{pot}</li>)
                          ) : (
                            <li>No high-risk cross-section anomalies detected.</li>
                          )}
                        </ul>
                      </div>
                    </div>

                    {/* Deterministic Validation Findings */}
                    {impact.findings && (
                      <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem' }}>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.3rem' }}>
                          Deterministic Regulatory Rules Evaluation:
                        </span>
                        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                          {impact.findings.map((f, i) => (
                            <span
                              key={i}
                              className="badge"
                              style={{
                                background: f.passed ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                color: f.passed ? 'var(--color-success)' : 'var(--color-danger)',
                                fontSize: '0.69rem',
                              }}
                            >
                              {f.rule_id}: {f.message}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 4. RELATED OCCURRENCE REVIEW STATION */}
                <div style={{ background: 'var(--bg-surface-elevated)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)', marginBottom: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
                    <span style={{ fontSize: '0.84rem', fontWeight: '600', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Layers size={15} color="var(--color-brand)" /> Related Occurrence Review ({relatedOccs.length})
                    </span>
                    <span className="badge badge-section" style={{ fontSize: '0.7rem' }}>
                      4-Layer Detection Active
                    </span>
                  </div>

                  {/* Mandatory Zero Autonomous Propagation Notice */}
                  <div
                    style={{
                      padding: '0.65rem 0.85rem',
                      background: 'rgba(59, 130, 246, 0.08)',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      borderRadius: 'var(--radius-sm)',
                      marginBottom: '0.6rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <ShieldAlert size={16} color="var(--color-brand)" style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: '0.76rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>
                      <strong>Zero Autonomous Propagation:</strong> No related occurrence is changed automatically. Each occurrence requires explicit human confirmation. Reviewer selections are stored for review only and do not mutate source documents.
                    </span>
                  </div>

                  {/* False-Match Protection Notice */}
                  <div
                    style={{
                      padding: '0.65rem 0.85rem',
                      background: 'rgba(245, 158, 11, 0.08)',
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                      borderRadius: 'var(--radius-sm)',
                      marginBottom: '0.75rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <ShieldCheck size={16} color="var(--color-warning)" style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: '0.76rem', color: 'var(--text-primary)', lineHeight: 1.4 }}>
                      <strong>Clinical False-Match Protection Active:</strong> Potentially conflicting clinical/content matches (disparate drug names, conflicting active ingredients, or mismatched therapeutic routes) are automatically excluded by the backend occurrence engine from the related-occurrence set and require human review.
                    </span>
                  </div>

                  {/* Occurrences List */}
                  {relatedOccs.length > 0 ? (
                    <div>
                      {relatedOccs.map((occ, idx) => {
                        const occKey = occ.occurrence_id || `${prop.change_id}_occ_${idx}`;
                        const currentSelection = occurrenceSelections[occKey] || (occ.status !== 'PENDING' ? occ.status : undefined); // undefined | 'CONFIRMED' | 'EXCLUDED'

                        return (
                          <div
                            key={occKey}
                            style={{
                              background: 'var(--bg-main)',
                              padding: '0.75rem',
                              borderRadius: 'var(--radius-sm)',
                              marginBottom: '0.6rem',
                              border: '1px solid var(--border-subtle)',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.3rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                <FileText size={14} color="var(--color-brand)" />
                                <strong style={{ fontSize: '0.82rem', color: '#fff' }}>
                                  {occ.section}
                                </strong>
                                {occ.document_name && (
                                  <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                                    ({occ.document_name})
                                  </span>
                                )}
                                {occ.location && (
                                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                                    • {occ.location}
                                  </span>
                                )}
                              </div>

                              <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                                <span className="badge badge-section" style={{ fontSize: '0.68rem' }}>
                                  {occ.match_type.replace('_', ' ').toUpperCase()}
                                </span>
                                {/* Reviewer Confirmation Status Badge */}
                                <span
                                  className="badge"
                                  style={{
                                    fontSize: '0.68rem',
                                    background:
                                      currentSelection === 'CONFIRMED'
                                        ? 'rgba(16, 185, 129, 0.2)'
                                        : currentSelection === 'EXCLUDED'
                                        ? 'rgba(239, 68, 68, 0.2)'
                                        : 'rgba(245, 158, 11, 0.15)',
                                    color:
                                      currentSelection === 'CONFIRMED'
                                        ? 'var(--color-success)'
                                        : currentSelection === 'EXCLUDED'
                                        ? 'var(--color-danger)'
                                        : 'var(--color-warning)',
                                  }}
                                >
                                  {currentSelection === 'CONFIRMED'
                                    ? 'CONFIRMED BY REVIEWER'
                                    : currentSelection === 'EXCLUDED'
                                    ? 'EXCLUDED BY REVIEWER'
                                    : 'PENDING REVIEW (UNCONFIRMED)'}
                                </span>
                              </div>
                            </div>

                            {/* Occurrence Current Text */}
                            <p style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', margin: '0.3rem 0', lineHeight: 1.45, fontFamily: 'monospace' }}>
                              {occ.current_text}
                            </p>

                            {/* Matching Basis / Evidence */}
                            {occ.reason && (
                              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>
                                <strong>Matching Basis:</strong> {occ.reason}
                              </div>
                            )}

                            {/* Phase 6G.4: Advisory Occurrence Recommendation */}
                            {occ.recommended_action && (
                              <div
                                style={{
                                  margin: '0.45rem 0',
                                  padding: '0.6rem 0.8rem',
                                  background: 'var(--bg-surface)',
                                  borderRadius: 'var(--radius-sm)',
                                  border: `1px solid ${
                                    occ.recommended_action === 'CONFIRM'
                                      ? 'rgba(16, 185, 129, 0.35)'
                                      : occ.recommended_action === 'EXCLUDE'
                                      ? 'rgba(239, 68, 68, 0.35)'
                                      : 'rgba(245, 158, 11, 0.35)'
                                  }`,
                                }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '0.25rem' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                    <span
                                      className="badge"
                                      style={{
                                        fontSize: '0.68rem',
                                        fontWeight: '700',
                                        background:
                                          occ.recommended_action === 'CONFIRM'
                                            ? 'rgba(16, 185, 129, 0.2)'
                                            : occ.recommended_action === 'EXCLUDE'
                                            ? 'rgba(239, 68, 68, 0.2)'
                                            : 'rgba(245, 158, 11, 0.2)',
                                        color:
                                          occ.recommended_action === 'CONFIRM'
                                            ? 'var(--color-success)'
                                            : occ.recommended_action === 'EXCLUDE'
                                            ? 'var(--color-danger)'
                                            : 'var(--color-warning)',
                                      }}
                                    >
                                      SYSTEM RECOMMENDATION: {occ.recommended_action.replace('_', ' ')}
                                    </span>
                                    <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                                      Advisory Recommendation Only — Human Reviewer Confirmation Required
                                    </span>
                                  </div>

                                  {/* STEP 8: Apply Recommendation Button (preselects local control only; does not submit) */}
                                  {(occ.recommended_action === 'CONFIRM' || occ.recommended_action === 'EXCLUDE') && (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        const choice = occ.recommended_action === 'CONFIRM' ? 'CONFIRMED' : 'EXCLUDED';
                                        setOccurrenceSelections((prev) => ({
                                          ...prev,
                                          [occKey]: choice,
                                        }));
                                      }}
                                      className="btn btn-secondary"
                                      style={{
                                        fontSize: '0.7rem',
                                        padding: '0.2rem 0.5rem',
                                        cursor: 'pointer',
                                        borderColor:
                                          occ.recommended_action === 'CONFIRM'
                                            ? 'rgba(16, 185, 129, 0.4)'
                                            : 'rgba(239, 68, 68, 0.4)',
                                        color:
                                          occ.recommended_action === 'CONFIRM'
                                            ? 'var(--color-success)'
                                            : 'var(--color-danger)',
                                      }}
                                    >
                                      Apply Recommendation ({occ.recommended_action === 'CONFIRM' ? 'Confirm' : 'Exclude'})
                                    </button>
                                  )}
                                </div>

                                {occ.recommendation_reason && (
                                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                    <strong>Reason:</strong> {occ.recommendation_reason}
                                  </div>
                                )}
                              </div>
                            )}

                            {/* 6D Alignment Evidence Section (Phase 6E) */}
                            {Boolean(occ.dimensional_scores && occ.dimensional_evidence) && (
                              <div
                                style={{
                                  margin: '0.6rem 0',
                                  padding: '0.6rem',
                                  background: 'rgba(255, 255, 255, 0.02)',
                                  border: '1px solid var(--border-subtle)',
                                  borderRadius: 'var(--radius-sm)',
                                }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                                  <span style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-brand)', fontWeight: '600' }}>
                                    6D Alignment Evidence
                                  </span>
                                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                                    Multi-dimensional comparison across 6 regulatory dimensions
                                  </span>
                                </div>

                                {/* Six Compact Summary Pills */}
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '0.55rem' }}>
                                  {OCCURRENCE_DIMENSIONS.map((dim) => {
                                    const evalData = occ.dimensional_evidence?.[dim.key];
                                    const rawScore = occ.dimensional_scores?.[dim.key] ?? evalData?.score;
                                    const scorePct = rawScore !== undefined && rawScore !== null ? Math.round(rawScore * 100) : null;
                                    const status = evalData?.status || 'NOT_APPLICABLE';
                                    const badgeStyle = getOccurrenceStatusStyle(status);

                                    return (
                                      <div
                                        key={dim.key}
                                        style={{
                                          display: 'inline-flex',
                                          alignItems: 'center',
                                          gap: '0.35rem',
                                          padding: '0.2rem 0.45rem',
                                          borderRadius: 'var(--radius-sm)',
                                          fontSize: '0.7rem',
                                          border: badgeStyle.border,
                                          background: badgeStyle.background,
                                          color: badgeStyle.color,
                                        }}
                                      >
                                        <span style={{ fontWeight: '600', color: 'var(--text-primary)' }}>{dim.label}:</span>
                                        {scorePct !== null && <span>{scorePct}%</span>}
                                        <span style={{ fontWeight: '700' }}>{status}</span>
                                      </div>
                                    );
                                  })}
                                </div>

                                {/* Expand/Collapse Toggle Button */}
                                <div>
                                  <button
                                    type="button"
                                    onClick={() => toggleOccurrenceEvidence(occKey)}
                                    aria-expanded={Boolean(expandedEvidence[occKey])}
                                    aria-controls={`evidence-panel-${occKey}`}
                                    className="btn btn-secondary"
                                    style={{
                                      width: '100%',
                                      fontSize: '0.72rem',
                                      padding: '0.3rem 0.6rem',
                                      display: 'flex',
                                      justifyContent: 'space-between',
                                      alignItems: 'center',
                                      background: 'var(--bg-surface-elevated)',
                                      border: '1px solid var(--border-subtle)',
                                      cursor: 'pointer',
                                    }}
                                  >
                                    <span>
                                      {expandedEvidence[occKey]
                                        ? 'Hide 6D Evidence & Reasoning'
                                        : 'Inspect 6D Evidence & Reasoning'}
                                    </span>
                                    {expandedEvidence[occKey] ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                                  </button>

                                  {/* Expanded Dimension Details */}
                                  {expandedEvidence[occKey] && (
                                    <div
                                      id={`evidence-panel-${occKey}`}
                                      style={{
                                        marginTop: '0.55rem',
                                        display: 'grid',
                                        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                                        gap: '0.55rem',
                                      }}
                                    >
                                      {OCCURRENCE_DIMENSIONS.map((dim) => {
                                        const evalData = occ.dimensional_evidence?.[dim.key];
                                        const rawScore = occ.dimensional_scores?.[dim.key] ?? evalData?.score;
                                        const scorePct = rawScore !== undefined && rawScore !== null ? Math.round(rawScore * 100) : null;
                                        const status = evalData?.status || 'NOT_APPLICABLE';
                                        const badgeStyle = getOccurrenceStatusStyle(status);

                                        return (
                                          <div
                                            key={dim.key}
                                            style={{
                                              background: 'var(--bg-surface-elevated)',
                                              border: '1px solid var(--border-subtle)',
                                              borderRadius: 'var(--radius-sm)',
                                              padding: '0.55rem',
                                              display: 'flex',
                                              flexDirection: 'column',
                                              gap: '0.35rem',
                                            }}
                                          >
                                            {/* Header: Dimension Number & Label + Status Badge */}
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                              <strong style={{ fontSize: '0.76rem', color: '#fff' }}>
                                                {dim.number}. {dim.label}
                                              </strong>
                                              <span
                                                className="badge"
                                                style={{
                                                  fontSize: '0.64rem',
                                                  padding: '0.15rem 0.35rem',
                                                  ...badgeStyle,
                                                }}
                                              >
                                                {status}
                                              </span>
                                            </div>

                                            {/* Score & Progress Bar */}
                                            {scorePct !== null && (
                                              <div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-secondary)', marginBottom: '0.15rem' }}>
                                                  <span>Alignment Score</span>
                                                  <strong style={{ color: '#fff' }}>{scorePct}%</strong>
                                                </div>
                                                <div style={{ height: '4px', background: 'rgba(255, 255, 255, 0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                                                  <div
                                                    style={{
                                                      height: '100%',
                                                      width: `${Math.min(Math.max(scorePct, 0), 100)}%`,
                                                      background: getScoreBarColor(rawScore),
                                                    }}
                                                  />
                                                </div>
                                              </div>
                                            )}

                                            {/* Details */}
                                            {evalData?.details && (
                                              <p style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', margin: '0.2rem 0', lineHeight: 1.4 }}>
                                                {evalData.details}
                                              </p>
                                            )}

                                            {/* Observed from Source */}
                                            {evalData?.observed_from_source && (
                                              <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.25rem', marginTop: '0.15rem' }}>
                                                <span style={{ color: 'var(--color-brand)', fontWeight: '600', fontSize: '0.66rem', display: 'block', marginBottom: '0.1rem' }}>
                                                  Observed from Source:
                                                </span>
                                                <span style={{ color: 'var(--text-secondary)', fontSize: '0.69rem', wordBreak: 'break-word', fontFamily: 'monospace' }}>
                                                  {evalData.observed_from_source}
                                                </span>
                                              </div>
                                            )}

                                            {/* Model Interpretation */}
                                            {evalData?.model_interpretation && (
                                              <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.25rem', marginTop: '0.15rem' }}>
                                                <span style={{ color: 'var(--color-openfda)', fontWeight: '600', fontSize: '0.66rem', display: 'block', marginBottom: '0.1rem' }}>
                                                  Model Interpretation:
                                                </span>
                                                <span style={{ color: 'var(--text-secondary)', fontSize: '0.69rem', wordBreak: 'break-word' }}>
                                                  {evalData.model_interpretation}
                                                </span>
                                              </div>
                                            )}
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}

                            {/* Human Reviewer Confirmation Controls */}
                            <div
                              style={{
                                borderTop: '1px dashed var(--border-subtle)',
                                paddingTop: '0.45rem',
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                flexWrap: 'wrap',
                                gap: '0.5rem',
                              }}
                            >
                              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                Coordinated Propagation Review:
                              </span>

                              <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', fontSize: '0.76rem' }}>
                                  <input
                                    type="radio"
                                    name={`occ_choice_${occKey}`}
                                    checked={currentSelection === 'CONFIRMED'}
                                    onChange={() => handleToggleOccurrenceConfirmation(prop, occKey, 'CONFIRMED')}
                                  />
                                  <span style={{ color: currentSelection === 'CONFIRMED' ? 'var(--color-success)' : 'var(--text-secondary)' }}>
                                    Confirm for coordinated change
                                  </span>
                                </label>

                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', fontSize: '0.76rem' }}>
                                  <input
                                    type="radio"
                                    name={`occ_choice_${occKey}`}
                                    checked={currentSelection === 'EXCLUDED'}
                                    onChange={() => handleToggleOccurrenceConfirmation(prop, occKey, 'EXCLUDED')}
                                  />
                                  <span style={{ color: currentSelection === 'EXCLUDED' ? 'var(--color-danger)' : 'var(--text-secondary)' }}>
                                    Exclude / preserve
                                  </span>
                                </label>

                                {currentSelection && currentSelection !== occ.status && (
                                  <button
                                    type="button"
                                    onClick={() => handleToggleOccurrenceConfirmation(prop, occKey, currentSelection)}
                                    className="btn btn-primary"
                                    style={{
                                      fontSize: '0.68rem',
                                      padding: '0.15rem 0.5rem',
                                      marginLeft: '0.4rem',
                                    }}
                                  >
                                    Save Decision ({currentSelection === 'CONFIRMED' ? 'Confirm' : 'Exclude'})
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                      No cross-section related occurrences detected for this text sequence. The proposed modification remains isolated to <strong>{prop.section}</strong>.
                    </div>
                  )}
                </div>

                {/* 5. STEP 6.7: HUMAN REGULATORY APPROVAL GATE */}
                <div
                  style={{
                    background: 'rgba(59, 130, 246, 0.04)',
                    border: '1px solid rgba(59, 130, 246, 0.3)',
                    borderRadius: 'var(--radius-md)',
                    padding: '1.25rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem' }}>
                    <ShieldCheck size={20} color="var(--color-brand)" />
                    <div>
                      <strong style={{ fontSize: '0.9rem', color: '#fff', display: 'block' }}>
                        Human Regulatory Approval Gate
                      </strong>
                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                        Explicit authorization to compile this controlled proposal into the Approved Change Report
                      </span>
                    </div>
                  </div>

                  {isApproved ? (
                    <div style={{ color: 'var(--color-success)', fontSize: '0.84rem', display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', background: 'rgba(16, 185, 129, 0.1)', borderRadius: 'var(--radius-sm)' }}>
                      <CheckCircle2 size={16} />
                      <span>This change has been authorized by the regulatory approver and recorded in the Approved Change Report.</span>
                    </div>
                  ) : (
                    <div>
                      {/* Summary of What is Being Authorized */}
                      <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', marginBottom: '1rem', fontSize: '0.78rem' }}>
                        <strong style={{ color: 'var(--color-brand)', display: 'block', marginBottom: '0.35rem' }}>
                          Authorization Specification Summary:
                        </strong>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', color: 'var(--text-secondary)' }}>
                          <span>Subject Target: <strong>{prop.document_name || documentName || 'Internal Draft'} — {prop.section}</strong></span>
                          <span>Controlled Action: <strong>{prop.decision_type}</strong></span>
                          <span>Evaluated Risk Level: <strong style={{ color: impact?.risk_level === 'HIGH' ? 'var(--color-danger)' : 'var(--color-success)' }}>{impact?.risk_level || 'LOW'} RISK</strong></span>
                          <span>
                            Occurrence Resolutions: <strong>{confirmedOccs.length} confirmed</strong>, <strong>{excludedOccs.length} excluded</strong>
                            {unresolvedOccs.length > 0 && <span style={{ color: 'var(--color-danger)' }}> ({unresolvedOccs.length} unreviewed)</span>}
                          </span>
                        </div>
                      </div>

                      {/* Unresolved Occurrences Blocking Warning */}
                      {unresolvedOccs.length > 0 && (
                        <div
                          style={{
                            padding: '0.75rem 1rem',
                            background: 'rgba(239, 68, 68, 0.12)',
                            border: '1px solid rgba(239, 68, 68, 0.35)',
                            borderRadius: 'var(--radius-sm)',
                            marginBottom: '1rem',
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '0.5rem',
                          }}
                        >
                          <AlertCircle size={17} color="var(--color-danger)" style={{ flexShrink: 0, marginTop: '2px' }} />
                          <div style={{ fontSize: '0.78rem', color: '#fca5a5' }}>
                            <strong>Action Blocked — Unreviewed Occurrences:</strong> {unresolvedOccs.length} related occurrence(s) remain <em>PENDING REVIEW (UNCONFIRMED)</em>. You must explicitly resolve every displayed occurrence above (as either <strong>Confirm for coordinated change</strong> or <strong>Exclude / preserve</strong>) before authorizing regulatory approval.
                          </div>
                        </div>
                      )}

                      {/* Approver Identity Inputs */}
                      <div className="grid-2" style={{ gap: '0.75rem', marginBottom: '1rem' }}>
                        <div>
                          <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem', fontWeight: '500' }}>
                            Approver Full Name *
                          </label>
                          <input
                            type="text"
                            className="input-text"
                            placeholder="e.g., Dr. Jane Doe"
                            value={approverName}
                            onChange={(e) => {
                              setApproverName(e.target.value);
                              setApprovalError(null);
                            }}
                            style={{ width: '100%' }}
                          />
                        </div>

                        <div>
                          <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem', fontWeight: '500' }}>
                            Regulatory Authority Title / Role *
                          </label>
                          <input
                            type="text"
                            className="input-text"
                            placeholder="e.g., Senior Director, Regulatory Affairs"
                            value={approverTitle}
                            onChange={(e) => {
                              setApproverTitle(e.target.value);
                              setApprovalError(null);
                            }}
                            style={{ width: '100%' }}
                          />
                        </div>
                      </div>

                      {/* Explicit Human Authorization Confirmation Checkbox */}
                      <div style={{ marginBottom: '1rem' }}>
                        <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={approvalConfirmed}
                            onChange={(e) => {
                              setApprovalConfirmed(e.target.checked);
                              setApprovalError(null);
                            }}
                            style={{ marginTop: '0.2rem' }}
                          />
                          <span style={{ fontSize: '0.78rem', color: 'var(--text-primary)', lineHeight: 1.45 }}>
                            I confirm that I have evaluated the proposed change, evidence, impact analysis, validation findings, and occurrence review, and authorize this change for inclusion in the Approved Change Report.
                          </span>
                        </label>
                      </div>

                      {/* Inline Approval Error Banner */}
                      {approvalError && (
                        <div
                          style={{
                            marginBottom: '1rem',
                            padding: '0.65rem 0.85rem',
                            background: 'rgba(239, 68, 68, 0.12)',
                            border: '1px solid rgba(239, 68, 68, 0.3)',
                            borderRadius: 'var(--radius-sm)',
                            color: '#fca5a5',
                            fontSize: '0.8rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.4rem',
                          }}
                        >
                          <AlertCircle size={15} color="var(--color-danger)" style={{ flexShrink: 0 }} />
                          <span>{approvalError}</span>
                        </div>
                      )}

                      {/* Action Button */}
                      <button
                        type="button"
                        onClick={() => handleAuthorizeApproval(prop, unresolvedOccs)}
                        className="btn btn-primary"
                        disabled={
                          submittingApproval ||
                          !approvalConfirmed ||
                          !approverName.trim() ||
                          !approverTitle.trim() ||
                          unresolvedOccs.length > 0
                        }
                        style={{ fontSize: '0.82rem', padding: '0.5rem 1rem' }}
                      >
                        <FileCheck2 size={15} />
                        {submittingApproval ? 'Authorizing & Compiling Report...' : 'Authorize & Generate Approved Change Report'}
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
