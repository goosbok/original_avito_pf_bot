// AppHeader — sticky navigation with quick nav, user dropdown
const { useState: useHeaderState, useEffect: useHeaderEffect, useRef: useHeaderRef } = React;

function Avatar({ name, size = 30 }) {
  const initials = (name || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: 'var(--primary)', color: '#fff',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.38, fontWeight: 700, flexShrink: 0, userSelect: 'none'
    }}>
      {initials}
    </div>
  );
}

function NavLink({ label, active, onClick, icon }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit',
        display: 'flex', alignItems: 'center', gap: 5,
        padding: '5px 10px', borderRadius: 8,
        fontSize: '0.875rem', fontWeight: active ? 700 : 500,
        color: active ? 'var(--primary)' : 'var(--text-2)',
        background: active ? 'var(--primary-dim)' : 'transparent',
        transition: 'color 0.15s, background 0.15s',
        whiteSpace: 'nowrap',
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.color = 'var(--text-1)'; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.color = 'var(--text-2)'; }}
    >
      {icon && <span style={{ fontSize: '0.85em' }}>{icon}</span>}
      {label}
    </button>
  );
}

function scrollToSection(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function AppHeader({ route, user, balance, brandName, theme, adminMode, onToggleTheme, onToggleAdminMode, onNavigate, onLogout }) {
  const [menuOpen, setMenuOpen] = useHeaderState(false);
  const [userDropOpen, setUserDropOpen] = useHeaderState(false);
  const dropRef = useHeaderRef(null);

  const isApp = !['landing', 'login', 'register', 'login-tg', 'auth'].includes(route);
  const isLanding = route === 'landing';

  // Close dropdown on outside click
  useHeaderEffect(() => {
    const handler = (e) => {
      if (dropRef.current && !dropRef.current.contains(e.target)) setUserDropOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Close mobile menu on route change
  useHeaderEffect(() => { setMenuOpen(false); setUserDropOpen(false); }, [route]);

  const navItems = [
    { label: 'Кабинет',  route: 'cabinet', icon: '🏠' },
    { label: 'Заказы',   route: 'orders',  icon: '📋' },
  ];

  return (
    <header className="header">
      <div className="header__inner">

        {/* Logo */}
        <div
          className="header__logo"
          onClick={() => onNavigate(user ? 'cabinet' : 'landing')}
        >
          <div className="header__logo-mark" style={{ fontWeight: 900, fontSize: '0.75rem', letterSpacing: '-0.02em' }}>PB</div>
          <span className="header__logo-name">{brandName}</span>
        </div>

        {/* Desktop center nav — app only */}
        {isApp && user && (
          <nav className="desktop-only" style={{ display: 'flex', alignItems: 'center', gap: 2, marginLeft: 16 }}>
            {navItems.map(n => (
              <NavLink
                key={n.route}
                label={n.label}
                icon={n.icon}
                active={route === n.route}
                onClick={() => onNavigate(n.route)}
              />
            ))}
            <div style={{ width: 1, height: 18, background: 'var(--border)', margin: '0 6px' }} />
            <button
              className="btn btn--primary btn--sm"
              onClick={() => onNavigate('order-pf')}
              style={{ padding: '5px 14px', fontSize: '0.8125rem' }}
            >
              + Заказать ПФ
            </button>
          </nav>
        )}

        {/* Landing nav links — desktop */}
        {isLanding && (
          <nav className="desktop-only" style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 20 }}>
            <NavLink label="Услуги" active={false} onClick={() => scrollToSection('services')} />
            <NavLink label="FAQ" active={false} onClick={() => scrollToSection('faq')} />
            <NavLink label="Контакты" active={false} onClick={() => scrollToSection('contacts')} />
          </nav>
        )}

        <div className="header__spacer" />

        {/* Right actions */}
        <div className="header__actions">

          {/* Admin-mode toggle (only for admins) */}
          {isApp && user && user.is_admin && (
            <button
              className={`admin-toggle${adminMode ? ' admin-toggle--on' : ''}`}
              onClick={onToggleAdminMode}
              title="Переключить админ-режим"
            >
              🛠 Админ
            </button>
          )}

          {/* Balance badge */}
          {isApp && user && (
            <div className="balance-badge desktop-only">
              {balance.toLocaleString('ru-RU')} ₽
            </div>
          )}

          {/* Theme toggle — sun/moon pill switch */}
          <button
            className={`theme-toggle theme-toggle--${theme}`}
            onClick={onToggleTheme}
            title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
            aria-label="Переключить тему"
          >
            <span className="theme-toggle__opt theme-toggle__opt--sun" aria-hidden="true">☀</span>
            <span className="theme-toggle__opt theme-toggle__opt--moon" aria-hidden="true">☾</span>
            <span className="theme-toggle__thumb" />
          </button>

          {/* Auth buttons — landing desktop */}
          {!isApp && !user && (
            <>
              <button className="btn btn--ghost btn--sm desktop-only" onClick={() => onNavigate('login')}>
                Войти
              </button>
              <button className="btn btn--primary btn--sm desktop-only" onClick={() => onNavigate('register')}>
                Регистрация
              </button>
            </>
          )}

          {/* User dropdown — desktop, app */}
          {isApp && user && (
            <div ref={dropRef} style={{ position: 'relative' }} className="desktop-only">
              <button
                onClick={() => setUserDropOpen(v => !v)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  background: userDropOpen ? 'var(--surface-2)' : 'transparent',
                  border: '1.5px solid var(--border)', borderRadius: 24,
                  padding: '4px 10px 4px 4px', cursor: 'pointer',
                  transition: 'background 0.15s',
                }}
              >
                <Avatar name={user.first_name} size={26} />
                <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-1)' }}>
                  {user.first_name}
                </span>
                <span style={{ fontSize: '0.65rem', color: 'var(--text-3)', marginLeft: -2 }}>▾</span>
              </button>

              {userDropOpen && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 8px)', right: 0,
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)',
                  minWidth: 200, zIndex: 300, overflow: 'hidden'
                }}>
                  {/* User info header */}
                  <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                      <Avatar name={user.first_name} size={36} />
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{user.first_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>
                          @{user.user_name || 'user'}
                        </div>
                      </div>
                    </div>
                    <div style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      background: 'var(--balance-bg)', borderRadius: 8, padding: '8px 10px'
                    }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--balance-text)', fontWeight: 600 }}>Баланс</span>
                      <span style={{ fontSize: '0.9rem', fontWeight: 800, color: 'var(--balance-text)' }}>
                        {balance.toLocaleString('ru-RU')} ₽
                      </span>
                    </div>
                  </div>

                  {/* Nav items */}
                  {[
                    { icon: '🏠', label: 'Кабинет',      action: () => onNavigate('cabinet') },
                    { icon: '📋', label: 'Мои заказы',   action: () => onNavigate('orders') },
                    { icon: '👤', label: 'Профиль',       action: () => onNavigate('profile') },
                  ].map((item, i) => (
                    <button
                      key={i}
                      onClick={() => { setUserDropOpen(false); item.action(); }}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                        padding: '10px 16px', background: 'none', border: 'none',
                        cursor: 'pointer', fontFamily: 'inherit', fontSize: '0.875rem',
                        color: 'var(--text-1)', textAlign: 'left',
                        transition: 'background 0.12s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-2)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'none'}
                    >
                      <span style={{ width: 18, textAlign: 'center' }}>{item.icon}</span>
                      {item.label}
                    </button>
                  ))}

                  <div style={{ height: 1, background: 'var(--border)', margin: '4px 0' }} />

                  <button
                    onClick={() => { setUserDropOpen(false); onLogout(); }}
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                      padding: '10px 16px', background: 'none', border: 'none',
                      cursor: 'pointer', fontFamily: 'inherit', fontSize: '0.875rem',
                      color: '#dc3545', textAlign: 'left', transition: 'background 0.12s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(220,53,69,0.05)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'none'}
                  >
                    <span style={{ width: 18, textAlign: 'center' }}>↩</span>
                    Выйти
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Mobile hamburger */}
          {(isApp && user) && (
            <div style={{ position: 'relative' }} className="mobile-only">
              <button
                className="theme-btn"
                onClick={() => setMenuOpen(v => !v)}
                aria-label="Меню"
              >
                {menuOpen ? '✕' : '☰'}
              </button>
              {menuOpen && (
                <div style={{
                  position: 'fixed', top: 'var(--header-h)', left: 0, right: 0,
                  background: 'var(--surface)', borderBottom: '1px solid var(--border)',
                  boxShadow: 'var(--shadow-lg)', zIndex: 200, padding: '8px 16px 16px'
                }}>
                  {/* User + balance */}
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '12px 0', borderBottom: '1px solid var(--border)', marginBottom: 8
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <Avatar name={user.first_name} size={34} />
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{user.first_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>@{user.user_name || 'user'}</div>
                      </div>
                    </div>
                    <div className="balance-badge">{balance.toLocaleString('ru-RU')} ₽</div>
                  </div>

                  {[
                    { label: 'Кабинет',     route: 'cabinet' },
                    { label: 'Мои заказы',  route: 'orders' },
                    { label: 'Заказать ПФ', route: 'order-pf' },
                  ].map(item => (
                    <button
                      key={item.route}
                      onClick={() => { setMenuOpen(false); onNavigate(item.route); }}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 12,
                        padding: '12px 4px', background: 'none', border: 'none',
                        borderBottom: '1px solid var(--border)',
                        cursor: 'pointer', fontFamily: 'inherit', fontSize: '0.9375rem',
                        color: route === item.route ? 'var(--primary)' : 'var(--text-1)',
                        fontWeight: route === item.route ? 700 : 400, textAlign: 'left',
                      }}
                    >
                      {item.label}
                      {route === item.route && <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--primary)' }}>●</span>}
                    </button>
                  ))}

                  <button
                    onClick={() => { setMenuOpen(false); onLogout(); }}
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', gap: 12,
                      padding: '12px 4px', marginTop: 4,
                      background: 'none', border: 'none',
                      cursor: 'pointer', fontFamily: 'inherit', fontSize: '0.9375rem',
                      color: '#dc3545', textAlign: 'left',
                    }}
                  >
                    Выйти
                  </button>
                </div>
              )}
            </div>
          )}

        </div>
      </div>
    </header>
  );
}

Object.assign(window, { AppHeader });
