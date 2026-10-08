import React, { useState, useEffect } from 'react';
import {
  GitPullRequest,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  Layers,
  XCircle,
  AlertCircle,
  Play,
  FileText,
  Shield,
  FileCheck2,
  ChevronDown,
  ChevronUp,
  Check
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
  // CRITICAL SAFETY CONSTRAINT: Must start empty/null. No occurrence starts confirmed.
  const [occurrenceSelections, setOccurrenceSelections] = useState({});

  // 6D occurrence evidence expansion state (key: occurrence_id / occKey -> boolean)
  const [expandedEvidence, setExpandedEvidence] = useState({});
  const [showTechnicalDetails, setShowTechnicalDetails] = useState({});

  function toggleOccurrenceEvidence(key) {
    setExpandedEvidence((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  }

  function toggleTechnicalDetails(changeId) {
    setShowTechnicalDetails((prev) => ({
      ...prev,
      [changeId]: !prev[changeId],
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
  const candidateText =
    comparisonContext?.candidateText ||
    candidateItem?.content_item?.text ||
    candidateItem?.text ||
    null;
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
    candidateItem?.content_item?.content_id ||
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
        'Required comparison context (target section name and original text) is missing. Please select and compare content before formulating proposals.'
      );
      return;
    }

    setAnalyzingProposal(true);
    try {
      const payload = {
        decision_id: activeDecision.decision_id,
        document_id:
          targetSection?.document_id ||
          activeDecision?.document_id ||
          null,
        section: sectionName,
        original_text: targetText,
        candidate_text: candidateText || null,
        document_name: documentName || null,
        document_version: targetSection?.document_version || null,
      };

      const newProposal = await api.analyzeChangeProposal(payload);

      setProposals((prev) => {
        const exists = prev.some((p) => p.change_id === newProposal.change_id);
        return exists ? prev : [newProposal, ...prev];
      });

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

      // 3. Replace proposal state with returned backend state
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

  // Explicit Human Regulatory Approval Handler
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
        document_id:
          prop.document_id ||
          targetSection?.document_id ||
          null,
        document_name: prop.document_name || documentName || null,
        document_version: prop.document_version || targetSection?.document_version || null,
        audit_notes: `Authorized by ${fullApproverIdentity}. Occurrence review: ${occSummary}. Rationale: ${prop.rationale}`,
      };

      const report = await api.approveAndGenerateReport(payload);

      // On successful authorization, pass report to App.jsx to navigate to Approved Change Report
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
      {/* 1. Change Review Header */}
      <div className="card" style={{ maxWidth: '960px', margin: '0 auto 1.5rem auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.2rem 0.55rem', borderRadius: '9999px', background: 'rgba(13, 148, 136, 0.08)', color: 'var(--color-brand)', fontSize: '0.76rem', fontWeight: 600, marginBottom: '0.45rem' }}>
              <GitPullRequest size={13} /> Controlled Change Review & Governance
            </div>
            <h2 style={{ fontSize: '1.45rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 0.35rem 0' }}>
              Review Proposed Document Change
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
              <span>
                Document: <strong>{documentName || targetSection?.document_name || 'Draft Prescribing Information'}</strong>
              </span>
              <span>•</span>
              <span>
                Section: <strong>{sectionName || 'Target Section'}</strong>
              </span>
              {activeDecision?.decision && (
                <>
                  <span>•</span>
                  <span>
                    Action: <strong>{activeDecision.decision}</strong>
                  </span>
                </>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              className="status-pill"
              style={{
                background: proposals.some(p => p.status === 'APPROVED') ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                color: proposals.some(p => p.status === 'APPROVED') ? 'var(--color-success)' : 'var(--color-warning)',
                borderColor: proposals.some(p => p.status === 'APPROVED') ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)',
              }}
            >
              {proposals.some(p => p.status === 'APPROVED') ? 'Change Authorized' : 'Awaiting Review & Approval'}
            </span>
          </div>
        </div>
      </div>

      {/* REJECT DECISION PATH: Informational preservation notice */}
      {activeDecision?.decision === 'REJECT' && (
        <div
          className="card"
          style={{
            maxWidth: '960px',
            margin: '0 auto 1.5rem auto',
            padding: '1.5rem',
            background: 'rgba(239, 68, 68, 0.05)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.6rem' }}>
            <XCircle size={22} color="var(--color-danger)" />
            <h3 style={{ margin: 0, fontSize: '1.05rem', color: 'var(--text-primary)', fontWeight: 600 }}>
              Candidate Reference Standard Rejected — Original Content Preserved
            </h3>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.86rem', lineHeight: 1.5, margin: '0 0 1rem 0' }}>
            The regulatory reviewer has authorized a <strong>REJECT</strong> decision for this candidate standard. The candidate wording has been formally declined, and original draft content in <strong>{sectionName || 'the target section'}</strong> remains strictly unchanged.
          </p>
          <div style={{ background: '#ffffff', padding: '0.85rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            <strong>Governance Audit Notice:</strong> No controlled change proposal will be formulated, no impact analysis will be executed, and no change propagation will occur. The original source document text is 100% preserved.
          </div>
        </div>
      )}

      {/* REUSE / ADAPT Formulate Proposal Call-To-Action (if not yet formulated) */}
      {(activeDecision?.decision === 'REUSE' || activeDecision?.decision === 'ADAPT') && !existingActiveProposal && (
        <div
          className="card"
          style={{
            maxWidth: '960px',
            margin: '0 auto 1.5rem auto',
            padding: '1.5rem',
            background: 'linear-gradient(135deg, rgba(13, 148, 136, 0.06) 0%, #ffffff 100%)',
            border: '1.5px solid var(--color-brand-border)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div style={{ maxWidth: '600px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-brand)', fontWeight: 600, fontSize: '0.82rem', marginBottom: '0.3rem' }}>
                <Shield size={15} /> Formulate Change Proposal
              </div>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 0.35rem 0' }}>
                Ready to Formulate Controlled Change Proposal
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.84rem', margin: 0, lineHeight: 1.45 }}>
                Your authorized <strong>{activeDecision.decision}</strong> decision is ready. Click below to synthesize the proposed text, detect cross-section occurrences, and evaluate validation rules.
              </p>
            </div>

            <button
              type="button"
              onClick={handleFormulateProposal}
              className="btn btn-primary"
              disabled={analyzingProposal || !targetText || !sectionName}
              style={{ fontSize: '0.88rem', padding: '0.65rem 1.3rem', fontWeight: 600 }}
            >
              <Play size={15} /> {analyzingProposal ? 'Formulating Proposal...' : 'Formulate Change Proposal'}
            </button>
          </div>

          {analysisError && (
            <div style={{ marginTop: '1rem', padding: '0.7rem 0.9rem', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#b91c1c', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertCircle size={16} />
              <span>{analysisError}</span>
            </div>
          )}
        </div>
      )}

      {/* Main Proposals List */}
      {proposals.length === 0 && activeDecision?.decision !== 'REJECT' && (
        <div className="card" style={{ maxWidth: '960px', margin: '0 auto', textAlign: 'center', padding: '2.5rem 1.5rem' }}>
          <div className="empty-state">
            <GitPullRequest size={36} color="var(--color-brand)" style={{ opacity: 0.7, margin: '0 auto 0.75rem auto' }} />
            <h3 style={{ fontSize: '1.05rem', color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
              {loading ? 'Loading Change Proposals...' : 'No Active Change Proposals'}
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', maxWidth: '480px', margin: '0 auto' }}>
              Record a REUSE or ADAPT decision in Candidate Comparison to initiate and review controlled document change proposals.
            </p>
          </div>
        </div>
      )}

      {proposals.map((prop) => {
        const impact = impactResults[prop.change_id] || prop.impact_analysis;
        const relatedOccs = prop.related_occurrences || [];
        const isApproved = prop.status === 'APPROVED';

        // Occurrence counts
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

        // Validation evaluation
        const findings = impact?.findings || [];
        const failedFindings = findings.filter(f => !f.passed);
        const isValidationReady = failedFindings.length === 0 && unresolvedOccs.length === 0;

        return (
          <div key={prop.change_id} style={{ maxWidth: '960px', margin: '0 auto 2rem auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* 2. Proposed Change — PROMINENT */}
            <div className="card">
              <div className="card-header">
                <div>
                  <span className="card-title">
                    <FileText size={16} color="var(--color-brand)" /> Proposed Change
                  </span>
                  <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                    Review current wording versus the proposed modification for {prop.section}
                  </span>
                </div>
                <span className={`badge badge-${prop.decision_type.toLowerCase()}`}>
                  {prop.decision_type}
                </span>
              </div>

              {/* Side-by-Side: Current Content vs Proposed Content */}
              <div className="grid-2" style={{ gap: '1rem', marginBottom: '1.25rem' }}>
                <div style={{ background: '#ffffff', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Current Content (Draft)
                    </span>
                    <span className="badge" style={{ fontSize: '0.68rem', background: 'rgba(239, 68, 68, 0.08)', color: 'var(--color-danger)' }}>
                      To Be Replaced
                    </span>
                  </div>
                  <p style={{ fontSize: '0.86rem', color: 'var(--text-primary)', lineHeight: 1.5, margin: 0, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                    {prop.original_text}
                  </p>
                </div>

                <div style={{ background: '#ffffff', border: '1.5px solid rgba(13, 148, 136, 0.35)', borderRadius: 'var(--radius-md)', padding: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--color-brand)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Proposed Content (Adapted Standard)
                    </span>
                    <span className="badge" style={{ fontSize: '0.68rem', background: 'rgba(21, 128, 61, 0.1)', color: 'var(--color-success)' }}>
                      Proposed Replacement
                    </span>
                  </div>
                  <p style={{ fontSize: '0.86rem', color: 'var(--text-primary)', lineHeight: 1.5, margin: 0, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                    {prop.proposed_text}
                  </p>
                </div>
              </div>

              {/* 3. Why This Change? */}
              <div style={{ background: 'var(--bg-surface-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', padding: '0.85rem 1rem' }}>
                <span style={{ fontSize: '0.76rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '0.3rem' }}>
                  Why This Change?
                </span>
                <p style={{ fontSize: '0.86rem', color: 'var(--text-primary)', lineHeight: 1.5, margin: 0 }}>
                  {prop.rationale}
                </p>
                {prop.source_evidence && (
                  <div style={{ marginTop: '0.5rem', fontSize: '0.76rem', color: 'var(--color-brand)' }}>
                    <strong>Evidence Citation:</strong> {prop.source_evidence.source} ({prop.source_evidence.exact_quote})
                  </div>
                )}
              </div>
            </div>

            {/* 4. Occurrence Review — PROMINENT HUMAN ACTION */}
            <div className="card">
              <div className="card-header">
                <div>
                  <span className="card-title">
                    <Layers size={16} color="var(--color-brand)" /> Occurrences Requiring Review ({relatedOccs.length})
                  </span>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0.15rem 0 0 0' }}>
                    Review each detected occurrence and explicitly confirm or exclude it before final approval.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span className="badge" style={{ fontSize: '0.72rem', background: unresolvedOccs.length === 0 ? 'rgba(21, 128, 61, 0.15)' : 'rgba(245, 158, 11, 0.15)', color: unresolvedOccs.length === 0 ? 'var(--color-success)' : 'var(--color-warning)' }}>
                    {unresolvedOccs.length === 0 ? 'All Occurrences Resolved' : `${unresolvedOccs.length} Unresolved`}
                  </span>
                </div>
              </div>

              {/* Zero Autonomous Propagation Notice */}
              <div style={{ padding: '0.75rem 1rem', background: 'rgba(13, 148, 136, 0.05)', border: '1px solid var(--color-brand-border)', borderRadius: 'var(--radius-sm)', marginBottom: '1rem', fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                <strong style={{ color: 'var(--text-primary)' }}>Human Gate Enforced:</strong> No related occurrence is modified automatically. Confirm an occurrence to coordinate the change across documents, or exclude it to preserve original text.
              </div>

              {relatedOccs.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  {relatedOccs.map((occ, idx) => {
                    const occKey = occ.occurrence_id || `${prop.change_id}_occ_${idx}`;
                    const currentSelection = occurrenceSelections[occKey] || (occ.status !== 'PENDING' ? occ.status : undefined);

                    return (
                      <div
                        key={occKey}
                        style={{
                          background: '#ffffff',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-md)',
                          padding: '1rem',
                        }}
                      >
                        {/* Occurrence Location & Match Type */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.45rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                            <FileText size={15} color="var(--color-brand)" />
                            <strong style={{ fontSize: '0.88rem', color: 'var(--text-primary)' }}>
                              {occ.section}
                            </strong>
                            {occ.document_name && (
                              <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                                ({occ.document_name})
                              </span>
                            )}
                            {occ.location && (
                              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                • {occ.location}
                              </span>
                            )}
                          </div>

                          <span className="badge badge-section" style={{ fontSize: '0.7rem' }}>
                            {occ.match_type.replace('_', ' ').toUpperCase()} MATCH
                          </span>
                        </div>

                        {/* Occurrence Content */}
                        <p style={{ color: 'var(--text-primary)', fontSize: '0.82rem', margin: '0 0 0.6rem 0', lineHeight: 1.45, fontFamily: 'monospace', background: 'var(--bg-main)', padding: '0.5rem 0.75rem', borderRadius: 'var(--radius-sm)' }}>
                          {occ.current_text}
                        </p>

                        {/* 5. Occurrence Recommendation (Advisory) */}
                        {occ.recommended_action && (
                          <div
                            style={{
                              marginBottom: '0.75rem',
                              padding: '0.65rem 0.85rem',
                              background: 'var(--bg-surface-elevated)',
                              borderRadius: 'var(--radius-sm)',
                              border: `1px solid ${
                                occ.recommended_action === 'CONFIRM'
                                  ? 'rgba(21, 128, 61, 0.25)'
                                  : occ.recommended_action === 'EXCLUDE'
                                  ? 'rgba(239, 68, 68, 0.25)'
                                  : 'rgba(245, 158, 11, 0.25)'
                              }`,
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <span
                                  className="badge"
                                  style={{
                                    fontSize: '0.7rem',
                                    fontWeight: 700,
                                    background:
                                      occ.recommended_action === 'CONFIRM'
                                        ? 'rgba(21, 128, 61, 0.15)'
                                        : occ.recommended_action === 'EXCLUDE'
                                        ? 'rgba(239, 68, 68, 0.15)'
                                        : 'rgba(245, 158, 11, 0.15)',
                                    color:
                                      occ.recommended_action === 'CONFIRM'
                                        ? 'var(--color-success)'
                                        : occ.recommended_action === 'EXCLUDE'
                                        ? 'var(--color-danger)'
                                        : 'var(--color-warning)',
                                  }}
                                >
                                  System Recommendation: {occ.recommended_action.replace('_', ' ')}
                                </span>
                                {occ.recommendation_reason && (
                                  <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                                    {occ.recommendation_reason}
                                  </span>
                                )}
                              </div>

                              {(occ.recommended_action === 'CONFIRM' || occ.recommended_action === 'EXCLUDE') && (
                                <button
                                  type="button"
                                  onClick={() => handleToggleOccurrenceConfirmation(prop, occKey, occ.recommended_action === 'CONFIRM' ? 'CONFIRMED' : 'EXCLUDED')}
                                  className="btn btn-secondary"
                                  style={{ fontSize: '0.72rem', padding: '0.25rem 0.6rem' }}
                                >
                                  Apply Recommendation ({occ.recommended_action === 'CONFIRM' ? 'Confirm' : 'Exclude'})
                                </button>
                              )}
                            </div>
                          </div>
                        )}

                        {/* 6. Human Occurrence Decision Controls */}
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                            gap: '0.6rem',
                            borderTop: '1px solid var(--border-subtle)',
                            paddingTop: '0.65rem',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                              Your Decision:
                            </span>
                            <span
                              className="badge"
                              style={{
                                fontSize: '0.72rem',
                                fontWeight: 700,
                                background:
                                  currentSelection === 'CONFIRMED'
                                    ? 'rgba(21, 128, 61, 0.15)'
                                    : currentSelection === 'EXCLUDED'
                                    ? 'rgba(239, 68, 68, 0.15)'
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
                                ? '✓ CONFIRMED FOR CHANGE'
                                : currentSelection === 'EXCLUDED'
                                ? '✗ EXCLUDED / PRESERVED'
                                : '⏳ PENDING REVIEW'}
                            </span>
                          </div>

                          <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <button
                              type="button"
                              onClick={() => handleToggleOccurrenceConfirmation(prop, occKey, 'CONFIRMED')}
                              className={`btn ${currentSelection === 'CONFIRMED' ? 'btn-primary' : 'btn-secondary'}`}
                              style={{ fontSize: '0.76rem', padding: '0.35rem 0.75rem' }}
                            >
                              <Check size={13} /> Confirm for Change
                            </button>
                            <button
                              type="button"
                              onClick={() => handleToggleOccurrenceConfirmation(prop, occKey, 'EXCLUDED')}
                              className={`btn ${currentSelection === 'EXCLUDED' ? 'btn-danger' : 'btn-secondary'}`}
                              style={{
                                fontSize: '0.76rem',
                                padding: '0.35rem 0.75rem',
                                color: currentSelection === 'EXCLUDED' ? '#ffffff' : 'var(--color-danger)',
                                background: currentSelection === 'EXCLUDED' ? 'var(--color-danger)' : undefined,
                              }}
                            >
                              <XCircle size={13} /> Exclude / Preserve
                            </button>
                          </div>
                        </div>

                        {/* Optional 6D Evidence Expandable */}
                        {Boolean(occ.dimensional_scores && occ.dimensional_evidence) && (
                          <div style={{ marginTop: '0.6rem', borderTop: '1px dashed var(--border-subtle)', paddingTop: '0.5rem' }}>
                            <button
                              type="button"
                              onClick={() => toggleOccurrenceEvidence(occKey)}
                              style={{
                                background: 'transparent',
                                border: 'none',
                                color: 'var(--color-brand)',
                                fontSize: '0.72rem',
                                fontWeight: 600,
                                cursor: 'pointer',
                                padding: 0,
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.3rem',
                              }}
                            >
                              <span>{expandedEvidence[occKey] ? 'Hide 6D Evidence' : 'Inspect 6D Evidence'}</span>
                              {expandedEvidence[occKey] ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                            </button>

                            {expandedEvidence[occKey] && (
                              <div style={{ marginTop: '0.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.45rem' }}>
                                {OCCURRENCE_DIMENSIONS.map((dim) => {
                                  const evalData = occ.dimensional_evidence?.[dim.key];
                                  const rawScore = occ.dimensional_scores?.[dim.key] ?? evalData?.score;
                                  const scorePct = rawScore !== undefined && rawScore !== null ? Math.round(rawScore * 100) : null;
                                  const status = evalData?.status || 'NOT_APPLICABLE';
                                  const badgeStyle = getOccurrenceStatusStyle(status);

                                  return (
                                    <div key={dim.key} style={{ background: 'var(--bg-main)', padding: '0.45rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '0.7rem' }}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                                        <strong>{dim.label}</strong>
                                        <span className="badge" style={{ ...badgeStyle, fontSize: '0.62rem', padding: '0.1rem 0.3rem' }}>{status}</span>
                                      </div>
                                      {scorePct !== null && (
                                        <div style={{ height: '3px', background: 'var(--border-subtle)', borderRadius: '1.5px', overflow: 'hidden' }}>
                                          <div style={{ height: '100%', width: `${scorePct}%`, background: getScoreBarColor(rawScore) }} />
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ background: 'var(--bg-main)', padding: '0.85rem', borderRadius: 'var(--radius-sm)', fontSize: '0.82rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                  No cross-section related occurrences detected. The proposed modification remains isolated to <strong>{prop.section}</strong>.
                </div>
              )}
            </div>

            {/* 7. Impact Analysis */}
            {impact && (
              <div className="card">
                <div className="card-header">
                  <div>
                    <span className="card-title">
                      <AlertTriangle size={16} color={impact.risk_level === 'HIGH' ? 'var(--color-danger)' : 'var(--color-warning)'} /> Impact Analysis
                    </span>
                    <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                      Evaluated via deterministic regulatory rules across draft documents
                    </span>
                  </div>
                  <span
                    className="badge"
                    style={{
                      background: impact.risk_level === 'HIGH' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(21, 128, 61, 0.15)',
                      color: impact.risk_level === 'HIGH' ? 'var(--color-danger)' : 'var(--color-success)',
                      fontWeight: 700,
                    }}
                  >
                    {impact.risk_level} RISK
                  </span>
                </div>

                <div className="grid-3" style={{ gap: '0.75rem', marginBottom: '1rem' }}>
                  <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Affected Sections</span>
                    <strong style={{ fontSize: '1.15rem', color: 'var(--text-primary)' }}>
                      {impact.affected_sections_count || impact.affected_sections?.length || 1}
                    </strong>
                  </div>
                  <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Affected Documents</span>
                    <strong style={{ fontSize: '1.15rem', color: 'var(--text-primary)' }}>
                      {impact.affected_documents?.length || 1}
                    </strong>
                  </div>
                  <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Total Affected Items</span>
                    <strong style={{ fontSize: '1.15rem', color: 'var(--text-primary)' }}>
                      {impact.affected_content_count || 1}
                    </strong>
                  </div>
                </div>

                {/* Observed vs Potential Impacts */}
                <div className="grid-2" style={{ gap: '0.85rem' }}>
                  <div style={{ background: '#ffffff', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                    <strong style={{ fontSize: '0.78rem', color: 'var(--color-success)', display: 'block', marginBottom: '0.3rem' }}>
                      ✓ Verified Direct Impact:
                    </strong>
                    <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                      {(impact.observed_impacts || [`Direct text update in ${prop.section}`]).map((obs, i) => (
                        <li key={i}>{obs}</li>
                      ))}
                    </ul>
                  </div>

                  <div style={{ background: '#ffffff', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                    <strong style={{ fontSize: '0.78rem', color: 'var(--color-warning)', display: 'block', marginBottom: '0.3rem' }}>
                      ⚠ Potential Cross-Section Impact:
                    </strong>
                    <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                      {impact.potential_impacts && impact.potential_impacts.length > 0 ? (
                        impact.potential_impacts.map((pot, i) => <li key={i}>{pot}</li>)
                      ) : (
                        <li>No cross-section anomalies detected.</li>
                      )}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* 8. Validation Status */}
            <div className="card">
              <div className="card-header">
                <div>
                  <span className="card-title">
                    <ShieldCheck size={16} color="var(--color-brand)" /> Validation Status
                  </span>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0.15rem 0 0 0' }}>
                    Deterministic regulatory validation checks (REG-VAL-001 through REG-VAL-006)
                  </p>
                </div>
                <span
                  className="badge"
                  style={{
                    background: isValidationReady ? 'rgba(21, 128, 61, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                    color: isValidationReady ? 'var(--color-success)' : 'var(--color-warning)',
                    fontWeight: 700,
                  }}
                >
                  {isValidationReady ? 'READY FOR APPROVAL' : 'ACTION REQUIRED'}
                </span>
              </div>

              {/* Status Readiness Summary */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem' }}>
                  {unresolvedOccs.length === 0 ? (
                    <CheckCircle2 size={16} color="var(--color-success)" />
                  ) : (
                    <AlertCircle size={16} color="var(--color-warning)" />
                  )}
                  <span>
                    <strong>Occurrence Resolutions:</strong>{' '}
                    {unresolvedOccs.length === 0
                      ? `All ${relatedOccs.length} occurrence(s) resolved (${confirmedOccs.length} confirmed, ${excludedOccs.length} excluded).`
                      : `${unresolvedOccs.length} occurrence(s) pending your decision.`}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem' }}>
                  {failedFindings.length === 0 ? (
                    <CheckCircle2 size={16} color="var(--color-success)" />
                  ) : (
                    <AlertCircle size={16} color="var(--color-danger)" />
                  )}
                  <span>
                    <strong>Regulatory Rules:</strong>{' '}
                    {failedFindings.length === 0
                      ? 'All validation rules passed.'
                      : `${failedFindings.length} validation rule warning(s) detected.`}
                  </span>
                </div>
              </div>

              {/* Validation Rules Findings Chips */}
              {findings.length > 0 && (
                <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
                  {findings.map((f, i) => (
                    <span
                      key={i}
                      className="badge"
                      style={{
                        background: f.passed ? 'rgba(21, 128, 61, 0.08)' : 'rgba(239, 68, 68, 0.08)',
                        color: f.passed ? 'var(--color-success)' : 'var(--color-danger)',
                        border: f.passed ? '1px solid rgba(21, 128, 61, 0.25)' : '1px solid rgba(239, 68, 68, 0.25)',
                        fontSize: '0.72rem',
                      }}
                    >
                      {f.passed ? '✓' : '✗'} {f.rule_id}: {f.message}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* 9. Final Approval Station — PROMINENT */}
            <div className="card" style={{ border: '2px solid var(--color-brand)' }}>
              <div className="card-header">
                <div>
                  <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <FileCheck2 size={18} color="var(--color-brand)" /> Final Approval
                  </span>
                  <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0 0' }}>
                    Final approval is a human decision. All required occurrence decisions and validation checks must be complete.
                  </p>
                </div>
                <span className="status-pill">
                  Human Authority Gate
                </span>
              </div>

              {isApproved ? (
                <div style={{ color: 'var(--color-success)', fontSize: '0.86rem', display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '1rem', background: 'rgba(21, 128, 61, 0.08)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(21, 128, 61, 0.25)' }}>
                  <CheckCircle2 size={18} />
                  <span>This change proposal has been approved and recorded in the Approved Change Report.</span>
                </div>
              ) : (
                <div>
                  {/* Blocking banner if occurrences unresolved */}
                  {unresolvedOccs.length > 0 && (
                    <div style={{ marginBottom: '1.25rem', padding: '0.75rem 1rem', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.35)', borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                      <AlertCircle size={18} color="var(--color-warning)" style={{ flexShrink: 0 }} />
                      <div style={{ fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                        <strong>Approval Blocked:</strong> {unresolvedOccs.length} occurrence(s) above require your explicit decision (Confirm or Exclude) before you can authorize this change.
                      </div>
                    </div>
                  )}

                  {/* Approver Details Inputs */}
                  <div className="grid-2" style={{ gap: '0.85rem', marginBottom: '1.25rem' }}>
                    <div>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.3rem' }}>
                        Approver Full Name *
                      </label>
                      <input
                        type="text"
                        className="input-text"
                        placeholder="e.g. Dr. Jane Doe"
                        value={approverName}
                        onChange={(e) => {
                          setApproverName(e.target.value);
                          setApprovalError(null);
                        }}
                        style={{ width: '100%' }}
                      />
                    </div>

                    <div>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.3rem' }}>
                        Regulatory Authority Title / Role *
                      </label>
                      <input
                        type="text"
                        className="input-text"
                        placeholder="e.g. Senior Director, Regulatory Affairs"
                        value={approverTitle}
                        onChange={(e) => {
                          setApproverTitle(e.target.value);
                          setApprovalError(null);
                        }}
                        style={{ width: '100%' }}
                      />
                    </div>
                  </div>

                  {/* Confirmation Checkbox */}
                  <div style={{ marginBottom: '1.25rem', background: 'var(--bg-surface-elevated)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                    <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={approvalConfirmed}
                        onChange={(e) => {
                          setApprovalConfirmed(e.target.checked);
                          setApprovalError(null);
                        }}
                        style={{ marginTop: '0.2rem' }}
                      />
                      <span style={{ fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.45 }}>
                        I confirm that I have evaluated the proposed change, occurrence decisions, impact analysis, and validation findings, and authorize this change for inclusion in the Approved Change Report.
                      </span>
                    </label>
                  </div>

                  {/* Approval Error Banner */}
                  {approvalError && (
                    <div style={{ marginBottom: '1rem', padding: '0.7rem 0.9rem', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#b91c1c', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <AlertCircle size={16} />
                      <span>{approvalError}</span>
                    </div>
                  )}

                  {/* Approval Button */}
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
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
                      style={{ fontSize: '0.9rem', padding: '0.65rem 1.4rem', fontWeight: 600 }}
                    >
                      <FileCheck2 size={16} />
                      {submittingApproval ? 'Authorizing & Compiling Report...' : 'Authorize & Generate Approved Change Report'}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Technical Details (Secondary & Expandable) */}
            <div className="card" style={{ background: 'var(--bg-surface)' }}>
              <div
                onClick={() => toggleTechnicalDetails(prop.change_id)}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  cursor: 'pointer',
                  userSelect: 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  {showTechnicalDetails[prop.change_id] ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                  <span>View Technical Details & Audit Metadata</span>
                </div>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Change ID: <code>{prop.change_id}</code>
                </span>
              </div>

              {showTechnicalDetails[prop.change_id] && (
                <div style={{ marginTop: '0.85rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)', fontSize: '0.76rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  <div>Decision ID: <code>{prop.decision_id || 'N/A'}</code></div>
                  <div>Target Content ID: <code>{targetContentId || 'N/A'}</code></div>
                  <div>Candidate Content ID: <code>{candidateId || 'N/A'}</code></div>
                  <div>Detection Architecture: 4-Layer Hybrid (Exact, Normalized, Structured, Semantic)</div>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
