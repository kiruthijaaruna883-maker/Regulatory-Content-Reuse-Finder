import React, { useState, useRef } from 'react';
import {
  FileText,
  UploadCloud,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  Layers,
  Database
} from 'lucide-react';
import { api } from '../services/api';

const SAMPLE_INTERNAL_DRAFT = `INDICATIONS AND USAGE
This drug product is indicated for the acute relief of mild to moderate headache and muscular aches in adult patients aged 18 and older.

DOSAGE AND ADMINISTRATION
Adults: Take 1 tablet (500 mg) orally every 4 to 6 hours as needed with water. Do not exceed 6 tablets (3000 mg) within a 24-hour period unless instructed by a qualified physician.

CONTRAINDICATIONS
Do not administer to individuals with known severe hypersensitivity to active salicylates or patients with active bleeding peptic ulcers.`;

const ALLOWED_EXTENSIONS = [
  '.pdf',
  '.doc',
  '.docx',
  '.txt'
];

export default function DocumentReview({ onSelectSectionForReview }) {
  const [inputMode, setInputMode] = useState('paste'); // 'paste' | 'file'
  const [docName, setDocName] = useState('Draft Prescribing Information v1.2');
  const [docContent, setDocContent] = useState(SAMPLE_INTERNAL_DRAFT);
  const [selectedFile, setSelectedFile] = useState(null);
  const [jurisdiction, setJurisdiction] = useState('US_FDA');
  const [docType, setDocType] = useState('REGULATORY_LABEL');
  const [productName, setProductName] = useState('');
  const [activeIngredient, setActiveIngredient] = useState('');

  const [extractedSections, setExtractedSections] = useState([]);
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState(null);
  const [error, setError] = useState(null);
  const [activeSectionId, setActiveSectionId] = useState(null);

  const fileInputRef = useRef(null);

  function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setError(`Unsupported file format '${ext}'. Supported formats are: ${ALLOWED_EXTENSIONS.join(', ')}`);
      setSelectedFile(null);
      return;
    }

    setError(null);
    setSelectedFile(file);
    // Auto-populate document name if currently using default or empty
    if (!docName || docName === 'Draft Prescribing Information v1.2') {
      const cleanTitle = file.name.replace(/\.[^/.]+$/, '').replace(/[_.-]+/g, ' ');
      setDocName(cleanTitle.charAt(0).toUpperCase() + cleanTitle.slice(1));
    }
  }

  async function handleIngestDocument(e) {
    if (e) e.preventDefault();
    setError(null);

    // Validation
    const cleanDocName = (docName || '').trim();
    if (!cleanDocName) {
      setError('Document title/name is required.');
      return;
    }

    if (inputMode === 'file' && !selectedFile) {
      setError('Please select a regulatory document file to upload.');
      return;
    }

    if (inputMode === 'paste' && (!docContent || !docContent.trim())) {
      setError('Document content cannot be empty in paste mode.');
      return;
    }

    setIngesting(true);
    try {
      const formData = new FormData();
      if (inputMode === 'file') {
        formData.append('file', selectedFile);
      } else {
        formData.append('pasted_text', docContent.trim());
      }
      formData.append('document_name', cleanDocName);
      formData.append('jurisdiction', jurisdiction);
      formData.append('document_type', docType);
      if (productName.trim()) {
        formData.append('product_name', productName.trim());
      }
      if (activeIngredient.trim()) {
        formData.append('active_ingredient', activeIngredient.trim());
      }
      formData.append('version', '1.0');

      // Call API service without manual Content-Type header
      const result = await api.ingestDocument(formData);
      setIngestResult(result);

      // If text is available (paste mode), segment sections so reviewer can drill into specific sections
      if (inputMode === 'paste' && docContent.trim()) {
        try {
          const sections = await api.uploadDocument(cleanDocName, docContent.trim());
          const enriched = (sections || []).map((sec) => ({
            ...sec,
            document_id: result.document_id,
            document_name: result.document_name,
            jurisdiction: result.jurisdiction,
            document_type: result.document_type,
          }));
          setExtractedSections(enriched);
          if (enriched.length > 0) {
            setActiveSectionId(enriched[0].content_id);
          }
        } catch {
          // Non-blocking fallback if secondary segmentation fails
        }
      } else {
        // In file mode, clear prior text-segmented sections to avoid stale display
        setExtractedSections([]);
      }
    } catch (err) {
      setError(err.message || 'Document ingestion failed. Please verify format and contents.');
    } finally {
      setIngesting(false);
    }
  }

  return (
    <div>
      <div className="screen-header">
        <div>
          <h2>Document Review Workspace</h2>
          <p>Ingest internal regulatory drafts and register candidate content for reuse discovery</p>
        </div>
      </div>

      <div className="grid-2">
        {/* Document Ingestion & Metadata Column */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <FileText size={16} /> Regulatory Document Ingestion
            </span>
            <button
              onClick={handleIngestDocument}
              className="btn btn-primary"
              style={{ fontSize: '0.82rem', padding: '0.4rem 0.9rem' }}
              disabled={ingesting}
            >
              <UploadCloud size={14} /> {ingesting ? 'Ingesting...' : 'Ingest Document'}
            </button>
          </div>

          {/* Mode Switcher Tabs */}
          <div className="nav-tabs" style={{ marginBottom: '1rem', width: 'fit-content' }}>
            <button
              type="button"
              className={`nav-tab ${inputMode === 'paste' ? 'active' : ''}`}
              onClick={() => { setInputMode('paste'); setError(null); }}
            >
              <FileText size={14} /> Paste Text
            </button>
            <button
              type="button"
              className={`nav-tab ${inputMode === 'file' ? 'active' : ''}`}
              onClick={() => { setInputMode('file'); setError(null); }}
            >
              <UploadCloud size={14} /> Upload File
            </button>
          </div>

          {/* Error Banner */}
          {error && (
            <div style={{
              marginBottom: '1rem',
              padding: '0.75rem 1rem',
              background: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 'var(--radius-sm)',
              color: '#fca5a5',
              fontSize: '0.82rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}>
              <AlertTriangle size={16} color="var(--color-danger)" style={{ flexShrink: 0 }} />
              <span>{error}</span>
            </div>
          )}

          {/* File Upload Mode */}
          {inputMode === 'file' ? (
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
                Regulatory Document File (.pdf, .doc, .docx, .txt)
              </label>
              <div
                style={{
                  border: '2px dashed var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: '1.75rem 1rem',
                  textAlign: 'center',
                  background: 'var(--bg-main)',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s ease'
                }}
                onClick={() => fileInputRef.current?.click()}
              >
                <UploadCloud size={30} color="var(--color-brand)" style={{ margin: '0 auto 0.5rem' }} />
                <div style={{ fontSize: '0.88rem', color: '#fff', fontWeight: '500' }}>
                  {selectedFile ? selectedFile.name : 'Click to select regulatory document file'}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>
                  Supported formats: PDF, DOC, DOCX, TXT
                </div>
                {selectedFile && (
                  <div style={{ marginTop: '0.6rem', fontSize: '0.78rem', color: 'var(--color-success)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }}>
                    <CheckCircle2 size={13} /> {(selectedFile.size / 1024).toFixed(1)} KB ready for ingestion
                  </div>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.doc,.docx,.txt"
                  style={{ display: 'none' }}
                  onChange={handleFileChange}
                />
              </div>
            </div>
          ) : (
            /* Pasted Text Mode */
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
                Document Content (Regulatory Text)
              </label>
              <textarea
                className="input-text"
                rows={9}
                value={docContent}
                onChange={(e) => setDocContent(e.target.value)}
                placeholder="Paste regulatory text, prescribing information, or SmPC sections here..."
                style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem', resize: 'vertical' }}
              />
            </div>
          )}

          {/* Metadata Section */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.85rem', marginTop: '0.5rem' }}>
            <div style={{ marginBottom: '0.75rem' }}>
              <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
                Document Title / Name *
              </label>
              <input
                type="text"
                className="input-text"
                value={docName}
                onChange={(e) => setDocName(e.target.value)}
                style={{ width: '100%' }}
                placeholder="e.g. Draft Prescribing Information v1.2"
              />
            </div>

            <div className="grid-2" style={{ gap: '0.75rem', marginBottom: '0.75rem' }}>
              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
                  Regulatory Jurisdiction
                </label>
                <select
                  className="select-box"
                  value={jurisdiction}
                  onChange={(e) => setJurisdiction(e.target.value)}
                  style={{ width: '100%' }}
                >
                  <option value="US_FDA">US_FDA (United States FDA)</option>
                  <option value="EMA">EMA (European Medicines Agency)</option>
                  <option value="PMDA">PMDA (Japan PMDA)</option>
                  <option value="Health_Canada">Health_Canada (Health Canada)</option>
                  <option value="ICH">ICH (International Harmonisation)</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
                  Document Type
                </label>
                <select
                  className="select-box"
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  style={{ width: '100%' }}
                >
                  <option value="REGULATORY_LABEL">REGULATORY_LABEL (Prescribing Info / SPL)</option>
                  <option value="SmPC">SmPC (Summary of Product Characteristics)</option>
                  <option value="PRESCRIBING_INFORMATION">PRESCRIBING_INFORMATION (Full Label)</option>
                  <option value="CLINICAL_OVERVIEW">CLINICAL_OVERVIEW (Module 2.5)</option>
                </select>
              </div>
            </div>

            <div className="grid-2" style={{ gap: '0.75rem' }}>
              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
                  Product Name (Optional)
                </label>
                <input
                  type="text"
                  className="input-text"
                  value={productName}
                  onChange={(e) => setProductName(e.target.value)}
                  placeholder="e.g. Cardiovax"
                  style={{ width: '100%' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem' }}>
                  Active Ingredient (Optional)
                </label>
                <input
                  type="text"
                  className="input-text"
                  value={activeIngredient}
                  onChange={(e) => setActiveIngredient(e.target.value)}
                  placeholder="e.g. Acetylsalicylic acid"
                  style={{ width: '100%' }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Ingestion Response & Segmented Review Column */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              <CheckCircle2 size={16} color="var(--color-brand)" /> Ingestion Status & Content Chunks
            </span>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              {ingestResult ? 'Store Registered' : 'Awaiting Ingestion'}
            </span>
          </div>

          {/* Ingestion Response Summary Card */}
          {ingestResult && (
            <div style={{
              marginBottom: '1rem',
              padding: '0.9rem',
              background: 'rgba(14, 165, 233, 0.08)',
              border: '1px solid rgba(14, 165, 233, 0.25)',
              borderRadius: 'var(--radius-md)'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#fff', fontWeight: '600', fontSize: '0.86rem' }}>
                  <ShieldCheck size={16} color="var(--color-brand)" /> Document Ingestion Confirmed
                </span>
                <span className="status-pill">
                  <span className="status-dot" /> Registered
                </span>
              </div>

              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.7rem' }}>
                {ingestResult.message}
              </p>

              <div className="grid-3" style={{ gap: '0.4rem', marginBottom: '0.5rem' }}>
                <div style={{ background: 'var(--bg-main)', padding: '0.45rem', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>DOCUMENT ID</span>
                  <code style={{ fontSize: '0.78rem', color: 'var(--color-brand)' }}>{ingestResult.document_id}</code>
                </div>
                <div style={{ background: 'var(--bg-main)', padding: '0.45rem', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>JURISDICTION</span>
                  <strong style={{ fontSize: '0.78rem', color: '#fff' }}>{ingestResult.jurisdiction}</strong>
                </div>
                <div style={{ background: 'var(--bg-main)', padding: '0.45rem', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>DOCUMENT TYPE</span>
                  <strong style={{ fontSize: '0.78rem', color: '#fff' }}>{ingestResult.document_type}</strong>
                </div>
              </div>

              <div className="grid-2" style={{ gap: '0.4rem', marginBottom: '0.5rem' }}>
                <div style={{ background: 'var(--bg-main)', padding: '0.45rem', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>SECTIONS PARSED</span>
                  <strong style={{ fontSize: '0.95rem', color: '#fff' }}>{ingestResult.sections_count}</strong>
                </div>
                <div style={{ background: 'var(--bg-main)', padding: '0.45rem', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>CANDIDATE CHUNKS REGISTERED</span>
                  <strong style={{ fontSize: '0.95rem', color: ingestResult.chunks_count > 0 ? 'var(--color-success)' : 'var(--color-warning)' }}>
                    {ingestResult.chunks_count}
                  </strong>
                </div>
              </div>

              {/* Direct action button to compare with document if sections list is empty (e.g. binary upload) */}
              {extractedSections.length === 0 && (
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.75rem' }}>
                  <button
                    onClick={() => onSelectSectionForReview && onSelectSectionForReview({
                      content_id: `${ingestResult.document_id}_item`,
                      document_id: ingestResult.document_id,
                      document_name: ingestResult.document_name,
                      section: 'Ingested Document Draft',
                      text: selectedFile ? `File: ${selectedFile.name} (Registered ${ingestResult.chunks_count} chunks in store)` : docContent,
                      jurisdiction: ingestResult.jurisdiction,
                      document_type: ingestResult.document_type,
                    })}
                    className="btn btn-primary"
                    style={{ fontSize: '0.78rem', padding: '0.4rem 0.8rem' }}
                  >
                    Compare Ingested Content <ArrowRight size={12} />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Structured Sections List (Paste Mode) */}
          {extractedSections.length > 0 ? (
            <div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.6rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <Layers size={13} color="var(--color-brand)" /> Structured Sections Ready for Comparison ({extractedSections.length}):
              </div>
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
          ) : !ingestResult ? (
            <div className="empty-state">
              <Database size={36} />
              <p>Choose <strong>Upload File</strong> or <strong>Paste Text</strong>, review metadata, and click <strong>"Ingest Document"</strong> to parse sections and register chunks in the candidate store.</p>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
