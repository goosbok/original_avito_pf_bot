// AdminHeader — neon nav for admin pages. Desktop: inline tabs. Mobile: burger menu.
const { useState: useAdmHState, useEffect: useAdmHEffect, useRef: useAdmHRef } = React;

function AdmIconLogout() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}

function AdmIconBurger() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

function AdminHeader({ route, user, balance, brandName, onToggleAdminMode, onNavigate, onLogout }) {
  const [menuOpen, setMenuOpen] = useAdmHState(false);
  const menuRef = useAdmHRef(null);

  const navItems = [
    { key: 'admin',         label: 'Дашборд',       icon: '📊' },
    { key: 'admin-users',   label: 'Юзеры',         icon: '👥' },
    { key: 'admin-orders',  label: 'Заказы',        icon: '📋' },
    { key: 'admin-support', label: 'Тех Поддержка', icon: '💬' },
  ];

  // Close mobile menu on outside click
  useAdmHEffect(() => {
    if (!menuOpen) return;
    const onDown = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [menuOpen]);

  const handleNav = (key) => { setMenuOpen(false); onNavigate(key); };

  return (
    <header className="header">
      <div className="header__inner">
        <div className="header__logo" onClick={() => onNavigate('admin')}>
          <div className="header__logo-mark" style={{
            background: 'var(--primary)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 900, fontSize: '0.7rem', letterSpacing: '-0.02em',
          }}>AD</div>
          <span className="header__logo-name">{brandName} · admin</span>
        </div>

        <nav className="desktop-only" style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 16 }}>
          {navItems.map(n => (
            <button
              key={n.key}
              className={`admin-nav__tab${route === n.key ? ' admin-nav__tab--active' : ''}`}
              onClick={() => onNavigate(n.key)}
            >
              <span style={{ fontSize: '0.95em' }}>{n.icon}</span>
              {n.label}
            </button>
          ))}
        </nav>

        <div className="header__spacer" />

        <div className="header__actions">
          {/* Exit admin mode — top-level, icon-only on mobile (label hidden by .admin-toggle__label CSS) */}
          <button
            className="admin-toggle admin-toggle--on"
            onClick={onToggleAdminMode}
            title="Обычный режим"
            aria-label="Обычный режим"
          >
            <span className="admin-toggle__icon" aria-hidden="true">🛠</span>
            <span className="admin-toggle__label">Обычный режим</span>
          </button>

          {/* Logout — desktop only; on mobile lives inside burger menu */}
          <button
            className="btn btn--ghost btn--icon desktop-only"
            onClick={onLogout}
            title="Выйти из аккаунта"
            aria-label="Выйти из аккаунта"
          >
            <AdmIconLogout />
          </button>

          {/* Mobile burger — opens nav menu */}
          <div ref={menuRef} className="mobile-only" style={{ position: 'relative' }}>
            <button
              className="btn btn--ghost btn--icon"
              onClick={() => setMenuOpen(v => !v)}
              title="Меню"
              aria-label="Меню"
            >
              <AdmIconBurger />
            </button>
            {menuOpen && (
              <div className="admin-mobile-menu">
                {navItems.map(n => (
                  <button
                    key={n.key}
                    className={`admin-mobile-menu__item${route === n.key ? ' admin-mobile-menu__item--active' : ''}`}
                    onClick={() => handleNav(n.key)}
                  >
                    <span style={{ fontSize: '1em' }}>{n.icon}</span>
                    {n.label}
                  </button>
                ))}
                <div className="admin-mobile-menu__divider" />
                <button
                  className="admin-mobile-menu__item"
                  onClick={() => { setMenuOpen(false); onLogout(); }}
                  style={{ color: '#dc3545' }}
                >
                  <AdmIconLogout /> Выйти из аккаунта
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

Object.assign(window, { AdminHeader });
