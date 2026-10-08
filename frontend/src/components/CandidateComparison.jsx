import React, { useState, useEffect, useRef } from 'react';
import {
  GitCompare,
  ExternalLink,
  AlertCircle,
  ArrowRight,
  Search,
  Database,
  ShieldAlert,
  CheckCircle2,
  Layers,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  FileText,
  Sliders,
  XCircle,
  Send,
  ShieldCheck
} from 'lucide-react';
import { api } from '../services/api';

const DIMENSIONS = [
  {
    key: 'meaning',
    name: 'Meaning',
    number: '1',
    description: 'Directive intent, regulatory modality (mandatory vs permissive), and administration conditions',
  },
  {
    key: 'template',
    name: 'Template',
    number: '2',
    description: 'Regulatory slot patterns: Posology, Indication, Contraindication structure',
  },
  {
    key: 'context',
    name: 'Context',
    number: '3',
    description: 'Operational setting (Prescribing vs Study observation), specialized patient populations',
  },
  {
    key: 'structure',
    name: 'Structure',
    number: '4',
    description: 'Section hierarchy, paragraph vs table vs bullet list vs stepwise instructions',
  },
  {
    key: 'format',
    name: 'Format',
    number: '5',
    description: 'Quantitative vs qualitative, fixed dose vs titration/range, shorthand vs narrative',
  },
  {
    key: 'key_information',
    name: 'Key Information',
    number: '6',
    description: 'Exact clinical entities: drug, dose, unit, frequency, route, population, indication',
  },
];

