import React, { useState } from 'react';
import { FileText, UploadCloud, Search, ArrowRight, CheckCircle2 } from 'lucide-react';
import { api } from '../services/api';

const SAMPLE_INTERNAL_DRAFT = `INDICATIONS AND USAGE
This drug product is indicated for the acute relief of mild to moderate headache and muscular aches in adult patients aged 18 and older.

DOSAGE AND ADMINISTRATION
Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours as needed with water. Do not exceed 6 tablets (3000 mg) within a 24-hour period unless instructed by a qualified physician.

CONTRAINDICATIONS
Do not administer to individuals with known severe hypersensitivity to active salicylates or patients with active bleeding peptic ulcers.`;

export default function DocumentReview({ onSelectSectionForReview }) {
  const [docName, setDocName] = useState('Draft Prescribing Information v1.2');
  const [docContent, setDocContent] = useState(SAMPLE_INTERNAL_DRAFT);
  const [extractedSections, setExtractedSections] = useState([]);
  const [parsing, setParsing] = useState(false);
  const [activeSectionId, setActiveSectionId] = useState(null);

  async function handleExtractSections() {
    setParsing(true);
    try {
      const sections = await api.uploadDocument(docName, docContent);
      setExtractedSections(sections);
      if (sections.length > 0) {
        setActiveSectionId(sections[0].content_id);
      }
    } catch (err) {
      alert(`Parsing failed: ${err.message}`);
    } finally {
      setParsing(false);
    }
  }

  return (
    <div>
      <div className="screen-header">
        <div>
          <h2>Document Review Workspace</h2>
          <p>Extract and evaluate internal draft sections alongside live external regulatory precedents</p>
        </div>
      </div>

      <div className="grid-2">
        {/* Document Input & Editor */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <FileText size={16} /> Regulatory Draft Document
            </span>
            <button
              onClick={handleExtractSections}
              className="btn btn-primary"
              style={{ fontSize: '0.82rem', padding: '0.4rem 0.8rem' }}
              disabled={parsing}
            >
              <UploadCloud size={14} /> {parsing ? 'Segmenting...' : 'Segment Sections'}
            </button>
          </div>

          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
              Document Title
            </label>
            <input
              type="text"
              className="input-text"
              value={docName}
              onChange={(e) => setDocName(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
              Document Content (Regulatory Text)
            </label>
            <textarea
              className="input-text"
              rows={14}
              value={docContent}
              onChange={(e) => setDocContent(e.target.value)}
              style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem', resize: 'vertical' }}
            />
          </div>
        </div>

        {/* Segmented Sections & Candidate Triggers */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <CheckCircle2 size={16} color="var(--color-brand)" /> Structured Sections ({extractedSections.length})
            </span>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              Ready for Reuse Analysis
            </span>
          </div>

          {extractedSections.length === 0 ? (
            <div className="empty-state">
              <FileText size={36} />
              <p>Click <strong>"Segment Sections"</strong> to automatically extract standard regulatory sections from the draft.</p>
            </div>
          ) : (
            <div>
              {extractedSections.map((sec) => (
                <div
                  key={sec.content_id}
                  className="result-item"
                  style={{
                    borderColor: activeSectionId === sec.content_id ? 'var(--color-brand)' : 'var(--border-subtle)',
                    background: activeSectionId === sec.content_id ? 'var(--bg-surface-elevated)' : 'var(--bg-main)'
                  }}
                  onClick={() => setActiveSectionId(sec.content_id)}
                >
                  <div className="result-title">
                    <span>{sec.section || 'General Section'}</span>
                    <span className="badge badge-section">{sec.content_id}</span>
                  </div>
                  <div className="result-text" style={{ maxHeight: '80px', marginBottom: '0.6rem' }}>
                    {sec.text}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                      onClick={() => onSelectSectionForReview && onSelectSectionForReview(sec)}
                      className="btn btn-secondary"
                      style={{ fontSize: '0.78rem', padding: '0.35rem 0.75rem' }}
                    >
                      Find Reusable Candidates <ArrowRight size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
