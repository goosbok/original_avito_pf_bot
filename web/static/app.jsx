// app.jsx — root state, session restore, routing
const { useState, useEffect } = React;

const TWEAK_DEFAULTS = {
  theme: 'light',
  variant: 'classic',
  brandName: 'ProBoost',
  accentColor: '#0088cc'
};

function App() {
  const _resetToken = new URLSearchParams(window.location.search).get('token');
  const _isResetRoute = window.location.pathname === '/reset-password' && !!_resetToken;
  // YooKassa redirect → /api/orders/pf/{id}/return → этот URL.
  // ?yookassa_return=paid|failed|unknown + ?order_id=N
  const _qs = new URLSearchParams(window.location.search);
  const _yookassaResult = _qs.get('yookassa_return');  // 'paid'|'failed'|'unknown'|null
  const _returnOrderId = (() => {
    const raw = _qs.get('order_id');
    const n = raw ? parseInt(raw, 10) : NaN;
    return Number.isFinite(n) && n > 0 ? n : null;
  })();
  // Решение начального route:
  // - yookassa_return=paid → order-detail (показать оплаченный заказ + таймер ушёл)
  // - yookassa_return=failed без логина → order-new (пусть переоформит)
  // - yookassa_return=failed с логином → orders (история заказов)
  // - yookassa_return=unknown / просто ?order_id=N → order-detail (там polling)
  // Логин ещё не восстановлен — для failed-случая откладываем решение
  // до loaderssession-restore useEffect ниже.
  const _initialRoute = (() => {
    if (_isResetRoute) return 'auth';
    if (_yookassaResult === 'paid') return 'order-detail';
    if (_yookassaResult === 'failed') return 'order-new';  // переопределим если залогинен
    if (_returnOrderId) return 'order-detail';
    return 'order-new';
  })();

  const [tweaks, setTweaks] = useState(TWEAK_DEFAULTS);
  const [route, setRoute] = useState(_initialRoute);
  const [authMode, setAuthMode] = useState(_isResetRoute ? 'reset' : 'login');
  const [resetToken] = useState(_isResetRoute ? _resetToken : null);
  const [user, setUser] = useState(null);
  const [balance, setBalance] = useState(0);
  const [appLoading, setAppLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [detailOrderId, setDetailOrderId] = useState(_returnOrderId);
  const [prefilledOrder, setPrefilledOrder] = useState(() => {
    try {
      const raw = sessionStorage.getItem('order_prefill');
      if (!raw) return null;
      sessionStorage.removeItem('order_prefill');
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  });
  const [botConfig, setBotConfig] = useState(null);
  const [adminMode, setAdminMode] = useState(
    () => localStorage.getItem('admin_mode') === '1'
  );

  // Reflect adminMode on <html> so platform.css applies the neon overrides.
  useEffect(() => {
    if (adminMode && user && user.is_admin) {
      document.documentElement.setAttribute('data-admin-mode', 'on');
    } else {
      document.documentElement.removeAttribute('data-admin-mode');
    }
  }, [adminMode, user]);

  // Force-off admin mode if the user signs out or isn't admin
  useEffect(() => {
    if (!user || !user.is_admin) setAdminMode(false);
  }, [user]);

  const toggleAdminMode = () => {
    const next = !adminMode;
    setAdminMode(next);
    localStorage.setItem('admin_mode', next ? '1' : '0');
    // When turning ON, jump to admin dashboard. When OFF, back to cabinet.
    setRoute(next ? 'admin' : 'cabinet');
  };

  // Load public config (bot deep-link, etc.) once
  useEffect(() => {
    api.get('/api/config').then(data => {
      if (data && !data.__unauthorized) setBotConfig(data);
    }).catch(() => {});
  }, []);

  // Apply theme + variant to <html>. In admin mode the panel is fully owned by
  // [data-admin-mode="on"] styles — pin a fixed dark/classic base and drop the
  // inline --primary so the user's regular-mode theme can't leak in.
  useEffect(() => {
    const isAdmin = adminMode && user && user.is_admin;
    if (isAdmin) {
      document.documentElement.setAttribute('data-theme', 'dark');
      document.documentElement.setAttribute('data-variant', 'classic');
      document.documentElement.style.removeProperty('--primary');
      return;
    }
    document.documentElement.setAttribute('data-theme', tweaks.theme);
    document.documentElement.setAttribute('data-variant', tweaks.variant);
    if (tweaks.accentColor) {
      document.documentElement.style.setProperty('--primary', tweaks.accentColor);
    }
  }, [tweaks, adminMode, user]);

  // Restore session from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) { setAppLoading(false); return; }
    api.get('/api/me').then(data => {
      if (data.__unauthorized) {
        localStorage.removeItem('access_token');
      } else {
        setUser({
          first_name: data.first_name,
          user_name: data.user_name,
          user_id: data.user_id,
          is_admin: !!data.is_admin,
        });
        setBalance(data.balance);
        // Route override на старте:
        // - yookassa_return=failed + залогинен → orders (история);
        //   незалогиненный остаётся на order-new (как _initialRoute уже выставил).
        // - yookassa_return=paid → order-detail (не перебиваем).
        // - просто ?order_id=N → order-detail (не перебиваем).
        // - иначе обычно cabinet.
        if (_yookassaResult === 'failed') {
          setRoute('orders');
        } else if (!_yookassaResult && !_returnOrderId) {
          setRoute('cabinet');
        }
      }
    }).catch(() => {
      localStorage.removeItem('access_token');
    }).finally(() => setAppLoading(false));
  }, []);

  // Чистим query (?yookassa_return, ?order_id) из URL после первой загрузки —
  // чтобы refresh не сбрасывал навигацию и URL выглядел опрятно.
  useEffect(() => {
    if ((_yookassaResult || _returnOrderId) && window.history && window.history.replaceState) {
      const url = new URL(window.location.href);
      url.searchParams.delete('order_id');
      url.searchParams.delete('yookassa_return');
      window.history.replaceState({}, '', url.toString());
    }
  }, []);

  const refreshBalance = () => {
    api.get('/api/me').then(data => {
      if (!data.__unauthorized) setBalance(data.balance);
    }).catch(() => {});
  };

  const setTweak = (key, val) => {
    setTweaks(prev => typeof key === 'object' ? { ...prev, ...key } : { ...prev, [key]: val });
  };

  const handleLogin = (token) => {
    localStorage.setItem('access_token', token);
    api.get('/api/me').then(data => {
      setUser({
        first_name: data.first_name,
        user_name: data.user_name,
        user_id: data.user_id,
        is_admin: !!data.is_admin,
      });
      setBalance(data.balance);
      // If user had a pending order prefill (stored before "Войти" in OrderForm step 2),
      // return them to order-new to finish creating the order. Otherwise → cabinet.
      let target = 'cabinet';
      try {
        const raw = sessionStorage.getItem('order_prefill');
        if (raw) {
          sessionStorage.removeItem('order_prefill');
          setPrefilledOrder(JSON.parse(raw));
          target = 'order-new';
        }
      } catch (_) {}
      setRoute(target);
    }).catch(() => {
      localStorage.removeItem('access_token');
    });
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    setUser(null);
    setBalance(0);
    setRoute('order-new');
  };

  const handleNavigate = (target, payload) => {
    // Auth-gated routes. 'order-new' / 'order-detail' are PUBLIC now
    // (guest can create unpaid orders and view payment status without a session).
    if (['cabinet', 'orders', 'profile', 'notifications'].includes(target) && !user) {
      setAuthMode('login');
      setRoute('auth');
      return;
    }
    if (['login', 'register', 'login-tg', 'forgot'].includes(target)) {
      setAuthMode(target);
      setRoute('auth');
      return;
    }
    if (target === 'order-new') {
      // Pick up prefill set just before navigation (e.g. "Войти" from OrderForm step 2,
      // or "Повторить заказ" from OrderDetail). Clear after read.
      try {
        const raw = sessionStorage.getItem('order_prefill');
        if (raw) {
          sessionStorage.removeItem('order_prefill');
          setPrefilledOrder(JSON.parse(raw));
        }
      } catch (_) {}
    }
    if (target === 'order-detail') {
      // Accept either a full order object (legacy callsites) or { order_id }.
      if (payload && (payload.order_id != null || payload.increment != null)) {
        setSelectedOrder(payload);
        setDetailOrderId(payload.order_id != null ? payload.order_id : payload.increment);
      } else if (typeof payload === 'number') {
        setSelectedOrder(null);
        setDetailOrderId(payload);
      } else {
        setSelectedOrder(payload || null);
        setDetailOrderId(null);
      }
    }
    setRoute(target);
  };

  const handleOrderPlaced = (price) => {
    setBalance(b => b - price);
  };

  if (appLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', color: 'var(--text-3)' }}>
      Загрузка...
    </div>
  );

  const headerProps = {
    route, user, balance,
    brandName: tweaks.brandName,
    theme: tweaks.theme,
    adminMode,
    onToggleAdminMode: toggleAdminMode,
    onToggleTheme: () => setTweak('theme', tweaks.theme === 'dark' ? 'light' : 'dark'),
    onNavigate: handleNavigate,
    onLogout: handleLogout,
  };

  const renderScreen = () => {
    if (adminMode && user && user.is_admin) {
      switch (route) {
        case 'admin':
        case 'admin-users':
        case 'admin-orders':
        case 'admin-support':
          return <AdminPanel route={route} onNavigate={handleNavigate} />;
        default:
          return <AdminPanel route="admin" onNavigate={handleNavigate} />;
      }
    }
    switch (route) {
      case 'auth':     return <AuthPage mode={authMode} onLogin={handleLogin} onNavigate={handleNavigate} botConfig={botConfig} resetToken={resetToken} />;
      case 'cabinet':  return <CabinetPage user={user} balance={balance} setBalance={setBalance} refreshBalance={refreshBalance} onNavigate={handleNavigate} />;
      case 'order-new':
        return <OrderFormPage
                 user={user} balance={balance}
                 prefilledFrom={prefilledOrder}
                 onNavigate={handleNavigate}
                 onOrderPlaced={handleOrderPlaced}
               />;
      case 'orders':   return <OrdersPage onNavigate={handleNavigate} />;
      case 'notifications': return <NotificationsPage onNavigate={handleNavigate} />;
      case 'order-detail': return <OrderDetailPage
                                    order={selectedOrder}
                                    orderId={detailOrderId}
                                    user={user}
                                    balance={balance}
                                    onNavigate={handleNavigate}
                                  />;
      case 'profile':  return <ProfilePage user={user} onNavigate={handleNavigate} botConfig={botConfig} />;
      default:         return <OrderFormPage
                                user={user} balance={balance}
                                prefilledFrom={prefilledOrder}
                                onNavigate={handleNavigate}
                                onOrderPlaced={handleOrderPlaced}
                              />;
    }
  };

  return (
    <div>
      {adminMode && user && user.is_admin
        ? <AdminHeader {...headerProps} />
        : <AppHeader {...headerProps} />
      }
      {renderScreen()}
      {user && !adminMode && <SupportChat />}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