export default function CandidateComparison({
  targetSection,
  candidateItem,
  activeSourceDocument,
  _onProceedToDecision,
  onDecisionRecorded,
}) {
  // Resolve effective source document identity (targetSection takes precedence, activeSourceDocument as fallback)
  const effectiveDocumentId = targetSection?.document_id || activeSourceDocument?.document_id || null;
  const effectiveDocumentFingerprint = targetSection?.document_fingerprint || activeSourceDocument?.document_fingerprint || null;
  const effectiveDocumentName = targetSection?.document_name || activeSourceDocument?.document_name || null;
  const effectiveTargetContentId = targetSection?.content_id || (activeSourceDocument?.sections?.length > 0 ? activeSourceDocument.sections[0].content_id : null) || null;

  // Target Content State
  const DEFAULT_SAMPLE_TARGET_TEXT =
    'Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours with water. Do not exceed 6 tablets within 24 hours.';
  const initialTargetText = targetSection?.text ||
    (activeSourceDocument?.sections?.find((s) => s.text)?.text || (activeSourceDocument?.sections?.length > 0 ? activeSourceDocument.sections[0].text : null)) ||
    DEFAULT_SAMPLE_TARGET_TEXT;
  const [targetText, setTargetText] = useState(initialTargetText);

  // Safety check: Never treat fallback sample text as a real uploaded document
  const isFallbackSampleText =
    !targetSection?.text &&
    (!activeSourceDocument?.sections || !activeSourceDocument.sections.some((s) => s.text && s.text.trim() === (targetText || '').trim())) &&
    (targetText || '').trim() === DEFAULT_SAMPLE_TARGET_TEXT.trim();

  // Active Selected Candidate State (initialized from candidateItem prop)
  const initialCandidateUnderlying =
    candidateItem?.content_item ||
    candidateItem?.candidate ||
    candidateItem ||
    null;
  const [selectedCandidate, setSelectedCandidate] = useState(initialCandidateUnderlying);
  const [candidateText, setCandidateText] = useState(
    initialCandidateUnderlying?.text ||
    candidateItem?.content_item?.text ||
    candidateItem?.text ||
    'Adults: Take 1 to 2 tablets (500 mg) orally every 4 to 6 hours as needed. Maximum dosage: 8 tablets in 24 hours.'
  );

  // Human Candidate Decision State
  const [selectedDecision, setSelectedDecision] = useState(null); // Explicit choice: REUSE | ADAPT | REJECT (defaults to null)
  const [reviewerName, setReviewerName] = useState('');
  const [reviewerNotes, setReviewerNotes] = useState('');
  const [adaptationInstructions, setAdaptationInstructions] = useState('');
  const [submittingDecision, setSubmittingDecision] = useState(false);
  const [decisionValidationError, setDecisionValidationError] = useState(null);
  const [decisionSubmitError, setDecisionSubmitError] = useState(null);
  const [recordedDecision, setRecordedDecision] = useState(null);

  // Candidate Discovery Search State
  const initialSearchQuery = targetSection?.section ||
    targetSection?.document_name ||
    activeSourceDocument?.document_name ||
    (activeSourceDocument?.sections?.length > 0 ? (activeSourceDocument.sections[0].section || activeSourceDocument.sections[0].document_name) : null) ||
    'aspirin';
  const [searchQuery, setSearchQuery] = useState(initialSearchQuery);
  const [sourceFilter, setSourceFilter] = useState('all');
  const [topK, setTopK] = useState(10);
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);

  // Six-Dimensional Analysis State
  const [analysisResult, setAnalysisResult] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState(null);
  const [selectedCandidateIndex, setSelectedCandidateIndex] = useState(0);

  // Grouped Differences State & UI Filter
  const [differences, setDifferences] = useState([]);
  const [selectedDimensionFilter, setSelectedDimensionFilter] = useState('all');
  const [expandedFacts, setExpandedFacts] = useState({});
  const [showTraceabilityDetails, setShowTraceabilityDetails] = useState(false);
  const [showDiscoveryConsole, setShowDiscoveryConsole] = useState(false);

  // Auto-discovery key ref to prevent repeated duplicate auto-discovery calls
  const autoDiscoveredKeyRef = useRef(null);

  // Adjust state when targetSection or activeSourceDocument prop changes
  const [prevTargetSection, setPrevTargetSection] = useState(targetSection);
  const [prevSourceDoc, setPrevSourceDoc] = useState(activeSourceDocument);
  if (targetSection !== prevTargetSection || activeSourceDocument !== prevSourceDoc) {
    setPrevTargetSection(targetSection);
    setPrevSourceDoc(activeSourceDocument);
    if (targetSection?.text) {
      setTargetText(targetSection.text);
    } else if (!targetSection && activeSourceDocument?.sections?.length > 0) {
      setTargetText(activeSourceDocument.sections[0].text);
    }
    if (targetSection?.section) {
      setSearchQuery(targetSection.section);
    } else if (!targetSection && activeSourceDocument?.document_name) {
      setSearchQuery(activeSourceDocument.document_name);
    }
    setAnalysisResult(null);
    setDifferences([]);
    setSelectedCandidateIndex(0);
  }

  // Adjust state when candidateItem prop changes
  const [prevCandidateItem, setPrevCandidateItem] = useState(candidateItem);
  if (candidateItem !== prevCandidateItem) {
    setPrevCandidateItem(candidateItem);
    if (candidateItem) {
      const underlying =
        candidateItem.content_item ||
        candidateItem.candidate ||
        candidateItem;
      setSelectedCandidate(underlying);
      const textToSet =
        underlying.text ||
        candidateItem.content_item?.text ||
        candidateItem.text;
      if (textToSet) {
        setCandidateText(textToSet);
      }
    }
    setAnalysisResult(null);
    setDifferences([]);
    setSelectedCandidateIndex(0);
  }

  // Automatic Candidate Discovery & 6D Evaluation on Mount / Section Change
  useEffect(() => {
    const currentKey = targetSection?.content_id ||
      effectiveTargetContentId ||
      targetSection?.section ||
      effectiveDocumentId ||
      (targetText ? targetText.slice(0, 60) : null);
    if (!currentKey || autoDiscoveredKeyRef.current === currentKey) {
      return;
    }
    autoDiscoveredKeyRef.current = currentKey;

    async function triggerAutoDiscovery() {
      const cleanTarget = (targetText || '').trim();
      if (cleanTarget.length < 5) return;

      setAnalyzing(true);
      setAnalysisError(null);
      try {
        const options = {
          retrieve_live: true,
          source_filter: 'all',
          top_k: 10,
        };
        if (effectiveTargetContentId && !isFallbackSampleText) {
          options.target_content_id = effectiveTargetContentId;
        }
        if (effectiveDocumentName) options.document_name = effectiveDocumentName;
        // Never treat the fallback sample text as a real uploaded document
        if (effectiveDocumentId && !isFallbackSampleText) {
          options.document_id = effectiveDocumentId;
        }
        // Always enforce exclusion if an active source document identity exists
        if (effectiveDocumentId) {
          options.exclude_document_id = effectiveDocumentId;
        }
        if (effectiveDocumentFingerprint) {
          options.exclude_document_fingerprint = effectiveDocumentFingerprint;
        }
        if (targetSection?.subsection) options.subsection = targetSection.subsection;
        if (targetSection?.location) options.location = targetSection.location;
        if (targetSection?.page !== undefined && targetSection?.page !== null) options.page = targetSection.page;
        if (targetSection?.content_type) options.content_type = targetSection.content_type;

        const candidatePayloads = candidateItem
          ? [
              {
                ...candidateItem,
                source: candidateItem.source || 'DailyMed',
                text: candidateText || candidateItem.text || '',
              },
            ]
          : [];

        const result = await api.analyzeCandidates(
          cleanTarget,
          candidatePayloads,
          targetSection?.section || null,
          options
        );

        setAnalysisResult(result);
        if (result?.candidates?.length > 0) {
          const topComp = result.candidates[0];
          const topUnderlying =
            topComp.content_item ||
            topComp.candidate ||
            topComp;
          setSelectedCandidate(topUnderlying);
          setCandidateText(
            topUnderlying.text ||
            topComp.content_item?.text ||
            ''
          );
          setDifferences(topComp.differences || []);
          setSelectedCandidateIndex(0);
        }
      } catch (err) {
        console.warn('Auto-discovery non-blocking notice:', err);
      } finally {
        setAnalyzing(false);
      }
    }

    triggerAutoDiscovery();
  }, [
    targetSection,
    activeSourceDocument,
    targetText,
    candidateItem,
    candidateText,
    effectiveDocumentId,
    effectiveDocumentFingerprint,
    effectiveDocumentName,
    effectiveTargetContentId,
    isFallbackSampleText,
  ]);

  // Trigger candidate discovery via api.searchCandidates
  async function handleDiscoverCandidates(e) {
    if (e) e.preventDefault();
    setSearchError(null);

    const queryClean = (searchQuery || '').trim();
    if (!queryClean) {
      setSearchError('Search query is required to discover regulatory candidates.');
      return;
    }

    setSearching(true);
    try {
      const response = await api.searchCandidates({
        query: queryClean,
        source_filter: sourceFilter,
        section: targetSection?.section || null,
        target_text: isFallbackSampleText ? null : (targetText || null),
        top_k: Number(topK),
        exclude_document_id: effectiveDocumentId,
        document_id: effectiveDocumentId,
        exclude_document_fingerprint: effectiveDocumentFingerprint,
        target_content_id: isFallbackSampleText ? null : effectiveTargetContentId,
      });

      const items = response?.items || [];
      setSearchResults(items);
    } catch (err) {
      setSearchError(err.message || 'Failed to discover regulatory candidates.');
    } finally {
      setSearching(false);
    }
  }

  // Set selected candidate and update comparison reference text
  function handleSelectCandidate(candidate) {
    setSelectedCandidate(candidate);
    setCandidateText(candidate.text || '');
    setDifferences([]);
    setAnalysisResult(null);
    setAnalysisError(null);
    setSelectedCandidateIndex(0);
    setSelectedDecision(null);
    setDecisionValidationError(null);
    setDecisionSubmitError(null);
    setRecordedDecision(null);
  }

  // Set active candidate from analyzed candidates list
  function handleSelectAnalysisCandidate(idx) {
    setSelectedCandidateIndex(idx);
    const comp = analysisResult?.candidates?.[idx];
    if (comp) {
      const underlying =
        comp.content_item ||
        comp.candidate ||
        comp;
      setSelectedCandidate(underlying);
      setCandidateText(
        underlying.text ||
        comp.content_item?.text ||
        ''
      );
      setDifferences(comp.differences || []);
      setAnalysisError(null);
      setSelectedDecision(null);
      setDecisionValidationError(null);
      setDecisionSubmitError(null);
      setRecordedDecision(null);
    }
  }

  // Run Six-Dimensional Comparison via api.analyzeCandidates
  async function handleRunSixDimensionalComparison() {
    setAnalysisError(null);

    const cleanTarget = (targetText || '').trim();
    if (!cleanTarget) {
      setAnalysisError('Target document content is required before running comparison.');
      return;
    }

    if (!selectedCandidate) {
      setAnalysisError(
        'Please select a regulatory candidate reference before running comparison. Use the search tool to find and select a candidate.'
      );
      return;
    }

    setAnalyzing(true);
    try {
      const candidatePayload = {
        ...selectedCandidate,
        source: selectedCandidate.source || 'DailyMed',
        text: candidateText || selectedCandidate.text || '',
      };

      const options = {};
      if (effectiveTargetContentId && !isFallbackSampleText) {
        options.target_content_id = effectiveTargetContentId;
      }
      if (effectiveDocumentName) options.document_name = effectiveDocumentName;
      if (effectiveDocumentId && !isFallbackSampleText) {
        options.document_id = effectiveDocumentId;
      }
      if (effectiveDocumentId) {
        options.exclude_document_id = effectiveDocumentId;
      }
      if (effectiveDocumentFingerprint) {
        options.exclude_document_fingerprint = effectiveDocumentFingerprint;
      }
      if (targetSection?.subsection) options.subsection = targetSection.subsection;
      if (targetSection?.location) options.location = targetSection.location;
      if (targetSection?.page !== undefined && targetSection?.page !== null) options.page = targetSection.page;
      if (targetSection?.content_type) options.content_type = targetSection.content_type;

      const result = await api.analyzeCandidates(
        cleanTarget,
        [candidatePayload],
        targetSection?.section || null,
        options
      );

      setAnalysisResult(result);
      setSelectedCandidateIndex(0);
      const candDiffs = result?.candidates?.[0]?.differences || [];
      setDifferences(candDiffs);
    } catch (err) {
      setAnalysisError(err.message || 'Six-dimensional comparison failed.');
    } finally {
      setAnalyzing(false);
    }
  }

  function toggleFactExpansion(key) {
    setExpandedFacts((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  }

  function getSourceStyle(source) {
    const s = (source || '').toLowerCase();
    if (s.includes('dailymed')) {
      return {
        background: 'rgba(56, 189, 248, 0.12)',
        color: 'var(--color-dailymed)',
        border: '1px solid rgba(56, 189, 248, 0.3)',
      };
    }
    if (s.includes('openfda')) {
      return {
        background: 'rgba(167, 139, 250, 0.12)',
        color: 'var(--color-openfda)',
        border: '1px solid rgba(167, 139, 250, 0.3)',
      };
    }
    if (s.includes('internal') || s.includes('draft') || s.includes('ingest')) {
      return {
        background: 'rgba(20, 184, 166, 0.12)',
        color: 'var(--color-brand-teal)',
        border: '1px solid rgba(20, 184, 166, 0.3)',
      };
    }
    return {
      background: 'var(--bg-surface-elevated)',
      color: 'var(--text-secondary)',
      border: '1px solid var(--border-subtle)',
    };
  }

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

  // Derive primary candidate evaluation from analysis result
  const primaryCandidate = analysisResult?.candidates?.[selectedCandidateIndex] || analysisResult?.candidates?.[0] || null;
  const matchResult = primaryCandidate?.multi_dimensional_match || null;
  const falseMatchWarning =
    primaryCandidate?.false_match_warning ||
    (analysisResult?.false_matches_detected > 0
      ? 'Critical regulatory discrepancy detected between current draft and reference.'
      : null);
  const primaryEvidence = primaryCandidate?.evidence?.[0] || null;
  const observedFacts = primaryEvidence?.observed_from_source || null;
  const targetFacts = primaryEvidence?.target_facts || null;

  // Filter differences by selected dimension tab
  const filteredDifferences = differences.filter((d) => {
    if (selectedDimensionFilter === 'all') return true;
    const dim = (d.source_dimension || '').toLowerCase();
    return dim === selectedDimensionFilter.toLowerCase();
  });

  const diffCounts = differences.reduce((acc, d) => {
    const dim = (d.source_dimension || 'other').toLowerCase();
    acc[dim] = (acc[dim] || 0) + 1;
    return acc;
  }, {});

  // Derived Provenance Identifiers for Decision Authorization
  const targetContentId =
    targetSection?.content_id ||
    analysisResult?.target_content_id ||
    analysisResult?.candidates?.[0]?.evidence?.[0]?.target_facts?.target_content_id ||
    null;

  const candidateId =
    selectedCandidate?.content_id ||
    primaryCandidate?.candidate?.content_id ||
    primaryCandidate?.content_item?.content_id ||
    primaryCandidate?.candidate_id ||
    null;

  // Advisory Recommendation Signals
  const recommendedDecision =
    primaryCandidate?.recommended_decision ||
    selectedCandidate?.recommended_decision ||
    null;
  const recommendationReason =
    primaryCandidate?.recommendation_reason ||
    selectedCandidate?.recommendation_reason ||
    null;
  const recommendationConfidence =
    primaryCandidate?.recommendation_confidence ??
    selectedCandidate?.recommendation_confidence ??
    null;
  const proposedAdaptedText =
    primaryCandidate?.proposed_adapted_text ||
    selectedCandidate?.proposed_adapted_text ||
    null;
  const adaptationRationale =
    primaryCandidate?.adaptation_rationale ||
    selectedCandidate?.adaptation_rationale ||
    null;

  // Human Decision Authorization Handler
  async function handleSubmitDecision() {
    setDecisionValidationError(null);
    setDecisionSubmitError(null);

    // 1. Validate Decision Selection (Explicit choice required)
    if (!selectedDecision) {
      setDecisionValidationError('An explicit regulatory action (Reuse, Adapt, or Reject) must be selected.');
      return;
    }

    // 2. Validate Provenance Context
    if (!targetContentId || !candidateId) {
      setDecisionValidationError(
        'Valid target and candidate content identifiers are required to authorize a decision. Ensure target draft and candidate reference items are selected.'
      );
      return;
    }

    // 3. Validate Reviewer Name
    if (!reviewerName.trim()) {
      setDecisionValidationError('Reviewer name and regulatory authority title are required.');
      return;
    }

    // 4. Validate Reviewer Rationale
    if (!reviewerNotes.trim()) {
      setDecisionValidationError(
        'Professional rationale and clinical justification are mandatory for all regulatory decisions.'
      );
      return;
    }

    // 5. Validate Adaptation Instructions when ADAPT is selected
    if (selectedDecision === 'ADAPT' && !adaptationInstructions.trim()) {
      setDecisionValidationError('Specific adaptation instructions are mandatory when selecting ADAPT.');
      return;
    }

    setSubmittingDecision(true);
    try {
      const decisionPayload = {
        target_content_id: targetContentId,
        candidate_id: candidateId,
        document_id:
          targetSection?.document_id ||
          analysisResult?.target_document_id ||
          null,
        decision: selectedDecision,
        reviewer_name: reviewerName.trim(),
        reviewer_notes: reviewerNotes.trim(),
        adaptation_instructions: selectedDecision === 'ADAPT' ? adaptationInstructions.trim() : null,
      };

      const result = await api.recordDecision(decisionPayload);
      setRecordedDecision(result);
    } catch (err) {
      setDecisionSubmitError(err.message || 'Failed to record regulatory decision.');
    } finally {
      setSubmittingDecision(false);
    }
  }

  function handleProceedToChangeReview() {
    if (onDecisionRecorded && recordedDecision) {
      const context = {
        targetText,
        candidateText,
        differences,
        candidateItem: selectedCandidate,
        analysisResult,
        targetSection: targetSection || (analysisResult?.target_section ? {
          section: analysisResult.target_section,
          document_name: analysisResult.target_document_name,
          document_id: analysisResult.target_document_id,
          content_id: analysisResult.target_content_id,
          subsection: analysisResult.target_subsection,
          location: analysisResult.target_location,
          page: analysisResult.target_page,
          content_type: analysisResult.target_content_type,
          text: targetText,
        } : null),
      };
      onDecisionRecorded(recordedDecision, context);
    }
  }

  return (
    <div>
      {/* 1. Review Header (Simple Business Language) */}
      <div className="card" style={{ marginBottom: '1.5rem', background: 'var(--bg-surface)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.2rem 0.55rem', borderRadius: '9999px', background: 'rgba(13, 148, 136, 0.08)', color: 'var(--color-brand)', fontSize: '0.76rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              <GitCompare size={13} /> Candidate Comparison & Human Decision
            </div>
            <h2 style={{ fontSize: '1.45rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 0.35rem 0' }}>
              Review Candidate Content
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
              <span>
                Draft Section: <strong>{targetSection?.section || 'Internal Draft Section'}</strong> ({targetSection?.document_name || 'Draft Prescribing Information'})
              </span>
              <span>•</span>
              <span>
                Candidate Reference: <strong>{selectedCandidate?.document_name || selectedCandidate?.product || 'Auto-Discovered Reference'}</strong> ({selectedCandidate?.source || 'DailyMed'})
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <button
              onClick={handleRunSixDimensionalComparison}
              className="btn btn-secondary"
              style={{ fontSize: '0.8rem', padding: '0.45rem 0.9rem' }}
              disabled={analyzing}
              title="Re-evaluate 6-dimensional comparison between draft and reference"
            >
              <GitCompare size={14} /> {analyzing ? 'Analyzing...' : 'Re-run Comparison'}
            </button>
            <button
              onClick={() => setShowDiscoveryConsole(!showDiscoveryConsole)}
              className="btn btn-secondary"
              style={{ fontSize: '0.8rem', padding: '0.45rem 0.9rem' }}
            >
              <Search size={14} /> {showDiscoveryConsole ? 'Hide Search' : 'Search / Switch Candidate'}
            </button>
          </div>
        </div>

        {/* Multi-candidate Switcher Bar if multiple candidates discovered */}
        {analysisResult?.candidates?.length > 1 && (
          <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.76rem', fontWeight: 600, color: 'var(--text-muted)' }}>
              Discovered Candidates ({analysisResult.candidates.length}):
            </span>
            {analysisResult.candidates.map((compCand, idx) => {
              const item =
                compCand.content_item ||
                compCand.candidate ||
                compCand;
              const isSelected = selectedCandidateIndex === idx;
              return (
                <button
                  key={item.content_id || idx}
                  onClick={() => handleSelectAnalysisCandidate(idx)}
                  className={`badge ${isSelected ? 'badge-section' : ''}`}
                  style={{
                    cursor: 'pointer',
                    fontSize: '0.74rem',
                    padding: '0.25rem 0.6rem',
                    border: isSelected ? '1px solid var(--color-brand)' : '1px solid var(--border-subtle)',
                    background: isSelected ? 'var(--bg-surface-elevated)' : 'transparent',
                    color: isSelected ? 'var(--color-brand)' : 'var(--text-secondary)',
                    fontWeight: isSelected ? 700 : 500,
                  }}
                >
                  Candidate #{idx + 1}: {item.document_name || item.product || 'Record'} ({item.source || compCand.source})
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Expandable Candidate Discovery & Search Console */}
      {showDiscoveryConsole && (
        <div className="card" style={{ marginBottom: '1.5rem', background: 'var(--bg-surface-elevated)' }}>
          <div className="card-header">
            <span className="card-title">
              <Search size={16} color="var(--color-brand)" /> Search Regulatory Candidates
            </span>
            <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
              Queries candidate stores and live health authority sources
            </span>
          </div>

          <form onSubmit={handleDiscoverCandidates} className="input-group" style={{ flexWrap: 'wrap', gap: '0.6rem', marginBottom: '0.75rem' }}>
            <input
              type="text"
              className="input-text"
              placeholder="Search by drug name, active ingredient, or section topic..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ minWidth: '260px', flex: 2 }}
            />
            <select
              className="select-box"
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              style={{ minWidth: '150px' }}
            >
              <option value="all">All Sources</option>
              <option value="ingested">Ingested Documents</option>
              <option value="dailymed">DailyMed</option>
              <option value="openfda">openFDA</option>
            </select>
            <select
              className="select-box"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              style={{ width: '85px' }}
            >
              <option value={5}>Top 5</option>
              <option value={10}>Top 10</option>
              <option value={20}>Top 20</option>
            </select>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={searching}
              style={{ fontSize: '0.82rem', padding: '0.55rem 1rem' }}
            >
              <Database size={14} /> {searching ? 'Searching...' : 'Find Candidates'}
            </button>
          </form>

          {searchError && (
            <div style={{ padding: '0.65rem 0.85rem', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#b91c1c', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <AlertCircle size={15} />
              <span>{searchError}</span>
            </div>
          )}

          {/* Search Results List */}
          {searchResults.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', maxHeight: '280px', overflowY: 'auto' }}>
              {searchResults.map((cand) => (
                <div
                  key={cand.content_id}
                  style={{
                    background: '#ffffff',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '0.75rem',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '0.75rem',
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                      <strong style={{ fontSize: '0.86rem' }}>{cand.document_name || cand.product || 'Record'}</strong>
                      <span className="badge" style={getSourceStyle(cand.source)}>{cand.source}</span>
                      {cand.section && <span className="badge badge-section">{cand.section}</span>}
                    </div>
                    <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0.25rem 0 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {cand.text}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      handleSelectCandidate(cand);
                      setShowDiscoveryConsole(false);
                    }}
                    className="btn btn-secondary"
                    style={{ fontSize: '0.76rem', padding: '0.35rem 0.75rem', flexShrink: 0 }}
                  >
                    Select This Candidate
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Global Error Banner */}
      {analysisError && (
        <div style={{ marginBottom: '1.25rem', padding: '0.75rem 1rem', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#b91c1c', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <AlertCircle size={16} />
          <span>{analysisError}</span>
        </div>
      )}

      {/* 2. Advisory Recommendation — PROMINENT */}
      {recommendedDecision ? (
        <div
          className="card"
          style={{
            marginBottom: '1.5rem',
            padding: '1.25rem 1.5rem',
            background:
              recommendedDecision === 'REUSE'
                ? 'linear-gradient(135deg, rgba(21, 128, 61, 0.08) 0%, #ffffff 100%)'
                : recommendedDecision === 'ADAPT'
                ? 'linear-gradient(135deg, rgba(180, 83, 9, 0.08) 0%, #ffffff 100%)'
                : 'linear-gradient(135deg, rgba(185, 28, 28, 0.08) 0%, #ffffff 100%)',
            border: `1.5px solid ${
              recommendedDecision === 'REUSE'
                ? 'rgba(21, 128, 61, 0.35)'
                : recommendedDecision === 'ADAPT'
                ? 'rgba(180, 83, 9, 0.35)'
                : 'rgba(185, 28, 28, 0.35)'
            }`,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.6rem', marginBottom: '0.6rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span
                style={{
                  fontSize: '0.88rem',
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                  padding: '0.35rem 0.8rem',
                  borderRadius: 'var(--radius-sm)',
                  background:
                    recommendedDecision === 'REUSE'
                      ? 'rgba(21, 128, 61, 0.15)'
                      : recommendedDecision === 'ADAPT'
                      ? 'rgba(180, 83, 9, 0.15)'
                      : 'rgba(185, 28, 28, 0.15)',
                  color:
                    recommendedDecision === 'REUSE'
                      ? 'var(--color-success)'
                      : recommendedDecision === 'ADAPT'
                      ? 'var(--color-warning)'
                      : 'var(--color-danger)',
                  border: `1px solid ${
                    recommendedDecision === 'REUSE'
                      ? 'rgba(21, 128, 61, 0.3)'
                      : recommendedDecision === 'ADAPT'
                      ? 'rgba(180, 83, 9, 0.3)'
                      : 'rgba(185, 28, 28, 0.3)'
                  }`,
                }}
              >
                {recommendedDecision}
              </span>
              <div>
                <strong style={{ fontSize: '0.94rem', color: 'var(--text-primary)', display: 'block' }}>
                  Advisory Recommendation
                </strong>
                <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                  Human decision required — The regulatory reviewer retains final authority
                </span>
              </div>
            </div>

            {recommendationConfidence !== null && recommendationConfidence !== undefined && (
              <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', background: 'var(--bg-surface-elevated)', padding: '0.25rem 0.65rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontWeight: 600 }}>
                Advisory Confidence: {Math.round(recommendationConfidence * 100)}%
              </span>
            )}
          </div>

          {/* 3. Why Was This Recommended? */}
          <div style={{ marginTop: '0.6rem', background: '#ffffff', padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.76rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Why Was This Recommended?
            </span>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-primary)', margin: 0, lineHeight: 1.5 }}>
              {recommendationReason || matchResult?.overall_alignment_summary || analysisResult?.summary_explanation || 'Candidate aligns with established regulatory standards.'}
            </p>
          </div>

          {/* ADAPT Advisory Wording (when recommended) */}
          {recommendedDecision === 'ADAPT' && proposedAdaptedText && (
            <div style={{ marginTop: '0.75rem', background: 'rgba(245, 158, 11, 0.05)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(245, 158, 11, 0.25)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                <strong style={{ fontSize: '0.82rem', color: 'var(--color-warning)' }}>
                  Advisory Proposed Adaptation:
                </strong>
                <button
                  type="button"
                  onClick={() => {
                    setAdaptationInstructions(proposedAdaptedText);
                    setSelectedDecision('ADAPT');
                    setDecisionValidationError(null);
                    const el = document.getElementById('decision-station');
                    if (el) el.scrollIntoView({ behavior: 'smooth' });
                  }}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.74rem', padding: '0.25rem 0.65rem', color: 'var(--color-warning)' }}
                >
                  <FileText size={12} /> Use As Starting Instructions
                </button>
              </div>
              <p style={{ fontSize: '0.84rem', color: 'var(--text-primary)', margin: 0, fontStyle: 'italic', lineHeight: 1.45 }}>
                "{proposedAdaptedText}"
              </p>
              {adaptationRationale && (
                <div style={{ marginTop: '0.4rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  <strong style={{ color: 'var(--text-secondary)' }}>Adaptation Rationale:</strong> {adaptationRationale}
                </div>
              )}
            </div>
          )}

          {/* False Match Discrepancy Alert */}
          {falseMatchWarning && (
            <div style={{ marginTop: '0.75rem', padding: '0.75rem 1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <ShieldAlert size={18} color="var(--color-danger)" style={{ flexShrink: 0 }} />
              <div>
                <strong style={{ fontSize: '0.82rem', color: 'var(--color-danger)', display: 'block' }}>False Match Warning</strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-primary)' }}>{falseMatchWarning}</span>
              </div>
            </div>
          )}
        </div>
      ) : null}

      {/* 4. Side-by-Side Content Comparison */}
      <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
        {/* Left: Target Content (Current Draft) */}
        <div className="card">
          <div className="card-header">
            <div>
              <span className="card-title">
                <FileText size={16} color="var(--color-brand)" /> Target Content (Current Draft)
              </span>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                {targetSection?.document_name || 'Draft Label'} • {targetSection?.section || 'Section'}
              </span>
            </div>
            {targetSection?.jurisdiction && (
              <span className="badge badge-section" style={{ fontSize: '0.72rem' }}>
                {targetSection.jurisdiction}
              </span>
            )}
          </div>

          <textarea
            className="input-text"
            rows={7}
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem', lineHeight: 1.45 }}
            placeholder="Target draft content..."
          />
        </div>

        {/* Right: Candidate Content (Approved Reference) */}
        <div className="card">
          <div className="card-header">
            <div>
              <span className="card-title">
                <Database size={16} color="var(--color-dailymed)" /> Candidate Content (Approved Reference)
              </span>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                {selectedCandidate?.document_name || selectedCandidate?.product || primaryCandidate?.content_item?.document_name || 'Reference Label'} • {selectedCandidate?.section || primaryCandidate?.content_item?.section || 'Approved Section'}
              </span>
            </div>
            <span className="badge" style={getSourceStyle(selectedCandidate?.source || primaryCandidate?.content_item?.source)}>
              {selectedCandidate?.source || primaryCandidate?.content_item?.source || 'Reference'}
            </span>
          </div>

          <textarea
            className="input-text"
            rows={7}
            value={candidateText}
            onChange={(e) => setCandidateText(e.target.value)}
            style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem', lineHeight: 1.45 }}
            placeholder="Candidate reference content..."
          />

          {selectedCandidate?.source_url && (
            <div style={{ marginTop: '0.5rem', display: 'flex', justifyContent: 'flex-end' }}>
              <a href={selectedCandidate.source_url} target="_blank" rel="noopener noreferrer" className="trace-link" style={{ fontSize: '0.74rem' }}>
                <ExternalLink size={12} /> Trace Official Health Authority Record
              </a>
            </div>
          )}
        </div>
      </div>

      {/* 5. Six Comparison Dimensions (Compact Summary + Detail Cards) */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">
          <div>
            <span className="card-title">
              <Layers size={16} color="var(--color-brand)" /> Six-Dimensional Regulatory Alignment
            </span>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0.15rem 0 0 0' }}>
              Multi-dimensional regulatory analysis across established health authority criteria
            </p>
          </div>
          {primaryCandidate?.similarity_score !== undefined && primaryCandidate?.similarity_score !== null && (
            <span className="badge badge-section" style={{ fontSize: '0.75rem' }}>
              Overall Retrieval Similarity: {Math.round(primaryCandidate.similarity_score * 100)}%
            </span>
          )}
        </div>

        {/* Compact Dimension Status Chips */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.5rem', marginBottom: '1rem', padding: '0.75rem', background: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-md)' }}>
          {DIMENSIONS.map((dim) => {
            const evalData = matchResult?.[dim.key];
            const status = evalData?.status || 'EVALUATED';
            return (
              <div key={dim.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.35rem 0.5rem', background: '#ffffff', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {dim.name}
                </span>
                <span className="badge" style={{ ...getStatusStyle(status), fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>
                  {status}
                </span>
              </div>
            );
          })}
        </div>

        {/* Six Dimensions Breakdown Cards */}
        <div className="grid-3" style={{ gap: '0.85rem' }}>
          {DIMENSIONS.map((dim) => {
            const evalData = matchResult?.[dim.key];
            const status = evalData?.status || 'EVALUATED';
            const isExpanded = !!expandedFacts[dim.key];

            return (
              <div
                key={dim.key}
                style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: '0.85rem',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <strong style={{ fontSize: '0.86rem', color: 'var(--text-primary)' }}>
                      {dim.number}. {dim.name}
                    </strong>
                    <span className="badge" style={getStatusStyle(status)}>
                      {status}
                    </span>
                  </div>

                  <p style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginBottom: '0.5rem', lineHeight: 1.4 }}>
                    {dim.description}
                  </p>

                  {evalData?.score !== undefined && evalData?.score !== null && (
                    <div style={{ marginBottom: '0.5rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.2rem' }}>
                        <span>Alignment</span>
                        <strong>{Math.round(evalData.score * 100)}%</strong>
                      </div>
                      <div style={{ height: '4px', background: 'var(--border-subtle)', borderRadius: '2px', overflow: 'hidden' }}>
                        <div
                          style={{
                            height: '100%',
                            width: `${Math.min(Math.max(evalData.score * 100, 0), 100)}%`,
                            background:
                              evalData.score >= 0.8
                                ? 'var(--color-success)'
                                : evalData.score >= 0.5
                                ? 'var(--color-warning)'
                                : 'var(--color-danger)',
                          }}
                        />
                      </div>
                    </div>
                  )}

                  <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.45, margin: '0 0 0.5rem 0' }}>
                    {evalData?.details || 'Dimension evaluated according to regulatory standards.'}
                  </p>
                </div>

                {/* Evidence & Reasoning Expandable */}
                {(evalData?.observed_from_source || evalData?.model_interpretation) && (
                  <div style={{ marginTop: '0.4rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.4rem' }}>
                    <button
                      type="button"
                      onClick={() => toggleFactExpansion(dim.key)}
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
                      <span>{isExpanded ? 'Hide Evidence' : 'View Evidence'}</span>
                      {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>

                    {isExpanded && (
                      <div style={{ marginTop: '0.4rem', padding: '0.5rem', background: '#ffffff', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '0.72rem' }}>
                        {evalData?.observed_from_source && (
                          <div style={{ marginBottom: '0.3rem' }}>
                            <span style={{ color: 'var(--color-brand)', fontWeight: 600, display: 'block' }}>Observed Source Evidence:</span>
                            <span style={{ color: 'var(--text-secondary)' }}>{evalData.observed_from_source}</span>
                          </div>
                        )}
                        {evalData?.model_interpretation && (
                          <div>
                            <span style={{ color: 'var(--color-openfda)', fontWeight: 600, display: 'block' }}>Analysis Interpretation:</span>
                            <span style={{ color: 'var(--text-secondary)' }}>{evalData.model_interpretation}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Detected Differences (if any exist) */}
      {differences.length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">
            <div>
              <span className="card-title">
                <AlertCircle size={16} color="var(--color-warning)" /> Detected Differences ({differences.length})
              </span>
              <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                Specific distinctions identified between current draft and reference
              </span>
            </div>
            <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => setSelectedDimensionFilter('all')}
                className={`badge ${selectedDimensionFilter === 'all' ? 'badge-section' : ''}`}
                style={{ cursor: 'pointer', border: '1px solid var(--border-subtle)', background: selectedDimensionFilter === 'all' ? 'var(--bg-surface-elevated)' : 'transparent' }}
              >
                All ({differences.length})
              </button>
              {DIMENSIONS.map((dim) => {
                const count = diffCounts[dim.key] || 0;
                if (count === 0 && selectedDimensionFilter !== dim.key) return null;
                const isActive = selectedDimensionFilter === dim.key;
                return (
                  <button
                    key={dim.key}
                    type="button"
                    onClick={() => setSelectedDimensionFilter(dim.key)}
                    className="badge"
                    style={{ cursor: 'pointer', border: isActive ? '1px solid var(--color-brand)' : '1px solid var(--border-subtle)', color: isActive ? 'var(--color-brand)' : 'var(--text-secondary)' }}
                  >
                    {dim.name} ({count})
                  </button>
                );
              })}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            {filteredDifferences.map((diff, idx) => (
              <div key={diff.difference_id || idx} className="result-item" style={{ padding: '0.75rem' }}>
                <div className="result-title" style={{ marginBottom: '0.35rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: '0.84rem' }}>{(diff.attribute || diff.aspect || 'Attribute').replace('_', ' ')}</strong>
                    {diff.source_dimension && (
                      <span className="badge badge-section" style={{ fontSize: '0.7rem' }}>
                        {diff.source_dimension}
                      </span>
                    )}
                    <span
                      className="badge"
                      style={{
                        fontSize: '0.7rem',
                        background: diff.regulatory_impact === 'MAJOR' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.12)',
                        color: diff.regulatory_impact === 'MAJOR' ? 'var(--color-danger)' : 'var(--color-warning)',
                      }}
                    >
                      {diff.regulatory_impact || 'REVIEW'} IMPACT
                    </span>
                  </div>
                </div>

                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '0 0 0.5rem 0', lineHeight: 1.45 }}>
                  {diff.explanation}
                </p>

                <div className="grid-2" style={{ gap: '0.5rem' }}>
                  {diff.current_value && (
                    <div style={{ background: 'rgba(239, 68, 68, 0.06)', padding: '0.45rem', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                      <span style={{ fontSize: '0.68rem', color: 'var(--color-danger)', display: 'block' }}>Current Draft Value:</span>
                      <code style={{ fontSize: '0.78rem' }}>{diff.current_value}</code>
                    </div>
                  )}
                  {diff.candidate_value && (
                    <div style={{ background: 'rgba(21, 128, 61, 0.06)', padding: '0.45rem', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(21, 128, 61, 0.2)' }}>
                      <span style={{ fontSize: '0.68rem', color: 'var(--color-success)', display: 'block' }}>Candidate Reference Value:</span>
                      <code style={{ fontSize: '0.78rem' }}>{diff.candidate_value}</code>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 6. Human Decision Station — PROMINENT */}
      <div id="decision-station" className="card" style={{ marginBottom: '1.5rem', border: '2px solid var(--color-brand)' }}>
        <div className="card-header">
          <div>
            <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <ShieldCheck size={18} color="var(--color-brand)" /> Your Decision
            </span>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0 0' }}>
              The recommendation is advisory. Please review the evidence and record the final decision.
            </p>
          </div>
          <span className="status-pill">
            Human Decision Required
          </span>
        </div>

        {/* 3 Decision Choice Cards */}
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.5rem' }}>
            Select Action *
          </label>

          <div className="grid-3" style={{ gap: '0.85rem' }}>
            {/* REUSE Option */}
            <button
              type="button"
              onClick={() => {
                setSelectedDecision('REUSE');
                setDecisionValidationError(null);
              }}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                textAlign: 'center',
                padding: '1.25rem 1rem',
                borderRadius: 'var(--radius-md)',
                background: selectedDecision === 'REUSE' ? 'rgba(21, 128, 61, 0.08)' : '#ffffff',
                border: selectedDecision === 'REUSE' ? '2px solid var(--color-success)' : '1px solid var(--border-subtle)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {recommendedDecision === 'REUSE' && (
                <span className="badge" style={{ fontSize: '0.68rem', background: 'rgba(21, 128, 61, 0.15)', color: 'var(--color-success)', marginBottom: '0.4rem' }}>
                  Advisory Recommendation
                </span>
              )}
              <CheckCircle2 size={26} color={selectedDecision === 'REUSE' ? 'var(--color-success)' : 'var(--text-muted)'} />
              <strong style={{ fontSize: '1.05rem', color: selectedDecision === 'REUSE' ? 'var(--color-success)' : 'var(--text-primary)', marginTop: '0.4rem' }}>
                REUSE
              </strong>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '0.25rem', lineHeight: 1.35 }}>
                Direct adoption of validated external regulatory standard
              </span>
            </button>

            {/* ADAPT Option */}
            <button
              type="button"
              onClick={() => {
                setSelectedDecision('ADAPT');
                setDecisionValidationError(null);
              }}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                textAlign: 'center',
                padding: '1.25rem 1rem',
                borderRadius: 'var(--radius-md)',
                background: selectedDecision === 'ADAPT' ? 'rgba(180, 83, 9, 0.08)' : '#ffffff',
                border: selectedDecision === 'ADAPT' ? '2px solid var(--color-warning)' : '1px solid var(--border-subtle)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {recommendedDecision === 'ADAPT' && (
                <span className="badge" style={{ fontSize: '0.68rem', background: 'rgba(180, 83, 9, 0.15)', color: 'var(--color-warning)', marginBottom: '0.4rem' }}>
                  Advisory Recommendation
                </span>
              )}
              <Sliders size={26} color={selectedDecision === 'ADAPT' ? 'var(--color-warning)' : 'var(--text-muted)'} />
              <strong style={{ fontSize: '1.05rem', color: selectedDecision === 'ADAPT' ? 'var(--color-warning)' : 'var(--text-primary)', marginTop: '0.4rem' }}>
                ADAPT
              </strong>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '0.25rem', lineHeight: 1.35 }}>
                Modify candidate with product-specific clinical adaptations
              </span>
            </button>

            {/* REJECT Option */}
            <button
              type="button"
              onClick={() => {
                setSelectedDecision('REJECT');
                setDecisionValidationError(null);
              }}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                textAlign: 'center',
                padding: '1.25rem 1rem',
                borderRadius: 'var(--radius-md)',
                background: selectedDecision === 'REJECT' ? 'rgba(185, 28, 28, 0.08)' : '#ffffff',
                border: selectedDecision === 'REJECT' ? '2px solid var(--color-danger)' : '1px solid var(--border-subtle)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {recommendedDecision === 'REJECT' && (
                <span className="badge" style={{ fontSize: '0.68rem', background: 'rgba(185, 28, 28, 0.15)', color: 'var(--color-danger)', marginBottom: '0.4rem' }}>
                  Advisory Recommendation
                </span>
              )}
              <XCircle size={26} color={selectedDecision === 'REJECT' ? 'var(--color-danger)' : 'var(--text-muted)'} />
              <strong style={{ fontSize: '1.05rem', color: selectedDecision === 'REJECT' ? 'var(--color-danger)' : 'var(--text-primary)', marginTop: '0.4rem' }}>
                REJECT
              </strong>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '0.25rem', lineHeight: 1.35 }}>
                Decline candidate; retain current internal document wording
              </span>
            </button>
          </div>
        </div>

        {/* 7. ADAPT FLOW: Instructions Input */}
        {selectedDecision === 'ADAPT' && (
          <div style={{ marginBottom: '1.25rem', background: 'rgba(245, 158, 11, 0.06)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid rgba(245, 158, 11, 0.25)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--color-warning)' }}>
                Adaptation Instructions *
              </label>
              {proposedAdaptedText && !adaptationInstructions && (
                <button
                  type="button"
                  onClick={() => setAdaptationInstructions(proposedAdaptedText)}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.72rem', padding: '0.2rem 0.5rem', color: 'var(--color-warning)' }}
                >
                  Prefill with Advisory Proposal
                </button>
              )}
            </div>
            <textarea
              className="input-text"
              rows={3}
              placeholder="Specify clinical adjustments (e.g., adjust dosage range for renal impairment or align pediatric warning)..."
              value={adaptationInstructions}
              onChange={(e) => {
                setAdaptationInstructions(e.target.value);
                setDecisionValidationError(null);
              }}
              style={{ width: '100%', fontSize: '0.84rem' }}
            />
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginTop: '0.25rem' }}>
              Instructions recorded here guide downstream document changes.
            </span>
          </div>
        )}

        {/* Reviewer Details (Name & Rationale) */}
        <div className="grid-2" style={{ gap: '0.85rem', marginBottom: '1.25rem' }}>
          <div>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.3rem' }}>
              Reviewer Name & Title *
            </label>
            <input
              type="text"
              className="input-text"
              placeholder="e.g. Dr. Jane Doe, Senior Regulatory Specialist"
              value={reviewerName}
              onChange={(e) => {
                setReviewerName(e.target.value);
                setDecisionValidationError(null);
              }}
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.3rem' }}>
              Professional Rationale / Clinical Justification *
            </label>
            <textarea
              className="input-text"
              rows={2}
              placeholder="Document regulatory reasoning supporting your decision..."
              value={reviewerNotes}
              onChange={(e) => {
                setReviewerNotes(e.target.value);
                setDecisionValidationError(null);
              }}
              style={{ width: '100%', fontSize: '0.84rem' }}
            />
          </div>
        </div>

        {/* Validation Error Banner */}
        {decisionValidationError && (
          <div style={{ marginBottom: '1rem', padding: '0.7rem 0.9rem', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#b91c1c', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertCircle size={16} />
            <span>{decisionValidationError}</span>
          </div>
        )}

        {/* Submission Error Banner */}
        {decisionSubmitError && (
          <div style={{ marginBottom: '1rem', padding: '0.7rem 0.9rem', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid var(--color-danger)', borderRadius: 'var(--radius-sm)', color: '#b91c1c', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertCircle size={16} />
            <span>{decisionSubmitError}</span>
          </div>
        )}

        {/* Recorded Confirmation Block */}
        {recordedDecision && (
          <div style={{ marginBottom: '1.25rem', padding: '1rem', background: 'rgba(21, 128, 61, 0.08)', border: '1px solid rgba(21, 128, 61, 0.3)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-success)', fontWeight: 600, fontSize: '0.9rem' }}>
                <CheckCircle2 size={18} /> Decision Recorded Successfully
              </div>
              <span className="badge" style={getStatusStyle('MATCH')}>
                {recordedDecision.decision} AUTHORIZED
              </span>
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
              <span>Decision ID: <code>{recordedDecision.decision_id}</code></span>
              <span>Authorizing Reviewer: <strong>{recordedDecision.reviewer_name}</strong></span>
              {recordedDecision.reviewer_notes && <span>Rationale: {recordedDecision.reviewer_notes}</span>}
              {recordedDecision.adaptation_instructions && <span>Instructions: {recordedDecision.adaptation_instructions}</span>}
            </div>

            <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={handleProceedToChangeReview}
                className="btn btn-primary"
                style={{ fontSize: '0.84rem', padding: '0.45rem 1rem' }}
              >
                Proceed to Change Review <ArrowRight size={13} />
              </button>
            </div>
          </div>
        )}

        {/* Decision Submission Button */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            {!selectedDecision
              ? 'Select an action above to enable authorization'
              : `Selected: ${selectedDecision} (Click to record)`}
          </span>

          <button
            type="button"
            onClick={handleSubmitDecision}
            className="btn btn-primary"
            disabled={!selectedDecision || submittingDecision || !targetContentId || !candidateId}
            style={{ fontSize: '0.88rem', padding: '0.6rem 1.3rem', fontWeight: 600 }}
          >
            <Send size={14} /> {submittingDecision ? 'Recording Decision...' : 'Authorize & Record Decision'}
          </button>
        </div>
      </div>

      {/* 9. Technical Details (Secondary & Expandable) */}
      <div className="card" style={{ background: 'var(--bg-surface)' }}>
        <div
          onClick={() => setShowTraceabilityDetails(!showTraceabilityDetails)}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            cursor: 'pointer',
            userSelect: 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.84rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            {showTraceabilityDetails ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <span>View Technical & Audit Traceability Details</span>
          </div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            Session ID: <code>{analysisResult?.comparison_id || 'N/A'}</code>
          </span>
        </div>

        {showTraceabilityDetails && (
          <div style={{ marginTop: '1rem', paddingTop: '0.85rem', borderTop: '1px solid var(--border-subtle)', fontSize: '0.76rem' }}>
            <div className="grid-2" style={{ gap: '1rem' }}>
              <div style={{ background: 'var(--bg-surface-elevated)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <strong style={{ color: 'var(--color-brand)', display: 'block', marginBottom: '0.35rem' }}>
                  Target Content Provenance
                </strong>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', color: 'var(--text-secondary)' }}>
                  <span>Document ID: <code>{targetFacts?.target_document_id || targetSection?.document_id || 'N/A'}</code></span>
                  <span>Content ID: <code>{targetFacts?.target_content_id || targetSection?.content_id || 'N/A'}</code></span>
                  <span>Section: <strong>{targetFacts?.target_section || targetSection?.section || 'N/A'}</strong></span>
                  {targetFacts?.target_page !== undefined && targetFacts?.target_page !== null && <span>Page: {targetFacts.target_page}</span>}
                </div>
              </div>

              <div style={{ background: 'var(--bg-surface-elevated)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <strong style={{ color: 'var(--color-dailymed)', display: 'block', marginBottom: '0.35rem' }}>
                  Candidate Reference Provenance
                </strong>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', color: 'var(--text-secondary)' }}>
                  <span>Source Identifier: <code>{observedFacts?.source_identifier || selectedCandidate?.source_identifier || 'N/A'}</code></span>
                  <span>Content ID: <code>{observedFacts?.content_id || selectedCandidate?.content_id || 'N/A'}</code></span>
                  <span>Section: <strong>{observedFacts?.section || selectedCandidate?.section || 'N/A'}</strong></span>
                  {observedFacts?.cross_sources && observedFacts.cross_sources.length > 1 && (
                    <span>Corroboration: <strong>{observedFacts.cross_sources.join(', ')}</strong></span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
