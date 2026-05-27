import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts';
import { dashboardAPI, batchAPI } from '../utils/api';
import { useAuth } from '../hooks/useAuth';

const fmt = (n, d = 2) => (typeof n === 'number' ? n.toFixed(d) : '—');
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';

function StatCard({ label, value, unit, color, sub }) {
  return (
    <div style={{ ...styles.statCard, borderTop: `2px solid ${color || 'var(--border)'}` }}>
      <div style={styles.statLabel}>{label}</div>
      <div style={styles.statValue}>
        <span style={{ color: color || 'var(--text)' }}>{value}</span>
        {unit && <span style={styles.statUnit}>{unit}</span>}
      </div>
      {sub && <div style={styles.statSub}>{sub}</div>}
    </div>
  );
}

function AlertRow({ icon, text, color, onClick }) {
  return (
    <div style={{ ...styles.alertRow, borderLeft: `3px solid ${color}`, cursor: onClick ? 'pointer' : 'default' }} onClick={onClick}>
      <span style={{ color }}>{icon}</span>
      <span style={styles.alertText}>{text}</span>
      {onClick && <span style={styles.alertArrow}>→</span>}
    </div>
  );
}

const SCOPE_COLORS = { scope1: '#f97316', scope2: '#3b82f6', scope3: '#a855f7' };
const PIE_DATA = (stats) => [
  { name: 'Scope 1', value: stats.scope1_tonnes || 0, color: '#f97316' },
  { name: 'Scope 2', value: stats.scope2_tonnes || 0, color: '#3b82f6' },
  { name: 'Scope 3', value: stats.scope3_tonnes || 0, color: '#a855f7' },
];

