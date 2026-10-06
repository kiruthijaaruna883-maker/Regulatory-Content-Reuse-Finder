import React, { useState } from 'react';
import {
  CheckCircle2,
  Sliders,
  XCircle,
  Send,
  ArrowRight,
  ShieldAlert,
  AlertCircle,
  FileText,
  ExternalLink,
  GitCompare
} from 'lucide-react';
import { api } from '../services/api';

const DIMENSIONS = [
  { key: 'meaning', name: '1. Meaning' },
  { key: 'template', name: '2. Template' },
  { key: 'context', name: '3. Context' },
  { key: 'structure', name: '4. Structure' },
  { key: 'format', name: '5. Format' },
  { key: 'key_information', name: '6. Key Information' },
];

export default function DecisionPanel({ comparisonData, onDecisionRecorded }) {
  // Explicit Human Choice: MUST be null initially (no default preselection)
  const [selectedDecision, setSelectedDecision] = useState(null);

  // Reviewer Form State: Empty by default, no prefilled fake regulatory reasoning
  const [reviewerName, setReviewerName] = useState('');
  const [reviewerNotes, setReviewerNotes] = useState('');
  const [adaptationInstructions, setAdaptationInstructions] = useState('');

  // Status & Validation State
  const [submitting, setSubmitting] = useState(false);
  const [validationError, setValidationError] = useState(null);
  const [submitError, setSubmitError] = useState(null);
  const [recordedDecision, setRecordedDecision] = useState(null);

  // Extract Comparison Context
  const targetText = comparisonData?.targetText || comparisonData?.targetSection?.text || null;
  const candidateText = comparisonData?.candidateText || comparisonData?.candidateItem?.text || null;
  const targetSection = comparisonData?.targetSection || null;
  const candidateItem = comparisonData?.candidateItem || null;
  const differences = comparisonData?.differences || [];
  const analysisResult = comparisonData?.analysisResult || null;

  // Extract Provenance Identifiers
  const targetContentId =
    targetSection?.content_id ||
    analysisResult?.target_content_id ||
    analysisResult?.candidates?.[0]?.evidence?.[0]?.target_facts?.target_content_id ||
    null;

  const candidateId =
    candidateItem?.content_id ||
    analysisResult?.candidates?.[0]?.content_item?.content_id ||
    analysisResult?.candidates?.[0]?.candidate_id ||
    null;

  const primaryCandidate = analysisResult?.candidates?.[0] || null;
  const matchResult = primaryCandidate?.multi_dimensional_match || null;
  const falseMatchWarning =
    primaryCandidate?.false_match_warning ||
    candidateItem?.false_match_warning ||
    (analysisResult?.false_matches_detected > 0
      ? 'Critical regulatory discrepancy detected between target and candidate reference.'
      : null);

  // Advisory Recommendation Signals (Phase 6G.2 & 6G.3)
  const recommendedDecision =
    primaryCandidate?.recommended_decision ||
    candidateItem?.recommended_decision ||
    null;
  const recommendationReason =
    primaryCandidate?.recommendation_reason ||
    candidateItem?.recommendation_reason ||
    null;
  const recommendationConfidence =
    primaryCandidate?.recommendation_confidence ??
    candidateItem?.recommendation_confidence ??
    null;
  const proposedAdaptedText =
    primaryCandidate?.proposed_adapted_text ||
    candidateItem?.proposed_adapted_text ||
    null;
  const adaptationRationale =
    primaryCandidate?.adaptation_rationale ||
    candidateItem?.adaptation_rationale ||
    null;

  const primaryEvidence = primaryCandidate?.evidence?.[0] || null;
  const observedFacts = primaryEvidence?.observed_from_source || null;
  const targetFacts = primaryEvidence?.target_facts || null;

  // Helper for Dimension Status Styling
  function getStatusStyle(status) {
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
      color: 'var(--text-muted)',
      border: '1px solid var(--border-subtle)',
    };
  }

  // Handle Form Submission
  async function handleSubmitDecision() {
    setValidationError(null);
    setSubmitError(null);

    // 1. Validate Decision Selection
    if (!selectedDecision) {
      setValidationError('An explicit regulatory action (Reuse, Adapt, or Reject) must be selected.');
      return;
    }

    // 2. Validate Provenance Context
    if (!targetContentId || !candidateId) {
      setValidationError(
        'Valid target and candidate content identifiers are required to authorize a decision. Return to Document Review and Candidate Comparison to establish full audit traceability.'
      );
      return;
    }

    // 3. Validate Reviewer Name
    if (!reviewerName.trim()) {
      setValidationError('Reviewer name and regulatory authority title are required.');
      return;
    }

    // 4. Validate Reviewer Rationale
    if (!reviewerNotes.trim()) {
      setValidationError(
        'Professional rationale and clinical justification are mandatory for all regulatory decisions.'
      );
      return;
    }

    // 5. Validate Adaptation Instructions when ADAPT is selected
    if (selectedDecision === 'ADAPT' && !adaptationInstructions.trim()) {
      setValidationError('Specific adaptation instructions are mandatory when selecting ADAPT.');
      return;
    }

    setSubmitting(true);
    try {
      const decisionPayload = {
        target_content_id: targetContentId,
        candidate_id: candidateId,
        decision: selectedDecision,
        reviewer_name: reviewerName.trim(),
        reviewer_notes: reviewerNotes.trim(),
        adaptation_instructions: selectedDecision === 'ADAPT' ? adaptationInstructions.trim() : null,
      };

      const result = await api.recordDecision(decisionPayload);
      setRecordedDecision(result);
    } catch (err) {
      setSubmitError(err.message || 'Failed to record regulatory decision.');
    } finally {
      setSubmitting(false);
    }
  }

  // Graceful Empty State when entered without comparison context
  if (!comparisonData || (!targetText && !candidateText && !candidateItem)) {
    return (
      <div>
        <div className="screen-header">
          <div>
            <h2>Human Decision Panel</h2>
            <p>Regulatory professional authority: Evaluate evidence and mandate Reuse, Adapt, or Reject</p>
          </div>
        </div>

        <div className="card" style={{ maxWidth: '800px', margin: '2rem auto', textAlign: 'center', padding: '2.5rem 1.5rem' }}>
          <ShieldAlert size={36} color="var(--color-warning)" style={{ marginBottom: '0.75rem', opacity: 0.8 }} />
          <h3 style={{ fontSize: '1.1rem', color: '#fff', marginBottom: '0.5rem' }}>
            No Active Comparison Context
          </h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', maxWidth: '540px', margin: '0 auto', lineHeight: 1.5 }}>
            A regulatory decision requires an active comparison between your internal draft document and an approved candidate reference standard. Please review a document and evaluate candidates in the Candidate Comparison workspace before authorizing a decision.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Screen Header */}
      <div className="screen-header">
        <div>
          <h2>Human Decision Panel</h2>
          <p>
            Regulatory Professional Authority: Review multi-dimensional comparison evidence and mandate Reuse, Adapt, or Reject
          </p>
        </div>
      </div>

      {/* Provenance Incomplete Notice if IDs are genuinely missing */}
      {(!targetContentId || !candidateId) && (
        <div
          style={{
            maxWidth: '900px',
            margin: '0 auto 1.5rem auto',
            padding: '0.85rem 1.1rem',
            background: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.35)',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '0.75rem',
          }}
        >
          <AlertCircle size={18} color="var(--color-warning)" style={{ flexShrink: 0, marginTop: '2px' }} />
          <div>
            <strong style={{ color: '#fbbf24', fontSize: '0.88rem', display: 'block', marginBottom: '0.2rem' }}>
              Provenance Incomplete
            </strong>
            <p style={{ color: 'var(--text-primary)', fontSize: '0.82rem', margin: 0, lineHeight: 1.45 }}>
              Required regulatory content identifiers are incomplete in this session (Target ID: {targetContentId || 'Missing'}, Candidate ID: {candidateId || 'Missing'}). Ensure both documents are ingested and selected in Candidate Comparison before authorizing a decision.
            </p>
          </div>
        </div>
      )}

      {/* 1. Comparison Evidence Station */}
      <div className="card" style={{ maxWidth: '900px', margin: '0 auto 1.5rem auto' }}>
        <div className="card-header">
          <span className="card-title">
            <FileText size={16} color="var(--color-brand)" /> Regulatory Comparison Evidence & Traceability
          </span>
          <span className="status-pill">
            Evidence for Review
          </span>
        </div>

        {/* Provenance Row */}
        <div className="grid-2" style={{ gap: '1rem', marginBottom: '1rem', fontSize: '0.78rem' }}>
          {/* Target Provenance */}
          <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ color: 'var(--color-brand)', fontWeight: '600', display: 'block', marginBottom: '0.3rem' }}>
              Target Document Provenance
            </span>
            <div style={{ color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
              <span>Document: <strong>{targetFacts?.target_document_name || targetSection?.document_name || 'Draft Document'}</strong></span>
              <span>Doc ID: <code>{targetFacts?.target_document_id || targetSection?.document_id || 'Not assigned'}</code></span>
              <span>Content ID: <code>{targetContentId || 'Not assigned'}</code></span>
              <span>Section: <strong>{targetFacts?.target_section || targetSection?.section || 'Not assigned'}</strong></span>
              {targetSection?.subsection && <span>Subsection: {targetSection.subsection}</span>}
              {targetSection?.location && <span>Location: {targetSection.location}</span>}
              {targetSection?.page !== undefined && targetSection?.page !== null && <span>Page: {targetSection.page}</span>}
            </div>
          </div>

          {/* Candidate Provenance */}
          <div style={{ background: 'var(--bg-main)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ color: 'var(--color-dailymed)', fontWeight: '600', display: 'block', marginBottom: '0.3rem' }}>
              Candidate Reference Provenance
            </span>
            <div style={{ color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
              <span>Source: <strong>{observedFacts?.source || candidateItem?.source || 'External Authority'}</strong></span>
              <span>Document: <strong>{observedFacts?.document_name || candidateItem?.document_name || 'Regulatory Precedent'}</strong></span>
              <span>Source ID: <code>{observedFacts?.source_identifier || candidateItem?.source_identifier || 'Not assigned'}</code></span>
              <span>Content ID: <code>{candidateId || 'Not assigned'}</code></span>
              <span>Section: <strong>{observedFacts?.section || candidateItem?.section || 'Not assigned'}</strong></span>
              {candidateItem?.metadata?.cross_sources && candidateItem.metadata.cross_sources.length > 1 && (
                <span>Corroboration: <strong>{candidateItem.metadata.cross_sources.join(', ')}</strong></span>
              )}
              {candidateItem?.source_url && (
                <a
                  href={candidateItem.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="trace-link"
                  style={{ marginTop: '0.25rem', fontSize: '0.75rem' }}
                >
                  <ExternalLink size={11} /> Trace Official Authority Record
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Side-by-Side Content Review */}
        <div className="grid-2" style={{ gap: '1rem', marginBottom: '1.25rem' }}>
          <div>
            <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)', fontWeight: '600', display: 'block', marginBottom: '0.35rem' }}>
              Target Current Draft Content:
            </span>
            <div
              style={{
                background: 'var(--bg-main)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.75rem',
                fontSize: '0.82rem',
                color: 'var(--text-primary)',
                fontFamily: 'monospace',
                maxHeight: '130px',
                overflowY: 'auto',
                lineHeight: 1.45,
              }}
            >
              {targetText || 'No target text available in comparison context.'}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)', fontWeight: '600', display: 'block', marginBottom: '0.35rem' }}>
              Candidate Regulatory Reference:
            </span>
            <div
              style={{
                background: 'var(--bg-main)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.75rem',
                fontSize: '0.82rem',
                color: 'var(--text-primary)',
                fontFamily: 'monospace',
                maxHeight: '130px',
                overflowY: 'auto',
                lineHeight: 1.45,
              }}
            >
              {candidateText || 'No candidate text available in comparison context.'}
            </div>
          </div>
        </div>

        {/* False Match Warning Banner */}
        {falseMatchWarning && (
          <div
            style={{
              marginBottom: '1.25rem',
              padding: '0.85rem 1rem',
              background: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.35)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.75rem',
            }}
          >
            <ShieldAlert size={20} color="var(--color-danger)" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <strong style={{ color: '#fca5a5', fontSize: '0.86rem', display: 'block', marginBottom: '0.2rem' }}>
                False Match Discrepancy Flagged
              </strong>
              <p style={{ color: 'var(--text-primary)', fontSize: '0.81rem', margin: 0, lineHeight: 1.45 }}>
                {falseMatchWarning}
              </p>
            </div>
          </div>
        )}

        {/* Six-Dimensional Comparison Summary */}
        {matchResult && (
          <div style={{ marginBottom: '1.25rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
              <span style={{ fontSize: '0.84rem', color: '#fff', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <GitCompare size={14} color="var(--color-brand)" /> Six-Dimensional Regulatory Alignment Summary
              </span>
              {matchResult.overall_alignment_summary && (
                <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                  Multi-Dimensional Synthesis
                </span>
              )}
            </div>

            {matchResult.overall_alignment_summary && (
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', background: 'var(--bg-main)', padding: '0.65rem 0.85rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', marginBottom: '0.75rem', lineHeight: 1.45 }}>
                {matchResult.overall_alignment_summary}
              </p>
            )}

            <div className="grid-3" style={{ gap: '0.6rem' }}>
              {DIMENSIONS.map((dim) => {
                const evalData = matchResult[dim.key];
                const status = evalData?.status || 'NOT_APPLICABLE';

                return (
                  <div
                    key={dim.key}
                    style={{
                      background: 'var(--bg-main)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '0.65rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.25rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '0.78rem', color: '#fff' }}>{dim.name}</strong>
                      <span className="badge" style={getStatusStyle(status)}>
                        {status}
                      </span>
                    </div>

                    {evalData?.score !== undefined && evalData?.score !== null && (
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                        Alignment: {Math.round(evalData.score * 100)}%
                      </span>
                    )}

                    {evalData?.details && (
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', lineHeight: 1.35 }}>
                        {evalData.details}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Detected Differences Summary */}
        {differences.length > 0 && (
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
            <span style={{ fontSize: '0.82rem', color: '#fff', fontWeight: '600', display: 'block', marginBottom: '0.5rem' }}>
              Detected Distinctions for Review ({differences.length}):
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '160px', overflowY: 'auto' }}>
              {differences.map((diff, idx) => (
                <div
                  key={diff.difference_id || idx}
                  style={{
                    background: 'var(--bg-main)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '0.55rem 0.75rem',
                    fontSize: '0.76rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <strong style={{ color: '#fff', textTransform: 'capitalize' }}>
                        {(diff.attribute || diff.aspect || 'attribute').replace('_', ' ')} distinction
                      </strong>
                      {diff.source_dimension && (
                        <span className="badge badge-section" style={{ fontSize: '0.68rem' }}>
                          {diff.source_dimension.replace('_', ' ')}
                        </span>
                      )}
                    </div>
                    {diff.regulatory_impact && (
                      <span
                        className="badge"
                        style={{
                          fontSize: '0.68rem',
                          background: diff.regulatory_impact === 'MAJOR' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.15)',
                          color: diff.regulatory_impact === 'MAJOR' ? 'var(--color-danger)' : 'var(--color-warning)',
                        }}
                      >
                        {diff.regulatory_impact} IMPACT
                      </span>
                    )}
                  </div>
                  <p style={{ color: 'var(--text-secondary)', margin: '0 0 0.25rem 0', lineHeight: 1.35 }}>
                    {diff.explanation}
                  </p>
                  {(diff.current_value || diff.candidate_value) && (
                    <div style={{ display: 'flex', gap: '1rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {diff.current_value && <span>Draft: <code style={{ color: '#f87171' }}>{diff.current_value}</code></span>}
                      {diff.candidate_value && <span>Reference: <code style={{ color: '#34d399' }}>{diff.candidate_value}</code></span>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Human Authority Notice */}
        <div style={{ marginTop: '1rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem', fontSize: '0.74rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <ShieldAlert size={13} color="var(--color-brand)" style={{ flexShrink: 0 }} />
          <span>
            Human Regulatory Authority Gate: AI provides comparison evidence across six dimensions; the human regulatory specialist retains exclusive legal authority for the final Reuse, Adapt, or Reject decision.
          </span>
        </div>
      </div>

      {/* 2. Regulatory Governance Decision Station */}
      <div className="card" style={{ maxWidth: '900px', margin: '0 auto' }}>
        <div className="card-header">
          <span className="card-title">
            <ShieldAlert size={16} color="var(--color-brand)" /> Regulatory Governance Decision Station
          </span>
          <span className="status-pill">
            Sole Human Authorization
          </span>
        </div>

        {/* Advisory Recommendation Banner (Phase 6G.2) */}
        {recommendedDecision && (
          <div
            style={{
              marginBottom: '1.25rem',
              padding: '0.9rem 1.15rem',
              background:
                recommendedDecision === 'REUSE'
                  ? 'rgba(21, 128, 61, 0.08)'
                  : recommendedDecision === 'ADAPT'
                  ? 'rgba(180, 83, 9, 0.08)'
                  : 'rgba(185, 28, 28, 0.08)',
              border: `1.5px solid ${
                recommendedDecision === 'REUSE'
                  ? 'rgba(21, 128, 61, 0.35)'
                  : recommendedDecision === 'ADAPT'
                  ? 'rgba(180, 83, 9, 0.35)'
                  : 'rgba(185, 28, 28, 0.35)'
              }`,
              borderRadius: 'var(--radius-md)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem', flexWrap: 'wrap', gap: '0.4rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span
                  className="badge"
                  style={{
                    fontSize: '0.76rem',
                    fontWeight: '700',
                    padding: '0.2rem 0.55rem',
                    background:
                      recommendedDecision === 'REUSE'
                        ? 'rgba(21, 128, 61, 0.18)'
                        : recommendedDecision === 'ADAPT'
                        ? 'rgba(180, 83, 9, 0.18)'
                        : 'rgba(185, 28, 28, 0.18)',
                    color:
                      recommendedDecision === 'REUSE'
                        ? 'var(--color-success)'
                        : recommendedDecision === 'ADAPT'
                        ? 'var(--color-warning)'
                        : 'var(--color-danger)',
                  }}
                >
                  {recommendedDecision}
                </span>
                <strong style={{ fontSize: '0.88rem', color: 'var(--text-primary)' }}>
                  ADVISORY RECOMMENDATION — HUMAN GOVERNANCE REQUIRED
                </strong>
              </div>
              {recommendationConfidence !== null && recommendationConfidence !== undefined && (
                <span
                  style={{
                    fontSize: '0.74rem',
                    color: 'var(--text-secondary)',
                    fontWeight: '600',
                    background: 'var(--bg-surface)',
                    padding: '0.2rem 0.5rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  Advisory Confidence: {Math.round(recommendationConfidence * 100)}%
                </span>
              )}
            </div>

            {recommendationReason && (
              <p style={{ fontSize: '0.82rem', color: 'var(--text-primary)', margin: '0.3rem 0', lineHeight: 1.45 }}>
                {recommendationReason}
              </p>
            )}

            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>
              Advisory output only. You must evaluate clinical alignment independently and deliberately select your decision below. You may adopt or override this recommendation.
            </span>
          </div>
        )}

        {/* Decision Option Buttons: Explicit Human Selection */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.6rem', fontWeight: '500' }}>
            Select Controlled Action * <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>(No default preselection; deliberate human choice required)</span>
          </label>
          <div className="grid-3">
            <button
              type="button"
              onClick={() => {
                setSelectedDecision('REUSE');
                setValidationError(null);
              }}
              className={`btn ${selectedDecision === 'REUSE' ? 'btn-reuse' : 'btn-secondary'}`}
              style={{
                flexDirection: 'column',
                padding: '1.1rem',
                borderWidth: selectedDecision === 'REUSE' ? '2px' : '1px',
                borderColor: selectedDecision === 'REUSE' ? 'var(--color-success)' : 'var(--border-subtle)',
                position: 'relative',
              }}
            >
              {recommendedDecision === 'REUSE' && (
                <span
                  className="badge"
                  style={{
                    fontSize: '0.68rem',
                    fontWeight: '700',
                    background: 'rgba(21, 128, 61, 0.18)',
                    color: 'var(--color-success)',
                    border: '1px solid rgba(21, 128, 61, 0.35)',
                    marginBottom: '0.35rem',
                  }}
                >
                  System Recommended
                </span>
              )}
              <CheckCircle2 size={24} color={selectedDecision === 'REUSE' ? 'var(--color-success)' : 'var(--text-muted)'} />
              <strong style={{ marginTop: '0.4rem', fontSize: '1rem' }}>REUSE</strong>
              <span style={{ fontSize: '0.72rem', opacity: 0.85, textAlign: 'center', marginTop: '0.2rem' }}>
                Direct adoption of validated external regulatory standard
              </span>
            </button>

            <button
              type="button"
              onClick={() => {
                setSelectedDecision('ADAPT');
                setValidationError(null);
              }}
              className={`btn ${selectedDecision === 'ADAPT' ? 'btn-adapt' : 'btn-secondary'}`}
              style={{
                flexDirection: 'column',
                padding: '1.1rem',
                borderWidth: selectedDecision === 'ADAPT' ? '2px' : '1px',
                borderColor: selectedDecision === 'ADAPT' ? 'var(--color-warning)' : 'var(--border-subtle)',
                position: 'relative',
              }}
            >
              {recommendedDecision === 'ADAPT' && (
                <span
                  className="badge"
                  style={{
                    fontSize: '0.68rem',
                    fontWeight: '700',
                    background: 'rgba(180, 83, 9, 0.18)',
                    color: 'var(--color-warning)',
                    border: '1px solid rgba(180, 83, 9, 0.35)',
                    marginBottom: '0.35rem',
                  }}
                >
                  System Recommended
                </span>
              )}
              <Sliders size={24} color={selectedDecision === 'ADAPT' ? 'var(--color-warning)' : 'var(--text-muted)'} />
              <strong style={{ marginTop: '0.4rem', fontSize: '1rem' }}>ADAPT</strong>
              <span style={{ fontSize: '0.72rem', opacity: 0.85, textAlign: 'center', marginTop: '0.2rem' }}>
                Modify candidate with product-specific clinical adaptations
              </span>
            </button>

            <button
              type="button"
              onClick={() => {
                setSelectedDecision('REJECT');
                setValidationError(null);
              }}
              className={`btn ${selectedDecision === 'REJECT' ? 'btn-reject' : 'btn-secondary'}`}
              style={{
                flexDirection: 'column',
                padding: '1.1rem',
                borderWidth: selectedDecision === 'REJECT' ? '2px' : '1px',
                borderColor: selectedDecision === 'REJECT' ? 'var(--color-danger)' : 'var(--border-subtle)',
                position: 'relative',
              }}
            >
              {recommendedDecision === 'REJECT' && (
                <span
                  className="badge"
                  style={{
                    fontSize: '0.68rem',
                    fontWeight: '700',
                    background: 'rgba(185, 28, 28, 0.18)',
                    color: 'var(--color-danger)',
                    border: '1px solid rgba(185, 28, 28, 0.35)',
                    marginBottom: '0.35rem',
                  }}
                >
                  System Recommended
                </span>
              )}
              <XCircle size={24} color={selectedDecision === 'REJECT' ? 'var(--color-danger)' : 'var(--text-muted)'} />
              <strong style={{ marginTop: '0.4rem', fontSize: '1rem' }}>REJECT</strong>
              <span style={{ fontSize: '0.72rem', opacity: 0.85, textAlign: 'center', marginTop: '0.2rem' }}>
                Decline candidate; retain current internal document wording
              </span>
            </button>
          </div>
        </div>

        {/* Adaptation Guidance (Mandatory when ADAPT selected) */}
        {selectedDecision === 'ADAPT' && (
          <div style={{ marginBottom: '1.25rem', background: 'rgba(245, 158, 11, 0.08)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
            {/* Phase 6G.3: Advisory Proposed Wording Box */}
            {proposedAdaptedText && (
              <div
                style={{
                  marginBottom: '1rem',
                  padding: '0.85rem 1rem',
                  background: 'var(--bg-surface)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid rgba(245, 158, 11, 0.35)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.45rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div>
                    <strong style={{ fontSize: '0.82rem', color: '#fbbf24', display: 'block' }}>
                      System Proposed Wording (Advisory Proposal)
                    </strong>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      Advisory starting draft grounded in 6D comparison evidence. You may adopt, edit, or replace this wording.
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setAdaptationInstructions(proposedAdaptedText);
                      setValidationError(null);
                    }}
                    className="btn btn-secondary"
                    style={{
                      fontSize: '0.76rem',
                      padding: '0.35rem 0.75rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      color: 'var(--color-warning)',
                      borderColor: 'rgba(245, 158, 11, 0.4)',
                    }}
                  >
                    <FileText size={13} /> Use Proposed Wording as Instructions
                  </button>
                </div>

                <div
                  style={{
                    fontSize: '0.84rem',
                    color: 'var(--text-primary)',
                    lineHeight: 1.45,
                    padding: '0.6rem 0.75rem',
                    background: 'var(--bg-main)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {proposedAdaptedText}
                </div>

                {adaptationRationale && (
                  <div style={{ marginTop: '0.45rem' }}>
                    <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', fontWeight: '600' }}>
                      Adaptation Rationale:{' '}
                    </span>
                    <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                      {adaptationRationale}
                    </span>
                  </div>
                )}
              </div>
            )}

            <label style={{ fontSize: '0.82rem', color: '#fbbf24', display: 'block', marginBottom: '0.4rem', fontWeight: '600' }}>
              Adaptation Instructions & Specific Changes *
            </label>
            <textarea
              className="input-text"
              rows={3}
              placeholder="Specify clinical adjustments (e.g., adjust maximum daily dose to 3000 mg for pediatric subset or align contraindications)..."
              value={adaptationInstructions}
              onChange={(e) => {
                setAdaptationInstructions(e.target.value);
                setValidationError(null);
              }}
              style={{ width: '100%' }}
            />
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginTop: '0.3rem' }}>
              Reviewer instructions recorded here become the authorized directives for downstream change formulation.
            </span>
          </div>
        )}

        {/* Reviewer Information */}
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem', fontWeight: '500' }}>
            Reviewer Name & Regulatory Authority Title *
          </label>
          <input
            type="text"
            className="input-text"
            placeholder="e.g., Dr. Jane Doe, Senior Regulatory Affairs Specialist"
            value={reviewerName}
            onChange={(e) => {
              setReviewerName(e.target.value);
              setValidationError(null);
            }}
            style={{ width: '100%' }}
          />
        </div>

        {/* Reviewer Clinical Notes / Justification: Mandatory for all decisions */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem', fontWeight: '500' }}>
            Professional Rationale / Clinical Justification *
          </label>
          <textarea
            className="input-text"
            rows={4}
            placeholder="Document clinical and regulatory justification supporting this decision based on comparison evidence..."
            value={reviewerNotes}
            onChange={(e) => {
              setReviewerNotes(e.target.value);
              setValidationError(null);
            }}
            style={{ width: '100%' }}
          />
        </div>

        {/* Inline Validation Error Banner */}
        {validationError && (
          <div
            style={{
              marginBottom: '1.25rem',
              padding: '0.75rem 1rem',
              background: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 'var(--radius-sm)',
              color: '#fca5a5',
              fontSize: '0.84rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <AlertCircle size={16} color="var(--color-danger)" style={{ flexShrink: 0 }} />
            <span>{validationError}</span>
          </div>
        )}

        {/* Submission Error Banner */}
        {submitError && (
          <div
            style={{
              marginBottom: '1.25rem',
              padding: '0.75rem 1rem',
              background: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 'var(--radius-sm)',
              color: '#fca5a5',
              fontSize: '0.84rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <AlertCircle size={16} color="var(--color-danger)" style={{ flexShrink: 0 }} />
            <span>{submitError}</span>
          </div>
        )}

        {/* Recorded Confirmation Block */}
        {recordedDecision && (
          <div
            style={{
              marginBottom: '1.5rem',
              padding: '1rem',
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.35)',
              borderRadius: 'var(--radius-md)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <span style={{ color: 'var(--color-success)', fontWeight: '600', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <CheckCircle2 size={18} /> Human Decision Recorded Successfully
              </span>
              <span className="badge" style={getStatusStyle('MATCH')}>
                {recordedDecision.decision} AUTHORIZED
              </span>
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <span>Decision ID: <code style={{ color: '#fff' }}>{recordedDecision.decision_id}</code></span>
              <span>Timestamp: <strong>{new Date(recordedDecision.decided_at).toLocaleString()}</strong></span>
              <span>Authorizing Reviewer: <strong>{recordedDecision.reviewer_name}</strong></span>
              {recordedDecision.reviewer_notes && <span>Rationale: {recordedDecision.reviewer_notes}</span>}
              {recordedDecision.adaptation_instructions && (
                <span>Adaptation Instructions: {recordedDecision.adaptation_instructions}</span>
              )}
            </div>

            {onDecisionRecorded && (
              <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => onDecisionRecorded(recordedDecision)}
                  className="btn btn-primary"
                  style={{ fontSize: '0.82rem', padding: '0.4rem 0.9rem' }}
                >
                  Proceed to Change Review <ArrowRight size={13} />
                </button>
              </div>
            )}
          </div>
        )}

        {/* Decision Submission Action Bar */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            {!selectedDecision
              ? 'Select an action above to enable authorization'
              : `Action selected: ${selectedDecision}`}
          </span>

          <button
            type="button"
            onClick={handleSubmitDecision}
            className="btn btn-primary"
            disabled={!selectedDecision || submitting || !targetContentId || !candidateId}
          >
            <Send size={14} /> {submitting ? 'Recording Decision...' : 'Authorize & Record Decision'}
          </button>
        </div>
      </div>
    </div>
  );
}
