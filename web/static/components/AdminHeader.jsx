// AdminHeader — neon nav for admin pages.
const { useState: useAdmHState } = React;

function AdminHeader({ route, user, balance, brandName, onToggleAdminMode, onNavigate, onLogout }) {
  const navItems = [
    { key: 'admin',         label: 'Дашборд',  icon: '📊' },
    { key: 'admin-users',   label: 'Юзеры',    icon: '👥' },
    { key: 'admin-orders',  label: 'Заказы',   icon: '📋' },
    { key: 'admin-support', label: 'Чаты',     icon: '💬' },
  ];

  return (
    <header className="header">
      <div className="header__inner">
        <div className="header__logo" onClick={() => onNavigate('admin')}>
          <div className="header__logo-mark" style={{ fontWeight: 900, fontSize: '0.7rem', letterSpacing: '-0.02em' }}>AD</div>
          <span className="header__logo-name">{brandName} · admin</span>
        </div>

        <nav className="desktop-only" style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 16 }}>
          {navItems.map(n => (
            <button
              key={n.key}
              onClick={() => onNavigate(n.key)}
              style={{
                background: route === n.key ? 'var(--primary-dim)' : 'transparent',
                border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '5px 12px', borderRadius: 8,
                fontSize: '0.875rem', fontWeight: route === n.key ? 700 : 500,
                color: route === n.key ? 'var(--primary)' : 'var(--text-2)',
              }}
            >
              <span style={{ fontSize: '0.85em' }}>{n.icon}</span>
              {n.label}
            </button>
          ))}
        </nav>

        <div className="header__spacer" />

        <div className="header__actions">
          <button
            className="admin-toggle admin-toggle--on"
            onClick={onToggleAdminMode}
            title="Выйти из админ-режима"
          >
            🛠 Выйти из админ-режима
          </button>
          <button
            className="theme-toggle"
            onClick={onLogout}
            title="Выйти из аккаунта"
            style={{ padding: '3px 10px', fontSize: '0.78rem', color: 'var(--status-cancel-text)' }}
          >
            ↩
          </button>
        </div>
      </div>
    </header>
  );
}

Object.assign(window, { AdminHeader });