const SOURCE_LABELS = {
  sap_fuel_procurement: 'SAP Fuel',
  utility_electricity: 'Electricity',
  travel_corporate: 'Travel',
};

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [recentBatches, setRecentBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const { org } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      dashboardAPI.stats(),
      batchAPI.list({ page_size: 5 }),
    ]).then(([s, b]) => {
      setStats(s.data);
      setRecentBatches(b.data.results || []);
    }).catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;
  if (!stats) return <div style={{ color: 'var(--text-2)' }}>Failed to load dashboard.</div>;

  const pieData = PIE_DATA(stats).filter(d => d.value > 0);
  const totalSuspicious = (stats.suspicious_rows?.sap || 0)
    + (stats.suspicious_rows?.utility || 0)
    + (stats.suspicious_rows?.travel || 0);

  return (
    <div style={styles.root}>
      {/* Page header */}
      <div style={styles.pageHeader}>
        <div>
          <h1 style={styles.title}>Dashboard</h1>
          <p style={styles.subtitle}>{org?.name} · Q1 FY2024–25 Overview</p>
        </div>
        <button style={styles.uploadBtn} onClick={() => navigate('/upload')}>
          ↑ Upload Data
        </button>
      </div>

      {/* Alerts */}
      {(stats.pending_batches > 0 || totalSuspicious > 0) && (
        <div style={styles.alertsBox}>
          {stats.pending_batches > 0 && (
            <AlertRow
              icon="⊡"
              color="var(--warn)"
              text={`${stats.pending_batches} batch${stats.pending_batches > 1 ? 'es' : ''} pending analyst review`}
              onClick={() => navigate('/batches?status=pending')}
            />
          )}
          {totalSuspicious > 0 && (
            <AlertRow
              icon="⚠"
              color="var(--warn)"
              text={`${totalSuspicious} row${totalSuspicious > 1 ? 's' : ''} flagged suspicious across all sources`}
              onClick={() => navigate('/batches')}
            />
          )}
        </div>
      )}

      {/* KPI cards */}
      <div style={styles.statsGrid}>
        <StatCard
          label="Total tCO₂e (locked)"
          value={fmt(stats.total_co2e_tonnes)}
          unit="tCO₂e"
          color="var(--accent)"
          sub="Approved & locked records only"
        />
        <StatCard
          label="Scope 1"
          value={fmt(stats.scope1_tonnes)}
          unit="tCO₂e"
          color="var(--scope1)"
          sub="Direct combustion (SAP)"
        />
        <StatCard
          label="Scope 2"
          value={fmt(stats.scope2_tonnes)}
          unit="tCO₂e"
          color="var(--scope2)"
          sub="Location-based, CEA 2023-24"
        />
        <StatCard
          label="Scope 3"
          value={fmt(stats.scope3_tonnes)}
          unit="tCO₂e"
          color="var(--scope3)"
          sub="Business travel (Cat. 6)"
        />
      </div>

      {/* Batch stats row */}
      <div style={styles.batchStatsRow}>
        {[
          { label: 'Total Batches', val: stats.total_batches, color: 'var(--text-2)' },
          { label: 'Pending Review', val: stats.pending_batches, color: 'var(--warn)' },
          { label: 'Approved', val: stats.approved_batches, color: 'var(--accent)' },
          { label: 'Rejected', val: stats.rejected_batches || 0, color: 'var(--danger)' },
        ].map(({ label, val, color }) => (
          <div key={label} style={styles.batchStat}>
            <div style={{ ...styles.batchStatNum, color }}>{val}</div>
            <div style={styles.batchStatLabel}>{label}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={styles.chartsRow}>
        {/* Monthly stacked bar */}
        <div style={styles.chartCard}>
          <div style={styles.chartTitle}>Monthly Emissions (tCO₂e)</div>
          {stats.by_month?.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={stats.by_month} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <XAxis dataKey="month" tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                  labelStyle={{ color: 'var(--text)' }}
                />
                <Bar dataKey="scope1" stackId="a" fill="#f97316" name="Scope 1" radius={[0,0,0,0]} />
                <Bar dataKey="scope2" stackId="a" fill="#3b82f6" name="Scope 2" />
                <Bar dataKey="scope3" stackId="a" fill="#a855f7" name="Scope 3" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={styles.emptyChart}>No approved records yet — upload and approve batches to see data.</div>
          )}
        </div>

        {/* Pie */}
        <div style={{ ...styles.chartCard, width: 280, flexShrink: 0 }}>
          <div style={styles.chartTitle}>Breakdown by Scope</div>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} dataKey="value" paddingAngle={3}>
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: 'var(--text-2)' }} />
                <Tooltip
                  formatter={(v) => [`${v.toFixed(2)} tCO₂e`]}
                  contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div style={styles.emptyChart}>—</div>
          )}
        </div>
      </div>

      {/* Source breakdown + Recent batches */}
      <div style={styles.bottomRow}>
        {/* Source breakdown */}
        <div style={styles.sourceBreakdown}>
          <div style={styles.sectionTitle}>Emissions by Source</div>
          {Object.entries(stats.by_source || {}).map(([key, val]) => {
            const total = stats.total_co2e_tonnes || 1;
            const pct = total > 0 ? (val / total * 100) : 0;
            return (
              <div key={key} style={styles.sourceRow}>
                <div style={styles.sourceRowLeft}>
                  <span style={styles.sourceRowLabel}>{SOURCE_LABELS[key] || key}</span>
                  <span style={styles.sourceRowVal}>{val.toFixed(2)} tCO₂e</span>
                </div>
                <div style={styles.sourceBar}>
                  <div style={{
                    ...styles.sourceBarFill,
                    width: `${pct}%`,
                    background: key === 'sap_fuel_procurement'
                      ? 'var(--scope1)'
                      : key === 'utility_electricity'
                      ? 'var(--scope2)'
                      : 'var(--scope3)',
                  }} />
                </div>
                <span style={styles.sourcePct}>{pct.toFixed(1)}%</span>
              </div>
            );
          })}
        </div>

        {/* Recent batches */}
        <div style={styles.recentBatches}>
          <div style={{ ...styles.sectionTitle, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Recent Batches</span>
            <button style={styles.viewAllBtn} onClick={() => navigate('/batches')}>View all →</button>
          </div>
          {recentBatches.length === 0 ? (
            <div style={styles.emptyChart}>No batches yet.</div>
          ) : (
            <div style={styles.batchList}>
              {recentBatches.map(batch => (
                <div key={batch.id} style={styles.batchRow} onClick={() => navigate(`/batches/${batch.id}`)}>
                  <div style={styles.batchRowLeft}>
                    <div style={styles.batchRowName}>{batch.original_filename || 'Upload'}</div>
                    <div style={styles.batchRowMeta}>
                      {SOURCE_LABELS[batch.source_type]} · {fmtDate(batch.uploaded_at)}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={styles.batchRowStats}>
                      <span style={{ color: 'var(--accent)' }}>{batch.rows_parsed}</span>
                      {batch.rows_suspicious > 0 && <span style={{ color: 'var(--warn)' }}>+{batch.rows_suspicious}⚠</span>}
                      {batch.rows_failed > 0 && <span style={{ color: 'var(--danger)' }}>{batch.rows_failed}✕</span>}
                    </div>
                    <span className={`badge badge-${batch.status}`}>{batch.status_display}</span>
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

function LoadingSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="skeleton" style={{ height: 36, width: 260 }} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {[...Array(4)].map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 100 }} />
        ))}
      </div>
      <div className="skeleton" style={{ height: 260 }} />
    </div>
  );
}

const styles = {
  root: { display: 'flex', flexDirection: 'column', gap: 24 },
  pageHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  title: { fontSize: 24, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-display)', fontStyle: 'italic' },
  subtitle: { fontSize: 13, color: 'var(--text-3)', marginTop: 4 },
  uploadBtn: { background: 'var(--accent)', color: '#000', fontWeight: 600, fontSize: 13, padding: '9px 18px', borderRadius: 'var(--radius)', cursor: 'pointer' },
  alertsBox: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' },
  alertRow: { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderBottom: '1px solid var(--border)', fontSize: 13 },
  alertText: { flex: 1, color: 'var(--text-2)' },
  alertArrow: { color: 'var(--text-3)', fontSize: 14 },
  statsGrid: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 },
  statCard: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '20px 20px 16px' },
  statLabel: { fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 },
  statValue: { fontSize: 28, fontWeight: 300, color: 'var(--text)', lineHeight: 1, marginBottom: 8, fontFamily: 'var(--font-mono)' },
  statUnit: { fontSize: 13, color: 'var(--text-3)', marginLeft: 4 },
  statSub: { fontSize: 11, color: 'var(--text-3)' },
  batchStatsRow: { display: 'flex', gap: 0, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' },
  batchStat: { flex: 1, padding: '16px 20px', borderRight: '1px solid var(--border)', textAlign: 'center' },
  batchStatNum: { fontSize: 22, fontWeight: 600, fontFamily: 'var(--font-mono)' },
  batchStatLabel: { fontSize: 11, color: 'var(--text-3)', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.06em' },
  chartsRow: { display: 'flex', gap: 16 },
  chartCard: { flex: 1, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '20px' },
  chartTitle: { fontSize: 12, fontWeight: 500, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 },
  emptyChart: { color: 'var(--text-3)', fontSize: 13, padding: '40px 0', textAlign: 'center' },
  bottomRow: { display: 'flex', gap: 16 },
  sourceBreakdown: { width: 280, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 20, flexShrink: 0 },
  recentBatches: { flex: 1, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 20 },
  sectionTitle: { fontSize: 11, fontWeight: 500, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 },
  sourceRow: { marginBottom: 14 },
  sourceRowLeft: { display: 'flex', justifyContent: 'space-between', marginBottom: 5 },
  sourceRowLabel: { fontSize: 12, color: 'var(--text-2)' },
  sourceRowVal: { fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text)' },
  sourceBar: { height: 4, background: 'var(--surface-3)', borderRadius: 2, marginBottom: 4 },
  sourceBarFill: { height: '100%', borderRadius: 2, transition: 'width 0.5s ease' },
  sourcePct: { fontSize: 10, color: 'var(--text-3)' },
  viewAllBtn: { background: 'none', color: 'var(--accent)', fontSize: 12, cursor: 'pointer', padding: 0 },
  batchList: { display: 'flex', flexDirection: 'column', gap: 2 },
  batchRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderRadius: 'var(--radius)', cursor: 'pointer', transition: 'background 0.12s', ':hover': { background: 'var(--surface-2)' } },
  batchRowLeft: { flex: 1, minWidth: 0 },
  batchRowName: { fontSize: 13, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  batchRowMeta: { fontSize: 11, color: 'var(--text-3)', marginTop: 2 },
  batchRowStats: { display: 'flex', gap: 6, fontSize: 12, fontFamily: 'var(--font-mono)' },
};
