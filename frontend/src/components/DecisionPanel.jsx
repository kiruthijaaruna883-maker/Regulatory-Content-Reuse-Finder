import React from 'react';
import CandidateComparison from './CandidateComparison';

/**
 * DecisionPanel (Legacy Compatibility Component)
 *
 * In Phase 6G.5, Candidate Comparison and Decision Panel were consolidated into
 * a single unified workspace in CandidateComparison.jsx.
 *
 * This wrapper is retained for backward compatibility to prevent broken imports.
 * It delegates directly to CandidateComparison without rendering a duplicate decision UI.
 */
export default function DecisionPanel({ comparisonData, onDecisionRecorded }) {
  return (
    <CandidateComparison
      targetSection={comparisonData?.targetSection}
      candidateItem={comparisonData?.candidateItem}
      onDecisionRecorded={onDecisionRecorded}
    />
  );
}
