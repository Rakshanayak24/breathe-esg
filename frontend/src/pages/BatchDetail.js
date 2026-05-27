import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { batchAPI } from '../utils/api';

const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
const fmtNum = (n, d = 2) => n != null ? Number(n).toFixed(d) : '—';

const SOURCE_LABELS = {
  sap_fuel_procurement: 'SAP Fuel & Procurement',
  utility_electricity: 'Utility Electricity',
  travel_corporate: 'Corporate Travel',
};

const STATUS_COLORS = {
  ok: 'var(--accent)',
  suspicious: 'var(--warn)',
  failed: 'var(--danger)',
  approved: 'var(--accent)',
  rejected: 'var(--danger)',
};

export default function BatchDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [batch, setBatch] = useState(null);
  const [rows, setRows] = useState({ sap_rows: [], utility_rows: [], travel_rows: [] });
  const [loading, setLoading] = useState(true);
  const [rowFilter, setRowFilter] = useState('');
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [notes, setNotes] = useState('');
  const [activeTab, setActiveTab] = useState('rows');
  const [msg, setMsg] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      batchAPI.get(id),
      batchAPI.rows(id, rowFilter ? { status: rowFilter } : {}),
    ]).then(([b, r]) => {
      setBatch(b.data);
      setRows(r.data);
    }).catch(console.error)
      .finally(() => setLoading(false));
  }, [id, rowFilter]);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async () => {
    setApproving(true);
    try {
      const res = await batchAPI.approve(id, { notes });
      setMsg({ type: 'ok', text: res.data.message });
      load();
    } catch (e) {
      setMsg({ type: 'err', text: e.response?.data?.error || 'Approval failed' });
    } finally {
      setApproving(false);
    }
  };

  const handleReject = async () => {
    if (!notes.trim()) { setMsg({ type: 'err', text: 'Please add a rejection reason in the notes field.' }); return; }
    setRejecting(true);
    try {
      await batchAPI.reject(id, { notes });
      setMsg({ type: 'ok', text: 'Batch rejected.' });
      load();
    } catch (e) {
      setMsg({ type: 'err', text: e.response?.data?.error || 'Rejection failed' });
    } finally {
      setRejecting(false);
    }
  };

  if (loading && !batch) return <LoadingSkeleton />;
  if (!batch) return <div style={{ color: 'var(--danger)' }}>Batch not found.</div>;

  const allRows = [
    ...(rows.sap_rows || []),
    ...(rows.utility_rows || []),
    ...(rows.travel_rows || []),
  ];
  const sourceType = batch.source_type;
  const canApprove = ['pending', 'in_review', 'partial'].includes(batch.status);

  return (
    <div style={styles.root}>
      {/* Breadcrumb */}
      <div style={styles.breadcrumb}>
        <button onClick={() => navigate('/batches')} style={styles.backBtn}>← Ingestion Queue</button>
        <span style={styles.breadSep}>/</span>
        <span style={styles.breadCurrent}>{batch.original_filename || 'Batch'}</span>
      </div>

      {/* Batch header */}
      <div style={styles.batchHeader}>
        <div>
          <div style={styles.batchTitle}>
            {batch.original_filename || 'Data Batch'}
            <span className={`badge badge-${batch.status}`} style={{ marginLeft: 12, verticalAlign: 'middle' }}>
              {batch.status_display}
            </span>
          </div>
          <div style={styles.batchMeta}>
            {SOURCE_LABELS[batch.source_type]} · Uploaded {fmtDate(batch.uploaded_at)} by {batch.uploaded_by_name}
            {batch.period_start && ` · Period: ${fmtDate(batch.period_start)} – ${fmtDate(batch.period_end)}`}
          </div>
        </div>
      </div>

      {/* Stats bar */}
      <div style={styles.statsBar}>
        <Stat label="Parsed" value={batch.rows_parsed} color="var(--accent)" />
        <Stat label="Suspicious" value={batch.rows_suspicious} color="var(--warn)" />
        <Stat label="Failed" value={batch.rows_failed} color="var(--danger)" />
        <Stat label="Success Rate" value={`${(batch.success_rate || 0).toFixed(1)}%`} color="var(--text)" />
      </div>

      {/* Tabs */}
      <div style={styles.tabs}>
        {['rows', 'parse_log', 'review'].map(tab => (
          <button
            key={tab}
            style={{ ...styles.tab, ...(activeTab === tab ? styles.tabActive : {}) }}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'rows' ? `Data Rows (${allRows.length})` : tab === 'parse_log' ? 'Parse Log' : 'Review & Approve'}
          </button>
        ))}
      </div>

      {activeTab === 'rows' && (
        <div>
          {/* Row filter */}
          <div style={styles.rowFilter}>
            {['', 'ok', 'suspicious', 'failed', 'approved'].map(f => (
              <button
                key={f}
                style={{ ...styles.filterBtn, ...(rowFilter === f ? styles.filterBtnActive : {}) }}
                onClick={() => setRowFilter(f)}
              >
                {f === '' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>

          {loading ? (
            <LoadingSkeleton />
          ) : allRows.length === 0 ? (
            <div style={styles.empty}>No rows match this filter.</div>
          ) : sourceType === 'sap_fuel_procurement' ? (
            <SAPTable rows={rows.sap_rows} />
          ) : sourceType === 'utility_electricity' ? (
            <UtilityTable rows={rows.utility_rows} />
          ) : (
            <TravelTable rows={rows.travel_rows} />
          )}
        </div>
      )}

      {activeTab === 'parse_log' && (
        <div style={styles.logBox}>
          {batch.parse_log?.length === 0 ? (
            <div style={{ color: 'var(--text-3)', padding: 20, textAlign: 'center' }}>No parse warnings or errors.</div>
          ) : (
            (batch.parse_log || []).map((entry, i) => (
              <div key={i} style={styles.logEntry}>
                <span style={styles.logRow}>Row {entry.row}</span>
                <span style={styles.logMsg}>{entry.message}</span>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'review' && (
        <div style={styles.reviewPanel}>
          {msg && (
            <div style={{
              ...styles.msgBox,
              background: msg.type === 'ok' ? 'var(--accent-dim)' : 'var(--danger-dim)',
              borderColor: msg.type === 'ok' ? 'var(--accent)' : 'var(--danger)',
              color: msg.type === 'ok' ? 'var(--accent)' : 'var(--danger)',
            }}>
              {msg.type === 'ok' ? '✓' : '⚠'} {msg.text}
            </div>
          )}

          <div style={styles.reviewSection}>
            <div style={styles.reviewTitle}>Review Summary</div>
            <p style={styles.reviewDesc}>
              This batch contains <strong style={{ color: 'var(--text)' }}>{batch.rows_parsed} parsed rows</strong>
              {batch.rows_suspicious > 0 && <>, of which <strong style={{ color: 'var(--warn)' }}>{batch.rows_suspicious} are flagged suspicious</strong></>}
              {batch.rows_failed > 0 && <> and <strong style={{ color: 'var(--danger)' }}>{batch.rows_failed} failed to parse</strong></>}.
            </p>
            {batch.rows_suspicious > 0 && (
              <div style={styles.suspiciousNote}>
                ⚠ Suspicious rows will be included in approval unless you filter them out. Review the "Data Rows" tab filtered to "Suspicious" before approving.
              </div>
            )}
          </div>

          <div style={styles.reviewSection}>
            <div style={styles.reviewTitle}>Notes</div>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Add review notes (required for rejection)..."
              style={styles.notesArea}
              rows={3}
            />
          </div>

          {canApprove ? (
            <div style={styles.actionRow}>
              <button
                onClick={handleApprove}
                disabled={approving}
                style={styles.approveBtn}
              >
                {approving ? '…' : '✓ Approve Batch & Lock Records'}
              </button>
              <button
                onClick={handleReject}
                disabled={rejecting}
                style={styles.rejectBtn}
              >
                {rejecting ? '…' : '✕ Reject Batch'}
              </button>
            </div>
          ) : (
            <div style={styles.alreadyActioned}>
              This batch has been <strong>{batch.status}</strong>
              {batch.approved_by_name && ` by ${batch.approved_by_name}`}
              {batch.approved_at && ` on ${fmtDate(batch.approved_at)}`}.
              {batch.status === 'approved' && ' Emission records are locked for audit.'}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={styles.statBox}>
      <div style={{ ...styles.statVal, color }}>{value}</div>
      <div style={styles.statLbl}>{label}</div>
    </div>
  );
}

function SAPTable({ rows }) {
  return (
    <div style={styles.tableWrap}>
      <table style={styles.table}>
        <thead>
          <tr>
            {['Row', 'Date', 'Plant', 'Material', 'Description', 'Qty', 'Unit', 'Fuel Type', 'Status', 'Flags'].map(h => (
              <th key={h} style={styles.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.id} style={{ background: row.status === 'suspicious' ? 'rgba(245,158,11,0.04)' : row.status === 'failed' ? 'rgba(239,68,68,0.04)' : 'transparent' }}>
              <td style={styles.td}><span style={styles.mono}>{row.row_number}</span></td>
              <td style={styles.td}><span style={styles.mono}>{fmtDate(row.posting_date)}</span></td>
              <td style={styles.td}><span style={styles.mono}>{row.plant_code || '—'}</span></td>
              <td style={styles.td}><span style={styles.mono}>{row.material_number || '—'}</span></td>
              <td style={{ ...styles.td, maxWidth: 200 }}>{row.material_description || '—'}</td>
              <td style={styles.td}><span style={styles.mono}>{fmtNum(row.quantity, 3)}</span></td>
              <td style={styles.td}><span style={styles.mono}>{row.unit_of_measure_raw}</span></td>
              <td style={styles.td}>
                {row.is_fuel ? <span style={styles.fuelTag}>{row.fuel_type || 'fuel'}</span> : row.is_procurement ? <span style={styles.procTag}>proc</span> : '—'}
              </td>
              <td style={styles.td}><span className={`badge badge-${row.status}`}>{row.status}</span></td>
              <td style={styles.td}>
                {row.suspicious_reason && <span style={styles.flag} title={row.suspicious_reason}>⚠ {row.suspicious_reason.slice(0, 40)}…</span>}
                {row.parse_error && <span style={styles.flagErr} title={row.parse_error}>✕ {row.parse_error.slice(0, 40)}…</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UtilityTable({ rows }) {
  return (
    <div style={styles.tableWrap}>
      <table style={styles.table}>
        <thead>
          <tr>
            {['Row', 'Site', 'Meter', 'Period Start', 'Period End', 'Days', 'kWh', 'Multiplier', 'Grid Region', 'Status', 'Flags'].map(h => (
              <th key={h} style={styles.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.id} style={{ background: row.status === 'suspicious' ? 'rgba(245,158,11,0.04)' : 'transparent' }}>
              <td style={styles.td}><span style={styles.mono}>{row.row_number}</span></td>
              <td style={{ ...styles.td, maxWidth: 160 }}>{row.site_name || '—'}</td>
              <td style={styles.td}><span style={styles.mono}>{row.meter_id || '—'}</span></td>
              <td style={styles.td}><span style={styles.mono}>{fmtDate(row.billing_period_start)}</span></td>
              <td style={styles.td}><span style={styles.mono}>{fmtDate(row.billing_period_end)}</span></td>
              <td style={styles.td}><span style={styles.mono}>{row.billing_period_days ?? '—'}</span></td>
              <td style={styles.td}><span style={styles.mono}>{fmtNum(row.units_consumed_kwh)}</span></td>
              <td style={styles.td}><span style={styles.mono}>{fmtNum(row.multiplier, 4)}</span></td>
              <td style={styles.td}>{row.grid_region || '—'}</td>
              <td style={styles.td}><span className={`badge badge-${row.status}`}>{row.status}</span></td>
              <td style={styles.td}>
                {row.suspicious_reason && <span style={styles.flag} title={row.suspicious_reason}>⚠</span>}
                {row.parse_error && <span style={styles.flagErr} title={row.parse_error}>✕</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TravelTable({ rows }) {
  return (
    <div style={styles.tableWrap}>
      <table style={styles.table}>
        <thead>
          <tr>
            {['Row', 'Type', 'Date', 'Employee', 'Route / Details', 'Cabin / Nights', 'Distance', 'Amount', 'Status', 'Flags'].map(h => (
              <th key={h} style={styles.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.id} style={{ background: row.status === 'suspicious' ? 'rgba(245,158,11,0.04)' : 'transparent' }}>
              <td style={styles.td}><span style={styles.mono}>{row.row_number}</span></td>
              <td style={styles.td}>
                <span style={{
                  ...styles.travelTypeBadge,
                  background: row.travel_type === 'flight' ? 'rgba(59,130,246,0.15)' : row.travel_type === 'hotel' ? 'rgba(168,85,247,0.15)' : 'rgba(34,211,160,0.15)',
                  color: row.travel_type === 'flight' ? '#3b82f6' : row.travel_type === 'hotel' ? '#a855f7' : 'var(--accent)',
                }}>
                  {row.travel_type_display || row.travel_type}
                </span>
              </td>
              <td style={styles.td}><span style={styles.mono}>{fmtDate(row.travel_date || row.check_in_date)}</span></td>
              <td style={styles.td}><span style={styles.mono}>{row.employee_id || '—'}</span></td>
              <td style={styles.td}>
                {row.travel_type === 'flight'
                  ? <span style={styles.route}>{row.origin_iata} → {row.destination_iata}{row.is_return ? ' ↩' : ''}</span>
                  : row.travel_type === 'hotel'
                  ? <span>{row.hotel_city}{row.hotel_city && row.hotel_country ? `, ${row.hotel_country}` : ''}</span>
                  : <span>{row.vendor || row.transport_mode_detail || '—'}</span>
                }
              </td>
              <td style={styles.td}>
                {row.travel_type === 'flight'
                  ? <span style={styles.mono}>{row.cabin_class}</span>
                  : row.travel_type === 'hotel'
                  ? <span style={styles.mono}>{row.nights ?? '—'} nights</span>
                  : '—'
                }
              </td>
              <td style={styles.td}>
                <span style={styles.mono}>
                  {row.distance_km ? `${fmtNum(row.distance_km)} km` : row.distance_km_ground ? `${fmtNum(row.distance_km_ground)} km` : '—'}
                  {row.distance_source === 'calculated_haversine' && <span style={{ color: 'var(--text-3)', fontSize: 10 }}> calc</span>}
                </span>
              </td>
              <td style={styles.td}>
                <span style={styles.mono}>{row.amount ? `${Number(row.amount).toLocaleString('en-IN')} ${row.currency}` : '—'}</span>
              </td>
              <td style={styles.td}><span className={`badge badge-${row.status}`}>{row.status}</span></td>
              <td style={styles.td}>
                {row.suspicious_reason && <span style={styles.flag} title={row.suspicious_reason}>⚠</span>}
                {row.parse_error && <span style={styles.flagErr} title={row.parse_error}>✕</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {[...Array(4)].map((_, i) => <div key={i} className="skeleton" style={{ height: 48 }} />)}
    </div>
  );
}

const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: 20 },
  breadcrumb: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 },
  backBtn: { background: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: 13 },
  breadSep: { color: 'var(--text-3)' },
  breadCurrent: { color: 'var(--text-2)', fontFamily: 'var(--font-mono)', fontSize: 12 },
  batchHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  batchTitle: { fontSize: 20, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-mono)' },
  batchMeta: { fontSize: 12, color: 'var(--text-3)', marginTop: 6 },
  statsBar: { display: 'flex', gap: 0, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' },
  statBox: { flex: 1, padding: '14px 20px', borderRight: '1px solid var(--border)', textAlign: 'center' },
  statVal: { fontSize: 20, fontWeight: 600, fontFamily: 'var(--font-mono)' },
  statLbl: { fontSize: 11, color: 'var(--text-3)', marginTop: 3, textTransform: 'uppercase', letterSpacing: '0.06em' },
  tabs: { display: 'flex', gap: 0, borderBottom: '1px solid var(--border)' },
  tab: { background: 'none', color: 'var(--text-3)', padding: '10px 20px', fontSize: 13, cursor: 'pointer', borderBottom: '2px solid transparent', transition: 'all 0.15s' },
  tabActive: { color: 'var(--accent)', borderBottomColor: 'var(--accent)' },
  rowFilter: { display: 'flex', gap: 6, marginBottom: 14 },
  filterBtn: { background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-3)', padding: '5px 12px', borderRadius: 'var(--radius)', fontSize: 12, cursor: 'pointer' },
  filterBtnActive: { background: 'var(--accent-dim)', borderColor: 'var(--accent)', color: 'var(--accent)' },
  tableWrap: { overflowX: 'auto', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border)', background: 'var(--surface)' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 12 },
  th: { padding: '10px 14px', textAlign: 'left', color: 'var(--text-3)', fontWeight: 500, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap', background: 'var(--surface)' },
  td: { padding: '10px 14px', borderBottom: '1px solid var(--border)', color: 'var(--text)', verticalAlign: 'top' },
  mono: { fontFamily: 'var(--font-mono)', fontSize: 11 },
  fuelTag: { background: 'rgba(249,115,22,0.15)', color: '#f97316', padding: '1px 6px', borderRadius: 3, fontSize: 10, fontFamily: 'var(--font-mono)' },
  procTag: { background: 'var(--surface-3)', color: 'var(--text-3)', padding: '1px 6px', borderRadius: 3, fontSize: 10 },
  flag: { color: 'var(--warn)', fontSize: 11, cursor: 'help' },
  flagErr: { color: 'var(--danger)', fontSize: 11, cursor: 'help' },
  travelTypeBadge: { padding: '2px 7px', borderRadius: 3, fontSize: 11, fontWeight: 500 },
  route: { fontFamily: 'var(--font-mono)', fontWeight: 500, color: 'var(--text)' },
  reviewPanel: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 24, display: 'flex', flexDirection: 'column', gap: 20 },
  reviewSection: { display: 'flex', flexDirection: 'column', gap: 10 },
  reviewTitle: { fontSize: 12, fontWeight: 500, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' },
  reviewDesc: { fontSize: 14, color: 'var(--text-2)', lineHeight: 1.6 },
  suspiciousNote: { background: 'var(--warn-dim)', border: '1px solid rgba(245,158,11,0.3)', color: 'var(--warn)', borderRadius: 'var(--radius)', padding: '10px 14px', fontSize: 13 },
  notesArea: { resize: 'vertical', minHeight: 80 },
  actionRow: { display: 'flex', gap: 12 },
  approveBtn: { background: 'var(--accent)', color: '#000', fontWeight: 600, fontSize: 14, padding: '12px 24px', borderRadius: 'var(--radius)', cursor: 'pointer' },
  rejectBtn: { background: 'var(--danger-dim)', color: 'var(--danger)', border: '1px solid rgba(239,68,68,0.3)', fontWeight: 500, fontSize: 14, padding: '12px 24px', borderRadius: 'var(--radius)', cursor: 'pointer' },
  alreadyActioned: { fontSize: 13, color: 'var(--text-2)', padding: '14px', background: 'var(--surface-2)', borderRadius: 'var(--radius)' },
  msgBox: { padding: '12px 16px', borderRadius: 'var(--radius)', fontSize: 13, border: '1px solid' },
  logBox: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden', fontFamily: 'var(--font-mono)', fontSize: 12 },
  logEntry: { display: 'flex', gap: 16, padding: '10px 16px', borderBottom: '1px solid var(--border)' },
  logRow: { color: 'var(--text-3)', width: 60, flexShrink: 0 },
  logMsg: { color: 'var(--warn)' },
  empty: { textAlign: 'center', padding: '40px', color: 'var(--text-3)', fontSize: 13 },
};
