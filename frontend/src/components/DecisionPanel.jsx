import React, { useState } from 'react';
import { CheckCircle2, Sliders, XCircle, Send, ArrowRight, ShieldAlert } from 'lucide-react';
import { api } from '../services/api';

export default function DecisionPanel({ comparisonData, onDecisionRecorded }) {
  const [selectedDecision, setSelectedDecision] = useState('REUSE');
  const [reviewerName, setReviewerName] = useState('Senior Regulatory Affairs Specialist');
  const [reviewerNotes, setReviewerNotes] = useState(
    'Content aligns with FDA-approved DailyMed reference standard. Recommend adoption.'
  );
  const [adaptationInstructions, setAdaptationInstructions] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [recordedDecision, setRecordedDecision] = useState(null);

  async function handleSubmitDecision() {
    if (!reviewerName.trim()) {
      alert('Reviewer name and regulatory authority title are required.');
      return;
    }
    if (selectedDecision === 'ADAPT' && !adaptationInstructions.trim()) {
      alert('Adaptation instructions are mandatory when selecting ADAPT.');
      return;
    }

    setSubmitting(true);
    try {
      const decisionPayload = {
        target_content_id: comparisonData?.targetSection?.content_id || 'rc_target_demo',
        candidate_id: comparisonData?.candidateItem?.content_id || 'rc_cand_demo',
        decision: selectedDecision,
        reviewer_name: reviewerName.trim(),
        reviewer_notes: reviewerNotes.trim() || 'Regulatory decision recorded.',
        adaptation_instructions: selectedDecision === 'ADAPT' ? adaptationInstructions.trim() : null,
      };

      const result = await api.recordDecision(decisionPayload);
      setRecordedDecision(result);

      // If REUSE or ADAPT, formulate the controlled proposal via Agent 2
      if (selectedDecision !== 'REJECT') {
        await api.analyzeChangeProposal({
          decision_id: result.decision_id,
          section: comparisonData?.targetSection?.section || 'Dosage and Administration',
          original_text: comparisonData?.targetSection?.text || 'Adults: Take 1 tablet orally every 4 to 6 hours.',
          candidate_text: comparisonData?.candidateItem?.text || null,
          document_name: comparisonData?.targetSection?.document_name || null,
        });
      }

      if (onDecisionRecorded) {
        onDecisionRecorded(result);
      }
    } catch (err) {
      alert(`Decision recording failed: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="screen-header">
        <div>
          <h2>Human Decision Panel</h2>
          <p>Human regulatory professional authority: Evaluate evidence and mandate Reuse, Adapt, or Reject</p>
        </div>
      </div>

      <div className="card" style={{ maxWidth: '800px', margin: '0 auto' }}>
        <div className="card-header">
          <span className="card-title">
            <ShieldAlert size={16} color="var(--color-brand)" /> Regulatory Governance Decision Station
          </span>
          <span className="status-pill">
            Sole Human Authorization
          </span>
        </div>

        {/* Decision Option Buttons */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.6rem', fontWeight: '500' }}>
            Select Controlled Action
          </label>
          <div className="grid-3">
            <button
              type="button"
              onClick={() => setSelectedDecision('REUSE')}
              className={`btn ${selectedDecision === 'REUSE' ? 'btn-reuse' : 'btn-secondary'}`}
              style={{
                flexDirection: 'column',
                padding: '1rem',
                borderWidth: selectedDecision === 'REUSE' ? '2px' : '1px',
              }}
            >
              <CheckCircle2 size={24} color={selectedDecision === 'REUSE' ? 'var(--color-success)' : 'var(--text-muted)'} />
              <strong style={{ marginTop: '0.4rem', fontSize: '1rem' }}>REUSE</strong>
              <span style={{ fontSize: '0.72rem', opacity: 0.8, textAlign: 'center' }}>
                Direct adoption of validated external regulatory standard
              </span>
            </button>

            <button
              type="button"
              onClick={() => setSelectedDecision('ADAPT')}
              className={`btn ${selectedDecision === 'ADAPT' ? 'btn-adapt' : 'btn-secondary'}`}
              style={{
                flexDirection: 'column',
                padding: '1rem',
                borderWidth: selectedDecision === 'ADAPT' ? '2px' : '1px',
              }}
            >
              <Sliders size={24} color={selectedDecision === 'ADAPT' ? 'var(--color-warning)' : 'var(--text-muted)'} />
              <strong style={{ marginTop: '0.4rem', fontSize: '1rem' }}>ADAPT</strong>
              <span style={{ fontSize: '0.72rem', opacity: 0.8, textAlign: 'center' }}>
                Modify candidate with product-specific adaptations
              </span>
            </button>

            <button
              type="button"
              onClick={() => setSelectedDecision('REJECT')}
              className={`btn ${selectedDecision === 'REJECT' ? 'btn-reject' : 'btn-secondary'}`}
              style={{
                flexDirection: 'column',
                padding: '1rem',
                borderWidth: selectedDecision === 'REJECT' ? '2px' : '1px',
              }}
            >
              <XCircle size={24} color={selectedDecision === 'REJECT' ? 'var(--color-danger)' : 'var(--text-muted)'} />
              <strong style={{ marginTop: '0.4rem', fontSize: '1rem' }}>REJECT</strong>
              <span style={{ fontSize: '0.72rem', opacity: 0.8, textAlign: 'center' }}>
                Decline candidate; retain current internal document wording
              </span>
            </button>
          </div>
        </div>

        {/* Adaptation Guidance (visible when ADAPT selected) */}
        {selectedDecision === 'ADAPT' && (
          <div style={{ marginBottom: '1.25rem', background: 'rgba(245, 158, 11, 0.08)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
            <label style={{ fontSize: '0.82rem', color: '#fbbf24', display: 'block', marginBottom: '0.4rem', fontWeight: '600' }}>
              Adaptation Instructions & Specific Changes
            </label>
            <textarea
              className="input-text"
              rows={3}
              placeholder="Specify clinical adjustments (e.g. adjust maximum daily dose to 3000 mg for pediatric subset)..."
              value={adaptationInstructions}
              onChange={(e) => setAdaptationInstructions(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
        )}

        {/* Reviewer Information */}
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
            Reviewer Name & Regulatory Authority Title
          </label>
          <input
            type="text"
            className="input-text"
            value={reviewerName}
            onChange={(e) => setReviewerName(e.target.value)}
            style={{ width: '100%' }}
          />
        </div>

        {/* Reviewer Clinical Notes / Justification */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
            Professional Rationale & Regulatory Justification
          </label>
          <textarea
            className="input-text"
            rows={4}
            value={reviewerNotes}
            onChange={(e) => setReviewerNotes(e.target.value)}
            style={{ width: '100%' }}
          />
        </div>

        {/* Action Button */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {recordedDecision ? (
            <span style={{ color: 'var(--color-success)', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <CheckCircle2 size={16} /> Decision recorded (ID: <code>{recordedDecision.decision_id}</code>)
            </span>
          ) : <span />}

          <button
            onClick={handleSubmitDecision}
            className="btn btn-primary"
            disabled={submitting}
          >
            <Send size={14} /> {submitting ? 'Recording...' : 'Authorize Decision & Formulate Proposal'}
          </button>
        </div>
      </div>
    </div>
  );
}
