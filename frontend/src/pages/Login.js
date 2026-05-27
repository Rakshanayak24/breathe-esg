import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login, loading } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const result = await login(username, password);
    if (result.success) {
      navigate('/');
    } else {
      setError(result.error);
    }
  };

  return (
    <div style={styles.root}>
      {/* Left panel */}
      <div style={styles.left}>
        <div style={styles.leftInner}>
          <div style={styles.logoMark}>◈</div>
          <h1 style={styles.brand}>Breathe ESG</h1>
          <p style={styles.tagline}>
            Carbon data ingestion &<br />
            <em>analyst review platform</em>
          </p>
          <div style={styles.pillsRow}>
            {['Scope 1', 'Scope 2', 'Scope 3'].map((s, i) => (
              <span key={i} style={{
                ...styles.pill,
                background: i === 0
                  ? 'rgba(249,115,22,0.15)'
                  : i === 1
                  ? 'rgba(59,130,246,0.15)'
                  : 'rgba(168,85,247,0.15)',
                color: i === 0 ? '#f97316' : i === 1 ? '#3b82f6' : '#a855f7',
              }}>{s}</span>
            ))}
          </div>
          <div style={styles.sources}>
            {[
              { label: 'SAP', sub: 'Fuel & Procurement' },
              { label: 'Utility', sub: 'Electricity Billing' },
              { label: 'Travel', sub: 'Navan / Concur' },
            ].map(({ label, sub }) => (
              <div key={label} style={styles.sourceCard}>
                <div style={styles.sourceLabel}>{label}</div>
                <div style={styles.sourceSub}>{sub}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right panel - login form */}
      <div style={styles.right}>
        <div style={styles.formCard}>
          <div style={styles.formHeader}>
            <h2 style={styles.formTitle}>Sign in</h2>
            <p style={styles.formSub}>Access your organisation's emissions data</p>
          </div>

          {error && (
            <div style={styles.errorBox}>
              <span>⚠</span> {error}
            </div>
          )}

          <form onSubmit={handleSubmit} style={styles.form}>
            <div style={styles.field}>
              <label style={styles.label}>Username</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="analyst"
                autoFocus
                required
                style={styles.input}
              />
            </div>
            <div style={styles.field}>
              <label style={styles.label}>Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                style={styles.input}
              />
            </div>
            <button type="submit" disabled={loading} style={styles.submitBtn}>
              {loading ? 'Signing in…' : 'Sign in →'}
            </button>
          </form>

          <div style={styles.demoHint}>
            <div style={styles.demoTitle}>Demo credentials</div>
            {[
              { u: 'analyst', p: 'breathe2024', r: 'Analyst' },
              { u: 'approver', p: 'breathe2024', r: 'Approver' },
            ].map(({ u, p, r }) => (
              <div key={u} style={styles.demoRow}>
                <button
                  type="button"
                  style={styles.demoBtn}
                  onClick={() => { setUsername(u); setPassword(p); }}
                >
                  <span style={styles.demoUser}>{u}</span>
                  <span style={styles.demoRole}>{r}</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const styles = {
  root: {
    display: 'flex',
    minHeight: '100vh',
    background: 'var(--bg)',
  },
  left: {
    flex: 1,
    background: 'linear-gradient(135deg, #0d1117 0%, #111820 50%, #0a1520 100%)',
    borderRight: '1px solid var(--border)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 48,
    position: 'relative',
    overflow: 'hidden',
  },
  leftInner: {
    maxWidth: 380,
  },
  logoMark: {
    fontSize: 40,
    color: 'var(--accent)',
    marginBottom: 16,
    display: 'block',
  },
  brand: {
    fontFamily: 'var(--font-display)',
    fontStyle: 'italic',
    fontSize: 42,
    color: 'var(--text)',
    lineHeight: 1.1,
    marginBottom: 12,
  },
  tagline: {
    fontSize: 18,
    color: 'var(--text-2)',
    lineHeight: 1.5,
    marginBottom: 28,
    fontFamily: 'var(--font-display)',
  },
  pillsRow: {
    display: 'flex',
    gap: 8,
    marginBottom: 36,
  },
  pill: {
    padding: '4px 12px',
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 500,
    letterSpacing: '0.04em',
  },
  sources: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  sourceCard: {
    padding: '12px 16px',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sourceLabel: {
    fontSize: 13,
    fontWeight: 500,
    color: 'var(--text)',
    fontFamily: 'var(--font-mono)',
  },
  sourceSub: {
    fontSize: 11,
    color: 'var(--text-3)',
  },
  right: {
    width: 420,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 40,
  },
  formCard: {
    width: '100%',
    maxWidth: 360,
  },
  formHeader: {
    marginBottom: 28,
  },
  formTitle: {
    fontSize: 22,
    fontWeight: 600,
    color: 'var(--text)',
    marginBottom: 4,
  },
  formSub: {
    fontSize: 13,
    color: 'var(--text-2)',
  },
  errorBox: {
    background: 'var(--danger-dim)',
    border: '1px solid rgba(239,68,68,0.3)',
    color: 'var(--danger)',
    borderRadius: 'var(--radius)',
    padding: '10px 14px',
    fontSize: 13,
    marginBottom: 20,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
    marginBottom: 24,
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  label: {
    fontSize: 12,
    fontWeight: 500,
    color: 'var(--text-2)',
    letterSpacing: '0.03em',
    textTransform: 'uppercase',
  },
  input: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    color: 'var(--text)',
    borderRadius: 'var(--radius)',
    padding: '10px 14px',
    fontSize: 14,
    transition: 'border-color 0.15s',
    outline: 'none',
  },
  submitBtn: {
    background: 'var(--accent)',
    color: '#000',
    fontWeight: 600,
    fontSize: 14,
    padding: '12px 20px',
    borderRadius: 'var(--radius)',
    cursor: 'pointer',
    transition: 'opacity 0.15s',
    marginTop: 4,
  },
  demoHint: {
    padding: '16px',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
  },
  demoTitle: {
    fontSize: 11,
    color: 'var(--text-3)',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    marginBottom: 10,
  },
  demoRow: {
    marginBottom: 6,
  },
  demoBtn: {
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    padding: '8px 12px',
    cursor: 'pointer',
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    transition: 'border-color 0.15s',
  },
  demoUser: {
    fontFamily: 'var(--font-mono)',
    fontSize: 13,
    color: 'var(--accent)',
  },
  demoRole: {
    fontSize: 11,
    color: 'var(--text-3)',
  },
};
