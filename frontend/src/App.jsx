import React, { useState } from 'react';
import {
  Layers,
  LayoutDashboard,
  FileText,
  GitCompare,
  GitPullRequest,
  FileCheck2
} from 'lucide-react';
import Dashboard from './components/Dashboard';
import DocumentReview from './components/DocumentReview';
import CandidateComparison from './components/CandidateComparison';
import ChangeReview from './components/ChangeReview';
import ApprovedChangeReport from './components/ApprovedChangeReport';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [selectedSection, setSelectedSection] = useState(null);
  const [activeSourceDocument, setActiveSourceDocument] = useState(null);
  const [activeDecision, setActiveDecision] = useState(null);
  const [comparisonContext, setComparisonContext] = useState(null);
  const [approvedReport, setApprovedReport] = useState(null);

  // Transition helper from Search/Dashboard to Comparison & Decision
  function handleSelectCandidateForComparison(candidate) {
    setSelectedCandidate(candidate);
    setActiveTab('comparison');
  }

  // Callback from DocumentReview upon successful document ingestion/upload
  function handleDocumentIngested(docData) {
    if (docData) {
      setActiveSourceDocument({
        document_id: docData.document_id,
        document_fingerprint: docData.document_fingerprint,
        document_name: docData.document_name,
        sections: docData.sections || [],
        jurisdiction: docData.jurisdiction,
        document_type: docData.document_type,
      });
    }
  }

  // Transition helper from Document Review to Comparison & Decision
  function handleSelectSectionForReview(section) {
    setSelectedSection(section);
    setActiveTab('comparison');
  }

  // Transition helper for legacy onProceedToDecision (kept for backward compatibility)
  function handleProceedToDecision(data) {
    const candidate = data.candidateItem || null;
    setSelectedCandidate(candidate);
    if (data) {
      setComparisonContext({
        targetText: data.targetText || null,
        candidateText: data.candidateText || null,
        differences: data.differences || [],
        candidateItem: candidate,
        analysisResult: data.analysisResult || null,
        targetSection: selectedSection || (data.analysisResult?.target_section ? {
          section: data.analysisResult.target_section,
          document_name: data.analysisResult.target_document_name,
          document_id: data.analysisResult.target_document_id,
          content_id: data.analysisResult.target_content_id,
          subsection: data.analysisResult.target_subsection,
          location: data.analysisResult.target_location,
          page: data.analysisResult.target_page,
          content_type: data.analysisResult.target_content_type,
          text: data.targetText,
        } : null),
      });
    }
    setActiveTab('comparison');
  }

  // Transition helper from Comparison & Decision to Change Review
  function handleDecisionRecorded(decision, extraContext = null) {
    setActiveDecision(decision);
    if (extraContext) {
      setComparisonContext((prev) => ({ ...prev, ...extraContext }));
    }
    setActiveTab('changes');
  }

  // Transition helper from Change Review to Approved Change Report
  function handleReportApproved(report) {
    setApprovedReport(report);
    setActiveTab('report');
  }

  return (
    <div className="app-container">
      {/* Top Navigation Bar */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">
            <Layers size={18} />
          </div>
          <div className="brand-title-group">
            <h1>Regulatory Content Reuse Finder</h1>
            <p>Life Sciences Regulatory Affairs</p>
          </div>
        </div>

        {/* Core Regulatory Workflow Tabs (Phase 6G.5 Consolidated to 5 Stages) */}
        <nav className="nav-tabs">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
          >
            <LayoutDashboard size={15} /> Dashboard
          </button>

          <button
            onClick={() => setActiveTab('review')}
            className={`nav-tab ${activeTab === 'review' ? 'active' : ''}`}
          >
            <FileText size={15} /> Document Review
          </button>

          <button
            onClick={() => setActiveTab('comparison')}
            className={`nav-tab ${activeTab === 'comparison' || activeTab === 'decision' ? 'active' : ''}`}
          >
            <GitCompare size={15} /> Candidate Comparison & Decision
          </button>

          <button
            onClick={() => setActiveTab('changes')}
            className={`nav-tab ${activeTab === 'changes' ? 'active' : ''}`}
          >
            <GitPullRequest size={15} /> Change Review
          </button>

          <button
            onClick={() => setActiveTab('report')}
            className={`nav-tab ${activeTab === 'report' ? 'active' : ''}`}
          >
            <FileCheck2 size={15} /> Approved Change Report
          </button>
        </nav>

        {/* Live System Indicator */}
        <div className="system-status">
          <div className="status-pill">
            <span className="status-dot" />
            <span>DailyMed & openFDA Live</span>
          </div>
        </div>
      </header>

      {/* Main Workflow View */}
      <main className="main-content">
        {activeTab === 'dashboard' && (
          <Dashboard
            onSelectCandidateForComparison={handleSelectCandidateForComparison}
            onNavigateTab={setActiveTab}
          />
        )}

        {activeTab === 'review' && (
          <DocumentReview
            onSelectSectionForReview={handleSelectSectionForReview}
            onDocumentIngested={handleDocumentIngested}
          />
        )}

        {(activeTab === 'comparison' || activeTab === 'decision') && (
          <CandidateComparison
            targetSection={selectedSection}
            candidateItem={selectedCandidate}
            activeSourceDocument={activeSourceDocument}
            onProceedToDecision={handleProceedToDecision}
            onDecisionRecorded={handleDecisionRecorded}
          />
        )}

        {activeTab === 'changes' && (
          <ChangeReview
            activeDecision={activeDecision}
            comparisonContext={comparisonContext}
            onReportApproved={handleReportApproved}
          />
        )}

        {activeTab === 'report' && (
          <ApprovedChangeReport
            approvedReport={approvedReport}
          />
        )}
      </main>
    </div>
  );
}
