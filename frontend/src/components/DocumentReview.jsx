import React, { useState, useRef, useEffect } from 'react';
import {
  FileText,
  UploadCloud,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Layers,
  ChevronDown,
  ChevronRight,
  File,
  X
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

export default function DocumentReview({
  activeSourceDocument,
  selectedSection,
  onSelectSectionForReview,
  onDocumentIngested,
}) {
  // Upload is the primary / default mode
  const [inputMode, setInputMode] = useState('file'); // 'file' | 'paste'
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);

  // Document metadata
  const [docName, setDocName] = useState(activeSourceDocument?.document_name || 'Draft Prescribing Information v1.2');
  const [docContent, setDocContent] = useState(SAMPLE_INTERNAL_DRAFT);
  const [jurisdiction, setJurisdiction] = useState(activeSourceDocument?.jurisdiction || 'US_FDA');
  const [docType, setDocType] = useState(activeSourceDocument?.document_type || 'REGULATORY_LABEL');
  const [productName, setProductName] = useState('');
  const [activeIngredient, setActiveIngredient] = useState('');

  // Processing & Ingestion states
  const [extractedSections, setExtractedSections] = useState(activeSourceDocument?.sections || []);
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState(() => {
    if (!activeSourceDocument?.document_id) return null;
    return {
      document_id: activeSourceDocument.document_id,
      document_fingerprint: activeSourceDocument.document_fingerprint,
      document_name: activeSourceDocument.document_name,
      jurisdiction: activeSourceDocument.jurisdiction,
      document_type: activeSourceDocument.document_type,
      sections_count: activeSourceDocument.sections_count || activeSourceDocument.sections?.length || 0,
      chunks_count: activeSourceDocument.chunks_count || activeSourceDocument.sections?.length || 0,
    };
  });
  const [error, setError] = useState(null);
  const [activeSectionId, setActiveSectionId] = useState(selectedSection?.content_id || activeSourceDocument?.sections?.[0]?.content_id || null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const fileInputRef = useRef(null);

  // Synchronize state when activeSourceDocument or selectedSection props change
  const [prevSourceDoc, setPrevSourceDoc] = useState(activeSourceDocument);
  const [prevSelectedSec, setPrevSelectedSec] = useState(selectedSection);
  if (activeSourceDocument !== prevSourceDoc || selectedSection !== prevSelectedSec) {
    setPrevSourceDoc(activeSourceDocument);
    setPrevSelectedSec(selectedSection);
    if (activeSourceDocument?.document_name) {
      setDocName(activeSourceDocument.document_name);
    }
    if (activeSourceDocument?.jurisdiction) {
      setJurisdiction(activeSourceDocument.jurisdiction);
    }
    if (activeSourceDocument?.document_type) {
      setDocType(activeSourceDocument.document_type);
    }
    if (activeSourceDocument?.document_id) {
      setIngestResult({
        document_id: activeSourceDocument.document_id,
        document_fingerprint: activeSourceDocument.document_fingerprint,
        document_name: activeSourceDocument.document_name,
        jurisdiction: activeSourceDocument.jurisdiction,
        document_type: activeSourceDocument.document_type,
        sections_count: activeSourceDocument.sections_count || activeSourceDocument.sections?.length || 0,
        chunks_count: activeSourceDocument.chunks_count || activeSourceDocument.sections?.length || 0,
      });
    }
    if (Array.isArray(activeSourceDocument?.sections) && activeSourceDocument.sections.length > 0) {
      setExtractedSections(activeSourceDocument.sections);
      setActiveSectionId(selectedSection?.content_id || activeSourceDocument.sections[0].content_id);
    }
  }

  // On-demand fetch if active document has an ID but sections array is empty in session
  useEffect(() => {
    if (!activeSourceDocument?.document_id) return;
    if (Array.isArray(activeSourceDocument.sections) && activeSourceDocument.sections.length > 0) return;

    let isSubscribed = true;
    api.getDocument(activeSourceDocument.document_id)
      .then((doc) => {
        if (!isSubscribed) return;
        if (doc?.sections && doc.sections.length > 0) {
          setExtractedSections(doc.sections);
          setActiveSectionId(selectedSection?.content_id || doc.sections[0].content_id);
        }
      })
      .catch((fetchErr) => {
        console.warn('Could not rehydrate document sections from session:', fetchErr);
      });

    return () => {
      isSubscribed = false;
    };
  }, [activeSourceDocument?.document_id, activeSourceDocument?.sections, selectedSection?.content_id]);

  function processFile(file) {
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

  function handleFileChange(e) {
    const file = e.target.files?.[0];
    processFile(file);
  }

  function handleDragOver(e) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    processFile(file);
  }

  function handleRemoveFile(e) {
    e.stopPropagation();
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
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

      // Call API service
      const result = await api.ingestDocument(formData);
      setIngestResult(result);

      // If backend returned parsed sections (from file or paste), populate extractedSections directly
      if (result.sections && result.sections.length > 0) {
        const enriched = result.sections.map((sec) => ({
          ...sec,
          document_id: result.document_id,
          document_fingerprint: result.document_fingerprint || sec.document_fingerprint,
          document_name: result.document_name,
          jurisdiction: result.jurisdiction,
          document_type: result.document_type,
        }));
        setExtractedSections(enriched);
        setActiveSectionId(enriched[0].content_id);
        if (onDocumentIngested) {
          onDocumentIngested({
            document_id: result.document_id,
            document_fingerprint: result.document_fingerprint,
            document_name: result.document_name,
            sections: enriched,
            jurisdiction: result.jurisdiction,
            document_type: result.document_type,
          });
        }
      } else if (inputMode === 'paste' && docContent.trim()) {
        try {
          const sections = await api.uploadDocument(cleanDocName, docContent.trim());
          const docId = result?.document_id || sections?.[0]?.document_id;
          const docFp = result?.document_fingerprint || sections?.[0]?.document_fingerprint;
          const enriched = (sections || []).map((sec) => ({
            ...sec,
            document_id: docId || sec.document_id,
            document_fingerprint: docFp || sec.document_fingerprint,
            document_name: result?.document_name || cleanDocName,
            jurisdiction: result?.jurisdiction || jurisdiction,
            document_type: result?.document_type || docType,
          }));
          setExtractedSections(enriched);
          if (enriched.length > 0) {
            setActiveSectionId(enriched[0].content_id);
          }
          if (onDocumentIngested) {
            onDocumentIngested({
              document_id: docId,
              document_fingerprint: docFp,
              document_name: result?.document_name || cleanDocName,
              sections: enriched,
              jurisdiction: result?.jurisdiction || jurisdiction,
              document_type: result?.document_type || docType,
            });
          }
        } catch {
          // Non-blocking fallback if secondary segmentation fails
        }
      } else {
        setExtractedSections([]);
      }
    } catch (err) {
      setError(err.message || 'Document ingestion failed. Please verify format and contents.');
    } finally {
      setIngesting(false);
    }
  }

  function handleProceedToReview(targetSection = null) {
    if (!onSelectSectionForReview || !ingestResult) return;

    if (targetSection) {
      onSelectSectionForReview(targetSection);
      return;
    }

    if (extractedSections.length > 0) {
      const selected = extractedSections.find(s => s.content_id === activeSectionId) || extractedSections[0];
      onSelectSectionForReview(selected);
      return;
    }

    // Fail clearly rather than fabricating synthetic target text
    setError('No source document section available for review. Please select or verify an extracted section.');
  }

  return (
    <div>
      {/* Screen Header */}
      <div className="screen-header" style={{ marginBottom: '1.5rem' }}>
        <div>
          <h2>Document Review</h2>
          <p>
            Upload the regulatory document you want to review for reusable content across approved health authority labels.
          </p>
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div style={{
          marginBottom: '1.25rem',
          padding: '0.85rem 1rem',
          background: 'rgba(239, 68, 68, 0.12)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 'var(--radius-sm)',
          color: '#b91c1c',
          fontSize: '0.84rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.6rem'
        }}>
          <AlertTriangle size={18} color="var(--color-danger)" style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      <div className="grid-2">
        {/* Left Column: Primary Upload & Metadata */}
        <div>
          {/* Card: Document Upload */}
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="card-header" style={{ paddingBottom: '0.6rem' }}>
              <span className="card-title">
                <UploadCloud size={16} color="var(--color-brand)" /> Upload Document
              </span>
              <div className="nav-tabs" style={{ padding: '0.15rem' }}>
                <button
                  type="button"
                  className={`nav-tab ${inputMode === 'file' ? 'active' : ''}`}
                  onClick={() => { setInputMode('file'); setError(null); }}
                  style={{ fontSize: '0.78rem', padding: '0.3rem 0.65rem' }}
                >
                  <UploadCloud size={13} /> Upload File
                </button>
                <button
                  type="button"
                  className={`nav-tab ${inputMode === 'paste' ? 'active' : ''}`}
                  onClick={() => { setInputMode('paste'); setError(null); }}
                  style={{ fontSize: '0.78rem', padding: '0.3rem 0.65rem' }}
                >
                  <FileText size={13} /> Paste Text
                </button>
              </div>
            </div>

            {/* Mode 1: Primary File Upload Area */}
            {inputMode === 'file' ? (
              <div>
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    border: isDragging ? '2px dashed var(--color-brand)' : '2px dashed var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: '2rem 1.5rem',
                    textAlign: 'center',
                    background: isDragging ? 'rgba(13, 148, 136, 0.05)' : 'var(--bg-surface-elevated)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <UploadCloud
                    size={38}
                    color="var(--color-brand)"
                    style={{ margin: '0 auto 0.75rem', display: 'block' }}
                  />

                  <div style={{ fontSize: '0.98rem', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '0.3rem' }}>
                    {selectedFile ? 'Document Selected' : 'Drop a document here'}
                  </div>

                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0 0 1rem 0' }}>
                    or click to choose a document from your computer
                  </p>

                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ fontSize: '0.82rem', padding: '0.45rem 1rem' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      fileInputRef.current?.click();
                    }}
                  >
                    <File size={14} /> Choose Document
                  </button>

                  <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '1rem', letterSpacing: '0.02em' }}>
                    PDF • DOC • DOCX • TXT
                  </div>

                  {selectedFile && (
                    <div
                      style={{
                        marginTop: '1rem',
                        padding: '0.65rem 0.9rem',
                        background: 'rgba(21, 128, 61, 0.08)',
                        border: '1px solid rgba(21, 128, 61, 0.25)',
                        borderRadius: 'var(--radius-sm)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        textAlign: 'left'
                      }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
                        <FileText size={16} color="var(--color-success)" style={{ flexShrink: 0 }} />
                        <div style={{ minWidth: 0 }}>
                          <strong style={{ fontSize: '0.84rem', color: 'var(--text-primary)', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {selectedFile.name}
                          </strong>
                          <span style={{ fontSize: '0.74rem', color: 'var(--color-success)' }}>
                            ✓ {(selectedFile.size / 1024).toFixed(1)} KB — Ready for review
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={handleRemoveFile}
                        style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '0.2rem' }}
                        title="Remove file"
                      >
                        <X size={15} />
                      </button>
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
              /* Mode 2: Secondary Paste Text Area */
              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.4rem', fontWeight: 500 }}>
                  Paste Regulatory Draft Text
                </label>
                <textarea
                  className="input-text"
                  rows={8}
                  value={docContent}
                  onChange={(e) => setDocContent(e.target.value)}
                  placeholder="Paste regulatory text, prescribing information, or SmPC sections here..."
                  style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.84rem', resize: 'vertical' }}
                />
              </div>
            )}
          </div>

          {/* Card: Document Information (Grouped Metadata) */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">
                <FileText size={16} color="var(--color-brand)" /> Document Information
              </span>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                Required for regulatory ingestion
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.3rem' }}>
                  Document Name *
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

              <div className="grid-2" style={{ gap: '0.85rem' }}>
                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.3rem' }}>
                    Jurisdiction
                  </label>
                  <select
                    className="select-box"
                    value={jurisdiction}
                    onChange={(e) => setJurisdiction(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="US_FDA">US FDA (United States)</option>
                    <option value="EMA">EMA (European Union)</option>
                    <option value="PMDA">PMDA (Japan)</option>
                    <option value="Health_Canada">Health Canada</option>
                    <option value="ICH">ICH (International)</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.3rem' }}>
                    Document Type
                  </label>
                  <select
                    className="select-box"
                    value={docType}
                    onChange={(e) => setDocType(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="REGULATORY_LABEL">Regulatory Label (Prescribing Info / SPL)</option>
                    <option value="SmPC">SmPC (Summary of Product Characteristics)</option>
                    <option value="PRESCRIBING_INFORMATION">Prescribing Information (Full Label)</option>
                    <option value="CLINICAL_OVERVIEW">Clinical Overview (Module 2.5)</option>
                  </select>
                </div>
              </div>

              <div className="grid-2" style={{ gap: '0.85rem' }}>
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

              <div style={{ marginTop: '0.5rem', display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={handleIngestDocument}
                  className="btn btn-primary"
                  style={{
                    fontSize: '0.9rem',
                    padding: '0.65rem 1.4rem',
                    fontWeight: 600,
                    boxShadow: '0 2px 10px rgba(13, 148, 136, 0.25)',
                  }}
                  disabled={ingesting}
                >
                  <UploadCloud size={16} /> {ingesting ? 'Processing Document...' : 'Ingest Document'}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Ingestion Status & Review Actions */}
        <div>
          {ingestResult ? (
            /* After Ingestion: Business-Friendly Result */
            <div className="card">
              <div
                style={{
                  padding: '1.25rem',
                  background: 'linear-gradient(135deg, rgba(21, 128, 61, 0.08) 0%, rgba(13, 148, 136, 0.08) 100%)',
                  border: '1px solid rgba(21, 128, 61, 0.25)',
                  borderRadius: 'var(--radius-md)',
                  marginBottom: '1.25rem'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                  <CheckCircle2 size={20} color="var(--color-success)" />
                  <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                    Document Ready for Review
                  </h3>
                </div>

                <p style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', margin: '0 0 1rem 0' }}>
                  {ingestResult.document_name ? (
                    <>Active Document: <strong>{ingestResult.document_name}</strong> registered for regulatory reuse analysis.</>
                  ) : (
                    'Your document was successfully processed and registered for regulatory reuse analysis.'
                  )}
                </p>

                <div className="grid-2" style={{ gap: '0.75rem', marginBottom: '1.25rem' }}>
                  <div style={{ background: '#ffffff', padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Sections Identified
                    </div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.1rem' }}>
                      {ingestResult.sections_count}
                    </div>
                  </div>

                  <div style={{ background: '#ffffff', padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Content Sections Available
                    </div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--color-brand)', marginTop: '0.1rem' }}>
                      {ingestResult.chunks_count}
                    </div>
                  </div>
                </div>

                {/* Primary CTA: Find Reusable Content */}
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <button
                    onClick={() => handleProceedToReview()}
                    className="btn btn-primary"
                    style={{
                      fontSize: '0.94rem',
                      padding: '0.7rem 1.4rem',
                      fontWeight: 600,
                      boxShadow: '0 4px 12px rgba(13, 148, 136, 0.3)'
                    }}
                  >
                    Find Reusable Content <ArrowRight size={16} />
                  </button>
                </div>
              </div>

              {/* Structured Sections if available (e.g. Paste mode) */}
              {extractedSections.length > 0 && (
                <div style={{ marginBottom: '1.25rem' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.65rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Layers size={14} color="var(--color-brand)" /> Sections Identified for Review ({extractedSections.length}):
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                    {extractedSections.map((sec) => (
                      <div
                        key={sec.content_id}
                        className="result-item"
                        style={{
                          borderColor: activeSectionId === sec.content_id ? 'var(--color-brand)' : 'var(--border-subtle)',
                          background: activeSectionId === sec.content_id ? 'var(--bg-surface-elevated)' : 'var(--bg-surface)'
                        }}
                        onClick={() => setActiveSectionId(sec.content_id)}
                      >
                        <div className="result-title">
                          <span style={{ fontWeight: 600 }}>{sec.section || 'General Section'}</span>
                          <span className="badge badge-section">{sec.content_id}</span>
                        </div>
                        <div className="result-text" style={{ maxHeight: '70px', marginBottom: '0.5rem', fontSize: '0.8rem' }}>
                          {sec.text || (sec.subsection ? `Subsection: ${sec.subsection}` : 'Registered regulatory section.')}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                          <button
                            onClick={() => handleProceedToReview(sec)}
                            className="btn btn-secondary"
                            style={{ fontSize: '0.78rem', padding: '0.35rem 0.75rem' }}
                          >
                            Find Reusable Content <ArrowRight size={12} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Secondary Expandable: View Processing Details */}
              <div
                style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: '0.85rem 1rem'
                }}
              >
                <div
                  onClick={() => setDetailsOpen(!detailsOpen)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    cursor: 'pointer',
                    userSelect: 'none'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    {detailsOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                    <span>View Processing Details</span>
                  </div>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    Document ID: <code>{ingestResult.document_id}</code>
                  </span>
                </div>

                {detailsOpen && (
                  <div style={{ marginTop: '0.85rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)' }}>
                    <div className="grid-3" style={{ gap: '0.5rem', marginBottom: '0.6rem' }}>
                      <div style={{ background: '#ffffff', padding: '0.45rem 0.6rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>DOCUMENT ID</span>
                        <code style={{ fontSize: '0.76rem', color: 'var(--color-brand)' }}>{ingestResult.document_id}</code>
                      </div>
                      <div style={{ background: '#ffffff', padding: '0.45rem 0.6rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>JURISDICTION</span>
                        <strong style={{ fontSize: '0.76rem', color: 'var(--text-primary)' }}>{ingestResult.jurisdiction}</strong>
                      </div>
                      <div style={{ background: '#ffffff', padding: '0.45rem 0.6rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block' }}>DOCUMENT TYPE</span>
                        <strong style={{ fontSize: '0.76rem', color: 'var(--text-primary)' }}>{ingestResult.document_type}</strong>
                      </div>
                    </div>

                    <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
                      Processing status: {ingestResult.message}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* Before Ingestion: Initial Guidance State */
            <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: '340px', textAlign: 'center', padding: '2rem' }}>
              <div style={{ maxWidth: '380px', margin: '0 auto' }}>
                <div
                  style={{
                    width: '54px',
                    height: '54px',
                    borderRadius: '50%',
                    background: 'rgba(13, 148, 136, 0.08)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto 1rem',
                  }}
                >
                  <FileText size={26} color="var(--color-brand)" />
                </div>

                <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.45rem' }}>
                  Ready to Start Review
                </h3>

                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: '1.5', marginBottom: '1.25rem' }}>
                  Select or drop a regulatory document file on the left, verify Document Information, and click <strong>Ingest Document</strong> to begin reuse analysis against approved drug labels.
                </p>

                <div style={{ background: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', padding: '0.75rem', border: '1px solid var(--border-subtle)', textAlign: 'left', fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.3rem' }}>Workflow steps:</div>
                  <div>1. Select regulatory document (.pdf, .doc, .docx, .txt)</div>
                  <div>2. Confirm jurisdiction and document type</div>
                  <div>3. Click Ingest Document to discover reusable content</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
