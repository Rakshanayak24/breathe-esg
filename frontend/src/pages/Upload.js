import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { batchAPI } from '../utils/api';

const SOURCE_OPTIONS = [
  {
    value: 'sap_fuel_procurement',
    label: 'SAP Fuel & Procurement',
    desc: 'Pipe-delimited MB51 export (fuel materials, goods issues)',
    formats: '.txt, .csv, .dat',
    icon: '⊞',
    color: 'var(--scope1)',
  },
  {
    value: 'utility_electricity',
    label: 'Utility Electricity',
    desc: 'Utility portal CSV export (BESCOM, Tata Power, MSEDCL, etc.)',
    formats: '.csv',
    icon: '⊟',
    color: 'var(--scope2)',
  },
  {
    value: 'travel_corporate',
    label: 'Corporate Travel',
    desc: 'Navan or Concur expense export (flights, hotels, ground)',
    formats: '.csv',
    icon: '◎',
    color: 'var(--scope3)',
  },
];

export default function Upload() {
  const [sourceType, setSourceType] = useState('');
  const [file, setFile] = useState(null);
  const [notes, setNotes] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const onDrop = useCallback((accepted) => {
    if (accepted[0]) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'text/csv': ['.csv'], 'text/plain': ['.txt', '.dat', '.tsv'] },
    maxFiles: 1,
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!sourceType) { setError('Select a data source type.'); return; }
    if (!file) { setError('Choose a file to upload.'); return; }
    setError('');
    setUploading(true);
    const formData = new FormData();
    formData.append('source_type', sourceType);
    formData.append('file', file);
    formData.append('notes', notes);
    try {
      const res = await batchAPI.upload(formData);
      navigate(`/batches/${res.data.id}`);
    } catch (err) {
      const detail = err.response?.data;
      if (typeof detail === 'object') {
        setError(Object.values(detail).flat().join(' '));
      } else {
        setError(detail || 'Upload failed.');
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <h1 style={styles.title}>Upload Data</h1>
        <p style={styles.subtitle}>
          Select a source type, then drop your file. We'll parse, normalize, and route it to the review queue.
        </p>
      </div>

      <form onSubmit={handleSubmit} style={styles.form}>
        {/* Source type selector */}
        <div style={styles.section}>
          <div style={styles.sectionLabel}>1. Select Data Source</div>
          <div style={styles.sourceGrid}>
            {SOURCE_OPTIONS.map(opt => (
              <div
                key={opt.value}
                style={{
                  ...styles.sourceCard,
                  borderColor: sourceType === opt.value ? opt.color : 'var(--border)',
                  background: sourceType === opt.value ? `rgba(${hexToRgb(opt.color)}, 0.05)` : 'var(--surface)',
                  cursor: 'pointer',
                }}
                onClick={() => setSourceType(opt.value)}
              >
                <div style={{ ...styles.sourceCardIcon, color: opt.color }}>{opt.icon}</div>
                <div>
                  <div style={styles.sourceCardLabel}>{opt.label}</div>
                  <div style={styles.sourceCardDesc}>{opt.desc}</div>
                  <div style={{ ...styles.sourceCardFormats, color: opt.color }}>
                    Accepts: {opt.formats}
                  </div>
                </div>
                {sourceType === opt.value && (
                  <div style={{ ...styles.checkMark, color: opt.color }}>✓</div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* File drop */}
        <div style={styles.section}>
          <div style={styles.sectionLabel}>2. Upload File</div>
          <div
            {...getRootProps()}
            style={{
              ...styles.dropzone,
              borderColor: isDragActive ? 'var(--accent)' : file ? 'var(--accent)' : 'var(--border)',
              background: isDragActive ? 'var(--accent-dim)' : 'var(--surface)',
            }}
          >
            <input {...getInputProps()} />
            {file ? (
              <div style={styles.filePreview}>
                <span style={styles.fileIcon}>📄</span>
                <div>
                  <div style={styles.fileName}>{file.name}</div>
                  <div style={styles.fileSize}>{(file.size / 1024).toFixed(1)} KB</div>
                </div>
                <button
                  type="button"
                  style={styles.clearFile}
                  onClick={e => { e.stopPropagation(); setFile(null); }}
                >
                  ✕
                </button>
              </div>
            ) : (
              <div style={styles.dropPrompt}>
                <div style={styles.dropIcon}>↑</div>
                <div style={styles.dropText}>
                  {isDragActive ? 'Drop the file here…' : 'Drag & drop your file, or click to browse'}
                </div>
                <div style={styles.dropSub}>CSV, TXT, DAT — up to 50MB</div>
              </div>
            )}
          </div>
        </div>

        {/* Notes */}
        <div style={styles.section}>
          <div style={styles.sectionLabel}>3. Notes (optional)</div>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="e.g. Q1 FY2024–25 fuel data from Plant IN01 and IN02. Reconciled against purchase orders."
            rows={2}
            style={styles.notesArea}
          />
        </div>

        {error && (
          <div style={styles.errorBox}>⚠ {error}</div>
        )}

        <button type="submit" disabled={uploading || !sourceType || !file} style={{
          ...styles.submitBtn,
          opacity: (!sourceType || !file) ? 0.4 : 1,
        }}>
          {uploading ? 'Parsing & uploading…' : '↑ Upload & Parse'}
        </button>
      </form>

      {/* Sample data hint */}
      <div style={styles.sampleHint}>
        <div style={styles.sampleTitle}>Sample files included in repository</div>
        <div style={styles.sampleList}>
          {[
            { name: 'sap_fuel_procurement_Q1FY25.txt', label: 'SAP MB51 export — 30 fuel rows (pipe-delimited, German date format)' },
            { name: 'utility_electricity_Q1FY25.csv', label: 'Utility CSV — 18 billing rows, 5 sites, BESCOM + MSEDCL format' },
            { name: 'travel_corporate_Q1FY25.csv', label: 'Navan export — 37 rows, flights/hotels/ground, IATA distance calculated' },
          ].map(({ name, label }) => (
            <div key={name} style={styles.sampleRow}>
              <span style={styles.sampleName}>{name}</span>
              <span style={styles.sampleLabel}>{label}</span>
            </div>
          ))}
        </div>
        <div style={styles.sampleNote}>Find these in <code style={styles.code}>sample_data/</code> in the repository root.</div>
      </div>
    </div>
  );
}

// Crude hex → rgb helper for inline style opacity trickery
function hexToRgb(cssVar) {
  const map = {
    'var(--scope1)': '249,115,22',
    'var(--scope2)': '59,130,246',
    'var(--scope3)': '168,85,247',
  };
  return map[cssVar] || '34,211,160';
}

const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: 28, maxWidth: 780 },
  header: {},
  title: { fontSize: 24, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-display)', fontStyle: 'italic' },
  subtitle: { fontSize: 13, color: 'var(--text-3)', marginTop: 6, lineHeight: 1.5 },
  form: { display: 'flex', flexDirection: 'column', gap: 24 },
  section: { display: 'flex', flexDirection: 'column', gap: 12 },
  sectionLabel: { fontSize: 12, fontWeight: 500, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' },
  sourceGrid: { display: 'flex', flexDirection: 'column', gap: 10 },
  sourceCard: { display: 'flex', alignItems: 'flex-start', gap: 14, padding: '16px 18px', borderRadius: 'var(--radius-lg)', border: '1px solid', transition: 'all 0.15s', position: 'relative' },
  sourceCardIcon: { fontSize: 22, width: 28, textAlign: 'center', flexShrink: 0, marginTop: 2 },
  sourceCardLabel: { fontSize: 14, fontWeight: 500, color: 'var(--text)', marginBottom: 3 },
  sourceCardDesc: { fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5, marginBottom: 4 },
  sourceCardFormats: { fontSize: 11, fontFamily: 'var(--font-mono)' },
  checkMark: { position: 'absolute', top: 14, right: 16, fontSize: 16, fontWeight: 600 },
  dropzone: { border: '2px dashed', borderRadius: 'var(--radius-lg)', padding: '40px 30px', transition: 'all 0.15s', cursor: 'pointer', textAlign: 'center' },
  dropPrompt: {},
  dropIcon: { fontSize: 28, color: 'var(--text-3)', marginBottom: 10 },
  dropText: { fontSize: 14, color: 'var(--text-2)', marginBottom: 6 },
  dropSub: { fontSize: 12, color: 'var(--text-3)' },
  filePreview: { display: 'flex', alignItems: 'center', gap: 14, justifyContent: 'center' },
  fileIcon: { fontSize: 24 },
  fileName: { fontSize: 14, fontFamily: 'var(--font-mono)', color: 'var(--accent)' },
  fileSize: { fontSize: 12, color: 'var(--text-3)', marginTop: 2 },
  clearFile: { background: 'var(--danger-dim)', color: 'var(--danger)', border: 'none', borderRadius: 'var(--radius)', padding: '4px 8px', cursor: 'pointer', fontSize: 12 },
  notesArea: { resize: 'vertical', minHeight: 60 },
  errorBox: { background: 'var(--danger-dim)', border: '1px solid rgba(239,68,68,0.3)', color: 'var(--danger)', padding: '10px 14px', borderRadius: 'var(--radius)', fontSize: 13 },
  submitBtn: { background: 'var(--accent)', color: '#000', fontWeight: 600, fontSize: 15, padding: '14px 28px', borderRadius: 'var(--radius)', cursor: 'pointer', transition: 'opacity 0.15s', alignSelf: 'flex-start' },
  sampleHint: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 20 },
  sampleTitle: { fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 },
  sampleList: { display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 },
  sampleRow: { display: 'flex', gap: 12, alignItems: 'flex-start' },
  sampleName: { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)', flexShrink: 0, width: 280 },
  sampleLabel: { fontSize: 12, color: 'var(--text-3)' },
  sampleNote: { fontSize: 12, color: 'var(--text-3)' },
  code: { fontFamily: 'var(--font-mono)', background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 3, fontSize: 11 },
};
