import React, { useState } from 'react';
import {
  Layers,
  LayoutDashboard,
  FileText,
  GitCompare,
  CheckSquare,
  GitPullRequest,
  FileCheck2,
  Database
} from 'lucide-react';
import Dashboard from './components/Dashboard';
import DocumentReview from './components/DocumentReview';
import CandidateComparison from './components/CandidateComparison';
import DecisionPanel from './components/DecisionPanel';
import ChangeReview from './components/ChangeReview';
import ApprovedChangeReport from './components/ApprovedChangeReport';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [selectedSection, setSelectedSection] = useState(null);
  const [activeDecision, setActiveDecision] = useState(null);

  // Transition helper from Search/Dashboard to Comparison
  function handleSelectCandidateForComparison(candidate) {
    setSelectedCandidate(candidate);
    setActiveTab('comparison');
  }

  // Transition helper from Document Review to Comparison
  function handleSelectSectionForReview(section) {
    setSelectedSection(section);
    setActiveTab('comparison');
  }

  // Transition helper from Comparison to Decision Panel
  function handleProceedToDecision(data) {
    setSelectedCandidate(data.candidateItem);
    setActiveTab('decision');
  }

  // Transition helper from Decision Panel to Change Review
  function handleDecisionRecorded(decision) {
    setActiveDecision(decision);
    setActiveTab('changes');
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
            <p>Life Sciences Regulatory Affairs • V1 Foundation</p>
          </div>
        </div>

        {/* Core Regulatory Workflow Tabs */}
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
            className={`nav-tab ${activeTab === 'comparison' ? 'active' : ''}`}
          >
            <GitCompare size={15} /> Candidate Comparison
          </button>

          <button
            onClick={() => setActiveTab('decision')}
            className={`nav-tab ${activeTab === 'decision' ? 'active' : ''}`}
          >
            <CheckSquare size={15} /> Decision Panel
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
          />
        )}

        {activeTab === 'review' && (
          <DocumentReview
            onSelectSectionForReview={handleSelectSectionForReview}
          />
        )}

        {activeTab === 'comparison' && (
          <CandidateComparison
            targetSection={selectedSection}
            candidateItem={selectedCandidate}
            onProceedToDecision={handleProceedToDecision}
          />
        )}

        {activeTab === 'decision' && (
          <DecisionPanel
            comparisonData={{ targetSection: selectedSection, candidateItem: selectedCandidate }}
            onDecisionRecorded={handleDecisionRecorded}
          />
        )}

        {activeTab === 'changes' && (
          <ChangeReview
            activeDecision={activeDecision}
            onNavigateToReport={() => setActiveTab('report')}
          />
        )}

        {activeTab === 'report' && (
          <ApprovedChangeReport />
        )}
      </main>
    </div>
  );
}
