import React, { useEffect, useState } from 'react';
import { emissionsAPI } from '../utils/api';

const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';

const SCOPE_COLORS = {
  scope1: { bg: 'rgba(249,115,22,0.12)', text: '#f97316', label: 'Scope 1' },
  scope2_location: { bg: 'rgba(59,130,246,0.12)', text: '#3b82f6', label: 'Scope 2 (location)' },
  scope2_market: { bg: 'rgba(59,130,246,0.12)', text: '#3b82f6', label: 'Scope 2 (market)' },
  scope3: { bg: 'rgba(168,85,247,0.12)', text: '#a855f7', label: 'Scope 3' },
};

export default function Emissions() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scopeFilter, setScopeFilter] = useState('');
  const [total, setTotal] = useState(0);

  const load = () => {
    setLoading(true);
    const params = { ordering: '-activity_period_start', page_size: 100 };
    if (scopeFilter) params.scope = scopeFilter;
    emissionsAPI.list(params)
      .then(r => {
        const results = r.data.results || r.data || [];
        setRecords(results);
        setTotal(r.data.count || results.length);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [scopeFilter]);

  const totalCO2e = records.reduce((acc, r) => acc + parseFloat(r.co2e_tonnes || 0), 0);

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Emission Records</h1>
          <p style={styles.subtitle}>Locked records ready for audit — immutable once approved</p>
        </div>
        <div style={styles.totalBadge}>
          <div style={styles.totalNum}>{totalCO2e.toFixed(3)}</div>
          <div style={styles.totalUnit}>tCO₂e total (locked)</div>
        </div>
      </div>

      <div style={styles.filters}>
        {[
          { val: '', label: 'All Scopes' },
          { val: 'scope1', label: 'Scope 1' },
          { val: 'scope2_location', label: 'Scope 2' },
          { val: 'scope3', label: 'Scope 3' },
        ].map(({ val, label }) => (
          <button
            key={val}
            style={{ ...styles.filterBtn, ...(scopeFilter === val ? styles.filterActive : {}) }}
            onClick={() => setScopeFilter(val)}
          >
            {label}
          </button>
        ))}
        <span style={styles.countHint}>{total} records</span>
      </div>

      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[...Array(6)].map((_, i) => <div key={i} className="skeleton" style={{ height: 52 }} />)}
        </div>
      ) : records.length === 0 ? (
        <div style={styles.empty}>
          <div style={styles.emptyIcon}>◉</div>
          <div style={styles.emptyText}>No locked emission records yet.</div>
          <div style={styles.emptySub}>Upload data, review it, then approve batches to generate locked records.</div>
        </div>
      ) : (
        <div style={styles.table}>
          <div style={styles.tableHead}>
            <span style={{ flex: 1 }}>Scope / Category</span>
            <span style={{ width: 160 }}>Activity Period</span>
            <span style={{ width: 120, textAlign: 'right' }}>Activity</span>
            <span style={{ width: 100, textAlign: 'right' }}>EF</span>
            <span style={{ width: 120, textAlign: 'right' }}>tCO₂e</span>
            <span style={{ width: 80, textAlign: 'center' }}>Source</span>
            <span style={{ width: 60, textAlign: 'center' }}>Locked</span>
          </div>
          {records.map(rec => {
            const scopeStyle = SCOPE_COLORS[rec.scope] || SCOPE_COLORS['scope3'];
            return (
              <div key={rec.id} style={styles.row}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ ...styles.scopeBadge, background: scopeStyle.bg, color: scopeStyle.text }}>
                    {scopeStyle.label}
                  </span>
                  <span style={styles.category}>{rec.category_display}</span>
                </div>
                <div style={{ width: 160, fontSize: 12, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>
                  {fmtDate(rec.activity_period_start)}
                  {rec.activity_period_start !== rec.activity_period_end && (
                    <> – {fmtDate(rec.activity_period_end)}</>
                  )}
                </div>
                <div style={{ width: 120, textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text)' }}>
                  {parseFloat(rec.activity_value).toFixed(2)} {rec.activity_unit}
                </div>
                <div style={{ width: 100, textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)' }}>
                  {parseFloat(rec.emission_factor).toFixed(4)}
                </div>
                <div style={{ width: 120, textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>
                  {parseFloat(rec.co2e_tonnes).toFixed(4)}
                </div>
                <div style={{ width: 80, textAlign: 'center' }}>
                  <span style={styles.sourceDot}>
                    {rec.source_sap_row ? 'SAP' : rec.source_utility_row ? 'Util' : 'Travel'}
                  </span>
                </div>
                <div style={{ width: 60, textAlign: 'center' }}>
                  {rec.is_locked ? (
                    <span style={styles.lockedIcon} title={`Locked ${fmtDate(rec.locked_at)}`}>🔒</span>
                  ) : (
                    <span style={{ color: 'var(--text-3)', fontSize: 12 }}>—</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div style={styles.auditNote}>
        <span style={styles.auditIcon}>🔒</span>
        <span>Locked records are immutable. Corrections create new records with a supersession link — originals are never modified. Emission factors: IPCC AR6 / DEFRA 2023 / CEA CO₂ Baseline Database v18 (March 2024).</span>
      </div>
    </div>
  );
}

const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: 24 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  title: { fontSize: 24, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-display)', fontStyle: 'italic' },
  subtitle: { fontSize: 13, color: 'var(--text-3)', marginTop: 4 },
  totalBadge: { textAlign: 'right', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '12px 20px' },
  totalNum: { fontSize: 28, fontWeight: 300, fontFamily: 'var(--font-mono)', color: 'var(--accent)' },
  totalUnit: { fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 2 },
  filters: { display: 'flex', gap: 6, alignItems: 'center' },
  filterBtn: { background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-3)', padding: '6px 14px', borderRadius: 999, fontSize: 12, cursor: 'pointer' },
  filterActive: { background: 'var(--accent-dim)', borderColor: 'var(--accent)', color: 'var(--accent)' },
  countHint: { marginLeft: 'auto', fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' },
  table: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' },
  tableHead: { display: 'flex', alignItems: 'center', padding: '10px 20px', borderBottom: '1px solid var(--border)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', gap: 12 },
  row: { display: 'flex', alignItems: 'center', padding: '12px 20px', borderBottom: '1px solid var(--border)', gap: 12, transition: 'background 0.12s' },
  scopeBadge: { display: 'inline-block', padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 500, marginRight: 8 },
  category: { fontSize: 12, color: 'var(--text-3)' },
  sourceDot: { fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', background: 'var(--surface-2)', padding: '2px 6px', borderRadius: 3 },
  lockedIcon: { fontSize: 13 },
  empty: { textAlign: 'center', padding: '60px 40px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' },
  emptyIcon: { fontSize: 32, color: 'var(--text-3)', marginBottom: 12 },
  emptyText: { fontSize: 16, fontWeight: 500, color: 'var(--text)', marginBottom: 6 },
  emptySub: { fontSize: 13, color: 'var(--text-3)' },
  auditNote: { display: 'flex', gap: 10, padding: '14px 16px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5 },
  auditIcon: { fontSize: 14, flexShrink: 0, marginTop: 1 },
};
