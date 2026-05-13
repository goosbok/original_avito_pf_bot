// app.jsx — root state, session restore, routing
const { useState, useEffect } = React;

const TWEAK_DEFAULTS = {
  theme: 'light',
  variant: 'classic',
  brandName: 'ProBoost',
  accentColor: '#0088cc'
};

function App() {
  const [tweaks, setTweaks] = useState(TWEAK_DEFAULTS);
  const [route, setRoute] = useState('landing');
  const [authMode, setAuthMode] = useState('login');
  const [user, setUser] = useState(null);
  const [balance, setBalance] = useState(0);
  const [appLoading, setAppLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [botConfig, setBotConfig] = useState(null);

  // Load public config (bot deep-link, etc.) once
  useEffect(() => {
    api.get('/api/config').then(data => {
      if (data && !data.__unauthorized) setBotConfig(data);
    }).catch(() => {});
  }, []);

  // Apply theme + variant to <html>
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', tweaks.theme);
    document.documentElement.setAttribute('data-variant', tweaks.variant);
    if (tweaks.accentColor) {
      document.documentElement.style.setProperty('--primary', tweaks.accentColor);
    }
  }, [tweaks]);

  // Restore session from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) { setAppLoading(false); return; }
    api.get('/api/me').then(data => {
      if (data.__unauthorized) {
        localStorage.removeItem('access_token');
      } else {
        setUser({ first_name: data.first_name, user_name: data.user_name, user_id: data.user_id });
        setBalance(data.balance);
        setRoute('cabinet');
      }
    }).catch(() => {
      localStorage.removeItem('access_token');
    }).finally(() => setAppLoading(false));
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
      setUser({ first_name: data.first_name, user_name: data.user_name, user_id: data.user_id });
      setBalance(data.balance);
      setRoute('cabinet');
    }).catch(() => {
      localStorage.removeItem('access_token');
    });
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    setUser(null);
    setBalance(0);
    setRoute('landing');
  };

  const handleNavigate = (target, payload) => {
    if (['cabinet', 'order-pf', 'orders', 'profile', 'order-detail'].includes(target) && !user) {
      setAuthMode('login');
      setRoute('auth');
      return;
    }
    if (['login', 'register', 'login-tg'].includes(target)) {
      setAuthMode(target);
      setRoute('auth');
      return;
    }
    if (target === 'order-detail') {
      setSelectedOrder(payload || null);
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
    onToggleTheme: () => setTweak('theme', tweaks.theme === 'dark' ? 'light' : 'dark'),
    onNavigate: handleNavigate,
    onLogout: handleLogout,
  };

  const renderScreen = () => {
    switch (route) {
      case 'landing':  return <LandingPage onNavigate={handleNavigate} brandName={tweaks.brandName} />;
      case 'auth':     return <AuthPage mode={authMode} onLogin={handleLogin} onNavigate={handleNavigate} botConfig={botConfig} />;
      case 'cabinet':  return <CabinetPage user={user} balance={balance} setBalance={setBalance} refreshBalance={refreshBalance} onNavigate={handleNavigate} />;
      case 'order-pf': return <OrderFormPage balance={balance} onNavigate={handleNavigate} onOrderPlaced={handleOrderPlaced} />;
      case 'orders':   return <OrdersPage onNavigate={handleNavigate} />;
      case 'order-detail': return <OrderDetailPage order={selectedOrder} onNavigate={handleNavigate} />;
      case 'profile':  return <ProfilePage user={user} onNavigate={handleNavigate} botConfig={botConfig} />;
      default:         return <LandingPage onNavigate={handleNavigate} brandName={tweaks.brandName} />;
    }
  };

  return (
    <div>
      <AppHeader {...headerProps} />
      {renderScreen()}
      {user && <SupportChat />}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
