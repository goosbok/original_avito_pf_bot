// Auth screens: Email login, Telegram OTP login, Email register
const { useState } = React;

const AuthPage = ({ mode: initialMode, onLogin, onNavigate }) => {
  const [mode, setMode] = useState(initialMode || 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [tgId, setTgId] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleEmailLogin = async () => {
    if (!email || !password) return setError('Заполните все поля');
    setLoading(true); setError('');
    try {
      const data = await api.post('/api/auth/email/login', { email, password });
      onLogin(data.access_token);
    } catch (e) {
      setError(e.status === 401 ? 'Неверный email или пароль' : (e.message || 'Ошибка входа'));
    } finally { setLoading(false); }
  };

  const handleRegister = async () => {
    if (!email || !password) return setError('Заполните все поля');
    if (password.length < 8) return setError('Пароль — минимум 8 символов');
    setLoading(true); setError('');
    try {
      const data = await api.post('/api/auth/email/register', {
        email, password, first_name: name || null
      });
      onLogin(data.access_token);
    } catch (e) {
      if (e.status === 409) setError('Email уже зарегистрирован');
      else setError(e.message || 'Ошибка регистрации');
    } finally { setLoading(false); }
  };

  const handleRequestOtp = async () => {
    if (!tgId) return setError('Введите username или телефон');
    setLoading(true); setError(''); setSuccess('');
    try {
      await api.post('/api/auth/telegram/request-code', { identifier: tgId });
      setOtpSent(true);
      setSuccess('Код отправлен в Telegram');
    } catch (e) {
      if (e.status === 429) setError('Подождите перед повторной отправкой');
      else if (e.status === 400) setError(e.message || 'Пользователь не найден в Telegram');
      else setError(e.message || 'Ошибка отправки кода');
    } finally { setLoading(false); }
  };

  const handleVerifyOtp = async () => {
    if (!otpCode || otpCode.length < 6) return setError('Введите 6-значный код');
    setLoading(true); setError('');
    try {
      const data = await api.post('/api/auth/telegram/verify-code', {
        identifier: tgId, code: otpCode
      });
      onLogin(data.access_token);
    } catch (e) {
      if (e.status === 410) setError('Код истёк — запросите новый');
      else if (e.status === 401) setError('Неверный код');
      else setError(e.message || 'Ошибка проверки кода');
    } finally { setLoading(false); }
  };

  const logoMark = (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <div style={{
        width: 48, height: 48, borderRadius: 14, background: 'var(--primary)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '1rem', fontWeight: 900, color: '#fff'
      }}>PB</div>
    </div>
  );

  if (mode === 'login-tg') return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Вход через Telegram</h2>
        <p className="auth-card__sub">Введите username или номер телефона — мы отправим код</p>
        <div className="auth-form">
          {error && <div className="alert alert--error">{error}</div>}
          {success && <div className="alert alert--success">{success}</div>}
          {!otpSent ? (
            <>
              <div className="form-field">
                <label className="form-label">Username или телефон</label>
                <input
                  className="input"
                  placeholder="@username или +79001234567"
                  value={tgId}
                  onChange={e => setTgId(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleRequestOtp()}
                />
              </div>
              <button className="btn btn--primary btn--lg btn--full" onClick={handleRequestOtp} disabled={loading}>
                {loading ? 'Отправка...' : 'Получить код в Telegram'}
              </button>
            </>
          ) : (
            <>
              <div className="form-field">
                <label className="form-label">6-значный код из Telegram</label>
                <input
                  className="input"
                  placeholder="123456"
                  value={otpCode}
                  maxLength={6}
                  onChange={e => setOtpCode(e.target.value.replace(/\D/g, ''))}
                  onKeyDown={e => e.key === 'Enter' && handleVerifyOtp()}
                  style={{ textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.2em', fontWeight: 700 }}
                  autoFocus
                />
                <div className="form-hint">Код действителен 10 минут</div>
              </div>
              <button className="btn btn--primary btn--lg btn--full" onClick={handleVerifyOtp} disabled={loading}>
                {loading ? 'Проверка...' : 'Войти →'}
              </button>
              <button className="btn btn--ghost btn--sm btn--full" onClick={() => { setOtpSent(false); setOtpCode(''); setSuccess(''); }}>
                ← Изменить username
              </button>
            </>
          )}
        </div>
        <div className="auth-links">
          <span onClick={() => setMode('login')} style={{ cursor: 'pointer', color: 'var(--primary)', fontWeight: 600 }}>
            Войти через Email
          </span>
          {' · '}
          <span onClick={() => onNavigate('landing')} style={{ cursor: 'pointer' }}>На главную</span>
        </div>
      </div>
    </div>
  );

  if (mode === 'register') return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Создать аккаунт</h2>
        <p className="auth-card__sub">Email + пароль. Позже можно привязать Telegram.</p>
        <div className="auth-form">
          {error && <div className="alert alert--error">{error}</div>}
          <div className="form-field">
            <label className="form-label">Имя (необязательно)</label>
            <input className="input" placeholder="Алексей" value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-label">Email</label>
            <input className="input" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-label">Пароль</label>
            <input
              className="input" type="password" placeholder="Минимум 8 символов"
              value={password} onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleRegister()}
            />
            <div className="form-hint">Минимум 8 символов</div>
          </div>
          <button className="btn btn--primary btn--lg btn--full" onClick={handleRegister} disabled={loading}>
            {loading ? 'Создание аккаунта...' : 'Создать аккаунт →'}
          </button>
          <div className="auth-divider"><span>или</span></div>
          <button className="btn btn--ghost btn--full" onClick={() => setMode('login-tg')}>
            Войти через Telegram
          </button>
        </div>
        <div className="auth-links">
          Уже есть аккаунт?{' '}
          <span onClick={() => setMode('login')} style={{ color: 'var(--primary)', fontWeight: 600, cursor: 'pointer' }}>Войти</span>
        </div>
      </div>
    </div>
  );

  // Default: Email login
  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Добро пожаловать</h2>
        <p className="auth-card__sub">Войдите в личный кабинет</p>
        <div className="auth-form">
          {error && <div className="alert alert--error">{error}</div>}
          <button className="btn btn--secondary btn--lg btn--full" onClick={() => setMode('login-tg')}>
            Войти через Telegram
          </button>
          <div className="auth-divider"><span>или через email</span></div>
          <div className="form-field">
            <label className="form-label">Email</label>
            <input className="input" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-label">Пароль</label>
            <input
              className="input" type="password" placeholder="Ваш пароль"
              value={password} onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleEmailLogin()}
            />
          </div>
          <button className="btn btn--primary btn--lg btn--full" onClick={handleEmailLogin} disabled={loading}>
            {loading ? 'Вход...' : 'Войти →'}
          </button>
        </div>
        <div className="auth-links">
          Нет аккаунта?{' '}
          <span onClick={() => setMode('register')} style={{ color: 'var(--primary)', fontWeight: 600, cursor: 'pointer' }}>Зарегистрироваться</span>
          {' · '}
          <span onClick={() => onNavigate('landing')} style={{ cursor: 'pointer' }}>На главную</span>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { AuthPage });
