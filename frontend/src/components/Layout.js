import React, { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const NAV = [
  { to: '/', label: 'Dashboard', icon: '◈', exact: true },
  { to: '/batches', label: 'Ingestion Queue', icon: '⊞' },
  { to: '/upload', label: 'Upload Data', icon: '↑' },
  { to: '/emissions', label: 'Emission Records', icon: '◉' },
];

export default function Layout() {
  const { user, org, logout } = useAuth();
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    await logout();
    navigate('/login');
  };

  return (
    <div style={styles.root}>
      {/* Sidebar */}
      <aside style={styles.sidebar}>
        {/* Logo */}
        <div style={styles.logo}>
          <span style={styles.logoIcon}>◈</span>
          <div>
            <div style={styles.logoName}>Breathe ESG</div>
            <div style={styles.logoSub}>Data Platform</div>
          </div>
        </div>

        {/* Org badge */}
        {org && (
          <div style={styles.orgBadge}>
            <div style={styles.orgDot} />
            <div>
              <div style={styles.orgName}>{org.name}</div>
              <div style={styles.orgRole}>{org.role}</div>
            </div>
          </div>
        )}

        <div style={styles.divider} />

        {/* Nav */}
        <nav style={styles.nav}>
          {NAV.map(({ to, label, icon, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              style={({ isActive }) => ({
                ...styles.navLink,
                ...(isActive ? styles.navLinkActive : {}),
              })}
            >
              <span style={styles.navIcon}>{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        <div style={{ flex: 1 }} />

        {/* User */}
        <div style={styles.userSection}>
          <div style={styles.userAvatar}>
            {(user?.name || user?.username || 'U')[0].toUpperCase()}
          </div>
          <div style={styles.userInfo}>
            <div style={styles.userName}>{user?.name || user?.username}</div>
            <div style={styles.userEmail}>{user?.email}</div>
          </div>
          <button
            onClick={handleLogout}
            disabled={loggingOut}
            style={styles.logoutBtn}
            title="Sign out"
          >
            ⎋
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main style={styles.main}>
        <div style={styles.content}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}

const styles = {
  root: {
    display: 'flex',
    height: '100vh',
    overflow: 'hidden',
    background: 'var(--bg)',
  },
  sidebar: {
    width: 220,
    minWidth: 220,
    background: 'var(--surface)',
    borderRight: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    padding: '20px 0',
    gap: 0,
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '0 20px 20px',
  },
  logoIcon: {
    fontSize: 22,
    color: 'var(--accent)',
    lineHeight: 1,
  },
  logoName: {
    fontFamily: 'var(--font-display)',
    fontSize: 16,
    color: 'var(--text)',
    lineHeight: 1.2,
    fontStyle: 'italic',
  },
  logoSub: {
    fontSize: 10,
    color: 'var(--text-3)',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  orgBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    margin: '0 12px',
    padding: '8px 10px',
    background: 'var(--accent-dim)',
    borderRadius: 'var(--radius)',
    border: '1px solid rgba(34,211,160,0.15)',
  },
  orgDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: 'var(--accent)',
    flexShrink: 0,
    animation: 'pulse-dot 2s infinite',
  },
  orgName: {
    fontSize: 11,
    fontWeight: 500,
    color: 'var(--text)',
    lineHeight: 1.3,
  },
  orgRole: {
    fontSize: 10,
    color: 'var(--accent)',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
  divider: {
    height: 1,
    background: 'var(--border)',
    margin: '16px 0',
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    padding: '0 8px',
  },
  navLink: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '9px 12px',
    borderRadius: 'var(--radius)',
    color: 'var(--text-2)',
    fontSize: 13,
    fontWeight: 400,
    textDecoration: 'none',
    transition: 'all 0.15s',
  },
  navLinkActive: {
    color: 'var(--accent)',
    background: 'var(--accent-dim)',
    fontWeight: 500,
  },
  navIcon: {
    fontSize: 14,
    width: 16,
    textAlign: 'center',
  },
  userSection: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '16px 12px 0',
    borderTop: '1px solid var(--border)',
  },
  userAvatar: {
    width: 28,
    height: 28,
    borderRadius: '50%',
    background: 'var(--accent-dim)',
    color: 'var(--accent)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 12,
    fontWeight: 600,
    flexShrink: 0,
  },
  userInfo: {
    flex: 1,
    minWidth: 0,
  },
  userName: {
    fontSize: 12,
    fontWeight: 500,
    color: 'var(--text)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  userEmail: {
    fontSize: 10,
    color: 'var(--text-3)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  logoutBtn: {
    background: 'none',
    color: 'var(--text-3)',
    fontSize: 16,
    padding: '4px',
    borderRadius: 'var(--radius)',
    transition: 'color 0.15s',
    flexShrink: 0,
  },
  main: {
    flex: 1,
    overflow: 'auto',
    background: 'var(--bg)',
  },
  content: {
    padding: '32px',
    maxWidth: 1300,
    margin: '0 auto',
    animation: 'fadeIn 0.25s ease',
  },
};
