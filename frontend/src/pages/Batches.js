import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { batchAPI } from '../utils/api';

const SOURCE_LABELS = {
  sap_fuel_procurement: 'SAP Fuel & Procurement',
  utility_electricity: 'Utility Electricity',
  travel_corporate: 'Corporate Travel',
};
const SOURCE_ICONS = {
  sap_fuel_procurement: '⊞',
  utility_electricity: '⊟',
  travel_corporate: '◎',
};
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';

export default function Batches() {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const load = useCallback(() => {
    setLoading(true);
    const params = {};
    if (sourceFilter) params.source_type = sourceFilter;
    if (statusFilter) params.status = statusFilter;
    batchAPI.list(params)
      .then(r => setBatches(r.data.results || r.data || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [sourceFilter, statusFilter]);

  useEffect(() => {
    const s = searchParams.get('status');
    if (s) setStatusFilter(s);
  }, [searchParams]);

  useEffect(() => { load(); }, [load]);

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Ingestion Queue</h1>
          <p style={styles.subtitle}>Review and approve uploaded data batches before they lock to audit</p>
        </div>
        <button style={styles.uploadBtn} onClick={() => navigate('/upload')}>↑ Upload</button>
      </div>

      {/* Filters */}
      <div style={styles.filters}>
        <select
          value={sourceFilter}
          onChange={e => setSourceFilter(e.target.value)}
          style={styles.select}
        >
          <option value="">All sources</option>
          <option value="sap_fuel_procurement">SAP Fuel & Procurement</option>
          <option value="utility_electricity">Utility Electricity</option>
          <option value="travel_corporate">Corporate Travel</option>
        </select>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          style={styles.select}
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="in_review">In Review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <button onClick={load} style={styles.refreshBtn}>↺ Refresh</button>
      </div>

      {/* Batch table */}
      {loading ? (
        <LoadingSkeleton />
      ) : batches.length === 0 ? (
        <Empty />
      ) : (
        <div style={styles.table}>
          <div style={styles.tableHeader}>
            <span style={{ flex: 2 }}>File / Source</span>
            <span style={{ flex: 1 }}>Period</span>
            <span style={{ width: 120, textAlign: 'right' }}>Rows</span>
            <span style={{ width: 100, textAlign: 'center' }}>Status</span>
            <span style={{ width: 120, textAlign: 'right' }}>Uploaded</span>
          </div>
          {batches.map(batch => (
            <BatchRow
              key={batch.id}
              batch={batch}
              onClick={() => navigate(`/batches/${batch.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function BatchRow({ batch, onClick }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      style={{
        ...styles.row,
        background: hovered ? 'var(--surface-2)' : 'var(--surface)',
      }}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* File + Source */}
      <div style={{ flex: 2, minWidth: 0, display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={styles.sourceIcon}>
          {SOURCE_ICONS[batch.source_type]}
        </span>
        <div style={{ minWidth: 0 }}>
          <div style={styles.fileName}>
            {batch.original_filename || 'Manual upload'}
          </div>
          <div style={styles.sourceName}>
            {SOURCE_LABELS[batch.source_type]}
          </div>
        </div>
      </div>

      {/* Period */}
      <div style={{ flex: 1 }}>
        {batch.period_start ? (
          <span style={styles.period}>
            {fmtDate(batch.period_start)} – {fmtDate(batch.period_end)}
          </span>
        ) : (
          <span style={{ color: 'var(--text-3)', fontSize: 12 }}>Unknown</span>
        )}
      </div>

      {/* Rows */}
      <div style={{ width: 120, textAlign: 'right', display: 'flex', gap: 8, justifyContent: 'flex-end', alignItems: 'center' }}>
        <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
          {batch.rows_parsed}
        </span>
        {batch.rows_suspicious > 0 && (
          <span style={{ color: 'var(--warn)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            {batch.rows_suspicious}⚠
          </span>
        )}
        {batch.rows_failed > 0 && (
          <span style={{ color: 'var(--danger)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            {batch.rows_failed}✕
          </span>
        )}
      </div>

      {/* Status */}
      <div style={{ width: 100, textAlign: 'center' }}>
        <span className={`badge badge-${batch.status}`}>
          {batch.status_display}
        </span>
      </div>

      {/* Date */}
      <div style={{ width: 120, textAlign: 'right', fontSize: 12, color: 'var(--text-3)' }}>
        {fmtDate(batch.uploaded_at)}
      </div>
    </div>
  );
}

function Empty() {
  const navigate = useNavigate();
  return (
    <div style={styles.empty}>
      <div style={styles.emptyIcon}>⊞</div>
      <div style={styles.emptyTitle}>No batches yet</div>
      <div style={styles.emptySub}>Upload your first data file to get started</div>
      <button style={styles.uploadBtn} onClick={() => navigate('/upload')}>
        ↑ Upload Data
      </button>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {[...Array(5)].map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 64, borderRadius: 'var(--radius)' }} />
      ))}
    </div>
  );
}

const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: 24 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  title: { fontSize: 24, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-display)', fontStyle: 'italic' },
  subtitle: { fontSize: 13, color: 'var(--text-3)', marginTop: 4 },
  uploadBtn: { background: 'var(--accent)', color: '#000', fontWeight: 600, fontSize: 13, padding: '9px 18px', borderRadius: 'var(--radius)', cursor: 'pointer' },
  filters: { display: 'flex', gap: 10, alignItems: 'center' },
  select: { width: 'auto', maxWidth: 220 },
  refreshBtn: { background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-2)', padding: '8px 14px', borderRadius: 'var(--radius)', cursor: 'pointer', fontSize: 13 },
  table: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' },
  tableHeader: { display: 'flex', alignItems: 'center', padding: '10px 20px', borderBottom: '1px solid var(--border)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', gap: 12 },
  row: { display: 'flex', alignItems: 'center', padding: '14px 20px', borderBottom: '1px solid var(--border)', cursor: 'pointer', transition: 'background 0.12s', gap: 12 },
  sourceIcon: { fontSize: 18, color: 'var(--text-3)', width: 24, textAlign: 'center', flexShrink: 0 },
  fileName: { fontSize: 13, color: 'var(--text)', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  sourceName: { fontSize: 11, color: 'var(--text-3)', marginTop: 2 },
  period: { fontSize: 12, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' },
  empty: { textAlign: 'center', padding: '80px 40px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' },
  emptyIcon: { fontSize: 36, color: 'var(--text-3)', marginBottom: 12 },
  emptyTitle: { fontSize: 16, fontWeight: 500, color: 'var(--text)', marginBottom: 6 },
  emptySub: { fontSize: 13, color: 'var(--text-3)', marginBottom: 24 },
};
