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
  Shield
} from 'lucide-react';
import { api } from '../services/api';

export default function ChangeReview({ activeDecision, comparisonContext }) {
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [impactResults, setImpactResults] = useState({});
  const [analyzingProposal, setAnalyzingProposal] = useState(false);
  const [analysisError, setAnalysisError] = useState(null);

  // Reviewer confirmation state per related occurrence (key: occurrence_id -> 'CONFIRMED' | 'EXCLUDED')
  // CRITICAL SAFETY CONSTRAINT: Must start empty/null (NOT CONFIRMED). No occurrence starts confirmed.
  const [occurrenceSelections, setOccurrenceSelections] = useState({});

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

  // Handle human confirmation toggle per related occurrence (frontend review state only)
  function handleToggleOccurrenceConfirmation(occKey, choice) {
    setOccurrenceSelections((prev) => ({
      ...prev,
      [occKey]: choice,
    }));
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
          <p>Impact analysis, multi-layer occurrence review, and explicit human confirmation before propagation</p>
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
              <span>Controlled change proposal <code>{existingActiveProposal.change_id}</code> is active for this decision. Review impact assessment and related occurrences below.</span>
            </div>
          )}
        </div>
      )}

      {/* 2. PROPOSALS LIST & IMPACT / OCCURRENCE REVIEW */}
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
                    <span className="status-pill">
                      {prop.status || 'PROPOSED'}
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
                          Target section + {prop.related_occurrences?.length || 0} occurrences
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
                <div style={{ background: 'var(--bg-surface-elevated)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
                    <span style={{ fontSize: '0.84rem', fontWeight: '600', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Layers size={15} color="var(--color-brand)" /> Related Occurrence Review ({prop.related_occurrences?.length || 0})
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
                  {prop.related_occurrences && prop.related_occurrences.length > 0 ? (
                    <div>
                      {prop.related_occurrences.map((occ, idx) => {
                        const occKey = occ.occurrence_id || `${prop.change_id}_occ_${idx}`;
                        const currentSelection = occurrenceSelections[occKey]; // undefined | 'CONFIRMED' | 'EXCLUDED'

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
                              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                <strong>Matching Basis:</strong> {occ.reason}
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
                                    onChange={() => handleToggleOccurrenceConfirmation(occKey, 'CONFIRMED')}
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
                                    onChange={() => handleToggleOccurrenceConfirmation(occKey, 'EXCLUDED')}
                                  />
                                  <span style={{ color: currentSelection === 'EXCLUDED' ? 'var(--color-danger)' : 'var(--text-secondary)' }}>
                                    Exclude / preserve
                                  </span>
                                </label>
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
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
