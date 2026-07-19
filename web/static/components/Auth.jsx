// Auth screens: Email login, Telegram OTP login, Email register
const { useState, useEffect } = React;

// TG-регистрация: вкл с 2026-06-19. Backend endpoints (/api/auth/telegram/*)
// и интеграция с ботом готовы; разделяем register/login через единый флаг.
// Чтобы снова спрятать TG-регистрацию — flip в false.
const TG_AUTH_ENABLED = true;

const AuthPage = ({ mode: initialMode, onLogin, onNavigate, botConfig }) => {
  const [mode, setMode] = useState(initialMode || 'login');

  // Keep internal mode in sync when parent navigates between auth sub-modes
  // (login → register, register → login with TG open, etc.). Without this, useState's
  // lazy init means clicks on header "Войти" / "Регистрация" do nothing when
  // we're already on the auth route.
  useEffect(() => { setMode(initialMode || 'login'); }, [initialMode]);

  // Reset transient sub-flow state whenever mode changes (incl. from header nav).
  useEffect(() => {
    setError(''); setSuccess('');
    setRegStep('form'); setRegCode('');
    setOtpSent(false); setOtpCode('');
    setNeedsConnect(false);
    setForgotEmail(''); setForgotStep('email'); setForgotCode('');
    setResetNew(''); setResetConfirm(''); setResetDone(false);
    setActiveMethod(null);
  }, [mode]);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [tgId, setTgId] = useState(() => sessionStorage.getItem('auth_tg_phone') || '');
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  // Registration: 'form' (name/email/password) → 'code' (email verification)
  const [regStep, setRegStep] = useState('form');
  const [regCode, setRegCode] = useState('');
  const [needsConnect, setNeedsConnect] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotStep, setForgotStep] = useState('email'); // 'email' | 'code'
  const [forgotCode, setForgotCode] = useState('');
  const [resetNew, setResetNew] = useState('');
  const [resetConfirm, setResetConfirm] = useState('');
  const [resetDone, setResetDone] = useState(false);
  const [activeMethod, setActiveMethod] = useState(null); // null | 'tg' | 'email' | 'sms'

  function pickMethod(method) {
    setError('');
    setSuccess('');
    if (activeMethod === method) {
      // tap on the same method → collapse
      setActiveMethod(null);
      if (method === 'tg') { setOtpSent(false); setOtpCode(''); setNeedsConnect(false); }
      return;
    }
    // switching methods — reset state of the previously-active TG step machine
    if (activeMethod === 'tg') { setOtpSent(false); setOtpCode(''); setNeedsConnect(false); }
    setActiveMethod(method);
  }

  useEffect(() => {
    if (tgId) sessionStorage.setItem('auth_tg_phone', tgId);
    else sessionStorage.removeItem('auth_tg_phone');
  }, [tgId]);

  // Validate phone: strip non-digits/plus; accept +XXXXXXXXXX..XXXXX or 10–11 plain digits.
  const isValidPhone = (raw) => {
    const cleaned = (raw || '').replace(/[^\d+]/g, '');
    if (/^\+\d{10,15}$/.test(cleaned)) return true;
    if (/^\d{10,11}$/.test(cleaned)) return true;
    return false;
  };

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

  const handleRegisterRequest = async () => {
    if (!email || !password) return setError('Заполните все поля');
    if (password.length < 8) return setError('Пароль — минимум 8 символов');
    setLoading(true); setError(''); setSuccess('');
    try {
      await api.post('/api/auth/email/register-request', {
        email, password, first_name: name || null
      });
      setRegStep('code');
      setRegCode('');
      setSuccess('Код отправлен на ' + email);
    } catch (e) {
      if (e.status === 409) setError('Email уже зарегистрирован');
      else if (e.status === 429) {
        const sec = e.retry_after;
        setError(sec
          ? `Код уже отправлен. Попробуйте через ${sec} секунд.`
          : 'Код уже отправлен. Попробуйте позже.');
      } else if (e.status === 502) {
        setError('Не удалось отправить код на email. Попробуйте позже или используйте другой email.');
      } else if (e.status === 400) {
        setError(e.message || 'Неверные данные');
      } else {
        setError(e.message || 'Ошибка регистрации');
      }
    } finally { setLoading(false); }
  };

  const handleRegisterVerify = async () => {
    if (!regCode || regCode.length < 6) return setError('Введите 6-значный код');
    setLoading(true); setError('');
    try {
      const data = await api.post('/api/auth/email/register-verify', {
        email, code: regCode,
        ref_code: window.getRefCode ? window.getRefCode() : null,
      });
      onLogin(data.access_token);
    } catch (e) {
      if (e.status === 401) setError('Неверный код');
      else if (e.status === 410) setError('Код истёк. Запросите новый.');
      else setError(e.message || 'Ошибка проверки кода');
    } finally { setLoading(false); }
  };

  const handleResendRegisterCode = async () => {
    setLoading(true); setError(''); setSuccess('');
    try {
      await api.post('/api/auth/email/register-request', {
        email, password, first_name: name || null
      });
      setSuccess('Код отправлен на ' + email);
    } catch (e) {
      if (e.status === 429) {
        const sec = e.retry_after;
        setError(sec
          ? `Код уже отправлен. Попробуйте через ${sec} секунд.`
          : 'Код уже отправлен. Попробуйте позже.');
      } else if (e.status === 502) {
        setError('Не удалось отправить код на email. Попробуйте позже.');
      } else {
        setError(e.message || 'Ошибка отправки кода');
      }
    } finally { setLoading(false); }
  };

  const handleRequestOtp = async () => {
    if (!tgId) return setError('Введите номер телефона');
    if (!isValidPhone(tgId)) return setError('Введите номер телефона, например +79001234567');
    setLoading(true); setError(''); setSuccess(''); setNeedsConnect(false);
    try {
      await api.post('/api/auth/telegram/request-code', { identifier: tgId });
      setOtpSent(true);
      setSuccess('Код отправлен в Telegram');
    } catch (e) {
      // 429 = cooldown; 400 = unknown phone or bot can't reach user; 502 = bot network error.
      if (e.status === 429) {
        const sec = e.retry_after;
        setError(sec
          ? `Слишком частые запросы. Попробуйте через ${sec} секунд.`
          : 'Слишком частые запросы. Попробуйте через минуту.');
      } else if (e.status === 400) {
        setNeedsConnect(true);
      } else if (e.status === 502) {
        setError('Не удалось отправить код через Telegram. Попробуйте позже.');
      } else {
        setError(e.message || 'Ошибка отправки кода. Попробуйте позже.');
      }
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

  const handleForgotPassword = async () => {
    if (!forgotEmail) return setError('Введите email');
    setLoading(true); setError('');
    try {
      await api.post('/api/auth/email/forgot-password', { email: forgotEmail });
      setForgotStep('code');
    } catch (e) {
      if (e.status === 429) {
        setError('Код уже отправлен, подождите немного перед повторной отправкой');
      } else {
        setError(e.message || 'Ошибка');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    if (!forgotCode || forgotCode.length !== 6) return setError('Введите 6-значный код');
    if (!resetNew || resetNew.length < 8) return setError('Пароль — минимум 8 символов');
    if (resetNew !== resetConfirm) return setError('Пароли не совпадают');
    setLoading(true); setError('');
    try {
      await api.post('/api/auth/email/reset-password', {
        email: forgotEmail,
        code: forgotCode,
        new_password: resetNew,
        new_password_confirm: resetConfirm,
      });
      setResetDone(true);
    } catch (e) {
      if (e.status === 410) {
        setError('Код истёк — запросите новый');
        setForgotStep('email');
        setForgotCode('');
      } else if (e.status === 401) {
        setError('Неверный код');
      } else {
        setError(e.message || 'Ошибка');
      }
    } finally {
      setLoading(false);
    }
  };

  const logoMark = (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <img src="/logo.png" alt="авито.пф" width="48" height="48"
        style={{ width: 48, height: 48, borderRadius: '50%', objectFit: 'cover', background: '#000' }} />
    </div>
  );

  if (mode === 'register') return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Регистрация</h2>
        <p className="auth-card__sub">Выберите способ</p>

        <div className={`method-row${activeMethod ? ' has-active' : ''}`}>
          {TG_AUTH_ENABLED && (
            <>
              {/* ── Telegram ─────────────────────────────────────────────── */}
              <button
                type="button"
                className={`method-btn${activeMethod === 'tg' ? ' active' : ''}`}
                onClick={() => pickMethod('tg')}
              >
                Через Telegram
              </button>
              {activeMethod === 'tg' && (
                <div className="method-form">
                  {needsConnect && (() => {
                    const botUrl = (botConfig && botConfig.bot_connect_url) || 'https://t.me/AVITOPF_bot?start=connect';
                    const botName = (botConfig && botConfig.bot_username) || 'AVITOPF_bot';
                    return (
                      <div className="alert alert--info">
                        <div style={{ fontWeight: 600, marginBottom: 8 }}>Номер не привязан к боту</div>
                        <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
                          <li><a href={botUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', fontWeight: 600, textDecoration: 'underline' }}>Откройте @{botName} в Telegram</a></li>
                          <li>Нажмите «Поделиться контактом»</li>
                          <li>Вернитесь сюда и нажмите «Получить код»</li>
                        </ol>
                      </div>
                    );
                  })()}
                  {!otpSent ? (
                    <>
                      <div className="form-field">
                        <label className="form-label">Номер телефона</label>
                        <input
                          className="input"
                          type="tel"
                          inputMode="tel"
                          placeholder="+7 900 123-45-67"
                          value={tgId}
                          onChange={e => setTgId(e.target.value)}
                          onKeyDown={e => e.key === 'Enter' && handleRequestOtp()}
                        />
                      </div>
                      <button className="btn btn--primary btn--lg btn--full" onClick={handleRequestOtp} disabled={loading}>
                        {loading ? 'Отправка...' : 'Получить код'}
                      </button>
                    </>
                  ) : (
                    <>
                      {success && <div className="alert alert--success">{success}</div>}
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
                        {loading ? 'Проверка...' : 'Создать аккаунт'}
                      </button>
                      <button className="btn btn--ghost btn--sm btn--full" onClick={() => { setOtpSent(false); setOtpCode(''); setSuccess(''); }}>
                        ← Изменить номер
                      </button>
                    </>
                  )}
                </div>
              )}
            </>
          )}

          {/* ── Email ────────────────────────────────────────────────────── */}
          <button
            type="button"
            className={`method-btn${activeMethod === 'email' ? ' active' : ''}`}
            onClick={() => pickMethod('email')}
          >
            По Email
          </button>
          {activeMethod === 'email' && (
            <div className="method-form">
              {error && <div className="alert alert--error">{error}</div>}
              {success && regStep === 'code' && <div className="alert alert--success">{success}</div>}
              {regStep === 'form' ? (
                <>
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
                      onKeyDown={e => e.key === 'Enter' && handleRegisterRequest()}
                    />
                    <div className="form-hint">Минимум 8 символов</div>
                  </div>
                  <button className="btn btn--primary btn--lg btn--full" onClick={handleRegisterRequest} disabled={loading}>
                    {loading ? 'Отправка кода...' : 'Получить код'}
                  </button>
                </>
              ) : (
                <>
                  <div className="form-field">
                    <label className="form-label">6-значный код из email</label>
                    <input
                      className="input"
                      placeholder="123456"
                      value={regCode}
                      maxLength={6}
                      inputMode="numeric"
                      onChange={e => setRegCode(e.target.value.replace(/\D/g, ''))}
                      onKeyDown={e => e.key === 'Enter' && handleRegisterVerify()}
                      style={{ textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.2em', fontWeight: 700 }}
                      autoFocus
                    />
                    <div className="form-hint">Код отправлен на {email}. Действителен 10 минут.</div>
                  </div>
                  <button className="btn btn--primary btn--lg btn--full" onClick={handleRegisterVerify} disabled={loading}>
                    {loading ? 'Проверка...' : 'Создать аккаунт'}
                  </button>
                  <div style={{ textAlign: 'center', fontSize: '0.875rem' }}>
                    <span style={{ color: 'var(--text-3)' }}>Не пришёл код?</span>{' '}
                    <span
                      onClick={() => { if (!loading) handleResendRegisterCode(); }}
                      style={{ color: 'var(--primary)', fontWeight: 600, cursor: loading ? 'default' : 'pointer' }}
                    >
                      Отправить заново
                    </span>
                  </div>
                  <button
                    className="btn btn--ghost btn--sm btn--full"
                    onClick={() => { setRegStep('form'); setRegCode(''); setError(''); setSuccess(''); }}
                  >
                    ← Назад
                  </button>
                </>
              )}
            </div>
          )}

          {/* ── SMS ── временно отключено (2026-06-07): нужен provider integration ──
              <button type="button" className={`method-btn${activeMethod === 'sms' ? ' active' : ''}`} onClick={() => pickMethod('sms')}>По SMS</button>
              {activeMethod === 'sms' && (<div className="method-form"><PhoneLogin onSuccess={(jwt) => onLogin(jwt)} /></div>)}
          */}
        </div>

        <div className="auth-links">
          Уже есть аккаунт?{' '}
          <span
            onClick={() => { setRegStep('form'); setRegCode(''); setError(''); setSuccess(''); setMode('login'); }}
            style={{ color: 'var(--primary)', fontWeight: 600, cursor: 'pointer' }}
          >Войти</span>
        </div>
      </div>
    </div>
  );

  if (mode === 'forgot') return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <h2 style={{ marginBottom: 6 }}>Восстановление пароля</h2>
        {resetDone ? (
          <>
            <div className="alert alert--success" style={{ marginBottom: 16 }}>
              Пароль изменён — войдите с новым паролем
            </div>
            <button className="btn btn--primary" onClick={() => onNavigate('login')}>
              Войти
            </button>
          </>
        ) : forgotStep === 'email' ? (
          <>
            {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}
            <div className="form-field" style={{ marginBottom: 12 }}>
              <label className="form-label">Email</label>
              <input className="input" type="email" placeholder="you@example.com"
                value={forgotEmail} onChange={e => setForgotEmail(e.target.value)} />
            </div>
            <button className="btn btn--primary" onClick={handleForgotPassword} disabled={loading}>
              {loading ? 'Отправляем...' : 'Отправить код'}
            </button>
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <button className="btn btn--ghost btn--sm" onClick={() => onNavigate('login')}
                style={{ fontSize: '0.85rem', color: 'var(--text-2)' }}>
                ← Назад ко входу
              </button>
            </div>
          </>
        ) : (
          <>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-2)', marginBottom: 12 }}>
              Код отправлен на {forgotEmail}
            </p>
            {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}
            <div className="form-field" style={{ marginBottom: 12 }}>
              <label className="form-label">Код из письма</label>
              <input className="input" type="text" inputMode="numeric" maxLength={6}
                placeholder="000000" value={forgotCode}
                onChange={e => setForgotCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
            </div>
            <div className="form-field" style={{ marginBottom: 12 }}>
              <label className="form-label">Новый пароль</label>
              <input className="input" type="password" placeholder="Минимум 8 символов"
                value={resetNew} onChange={e => setResetNew(e.target.value)} />
            </div>
            <div className="form-field" style={{ marginBottom: 16 }}>
              <label className="form-label">Повторите пароль</label>
              <input className="input" type="password" placeholder="Повторите пароль"
                value={resetConfirm} onChange={e => setResetConfirm(e.target.value)} />
            </div>
            <button className="btn btn--primary" onClick={handleResetPassword} disabled={loading}>
              {loading ? 'Сохраняем...' : 'Сбросить пароль'}
            </button>
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <button className="btn btn--ghost btn--sm"
                onClick={() => { setForgotStep('email'); setForgotCode(''); setError(''); }}
                style={{ fontSize: '0.85rem', color: 'var(--text-2)' }}>
                ← Ввести другой email
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );

  // Default: accordion method picker (Telegram / Email / SMS)
  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Войти</h2>
        <p className="auth-card__sub">Выберите способ</p>

        {error && <div className="alert alert--error">{error}</div>}

        <div className={`method-row${activeMethod ? ' has-active' : ''}`}>
          {/* ── Telegram ─────────────────────────────────────────────────── */}
          {/* NB: kept on the LOGIN screen even though registration via TG is
              disabled — 14k+ existing users have TG-only accounts and must
              still be able to log in. Registration's TG block is gated by
              TG_AUTH_ENABLED above. */}
          <button
            type="button"
            className={`method-btn${activeMethod === 'tg' ? ' active' : ''}`}
            onClick={() => pickMethod('tg')}
          >
            Через Telegram
          </button>
          {activeMethod === 'tg' && (
            <div className="method-form">
              {needsConnect && (() => {
                const botUrl = (botConfig && botConfig.bot_connect_url) || 'https://t.me/AVITOPF_bot?start=connect';
                const botName = (botConfig && botConfig.bot_username) || 'AVITOPF_bot';
                return (
                  <div className="alert alert--info">
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>Номер не привязан к боту</div>
                    <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
                      <li><a href={botUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', fontWeight: 600, textDecoration: 'underline' }}>Откройте @{botName} в Telegram</a></li>
                      <li>Нажмите «Поделиться контактом»</li>
                      <li>Вернитесь сюда и нажмите «Получить код»</li>
                    </ol>
                  </div>
                );
              })()}
              {!otpSent ? (
                <>
                  <div className="form-field">
                    <label className="form-label">Номер телефона</label>
                    <input
                      className="input"
                      type="tel"
                      inputMode="tel"
                      placeholder="+7 900 123-45-67"
                      value={tgId}
                      onChange={e => setTgId(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleRequestOtp()}
                    />
                  </div>
                  <button className="btn btn--primary btn--lg btn--full" onClick={handleRequestOtp} disabled={loading}>
                    {loading ? 'Отправка...' : 'Получить код'}
                  </button>
                </>
              ) : (
                <>
                  {success && <div className="alert alert--success">{success}</div>}
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
                    {loading ? 'Проверка...' : 'Войти'}
                  </button>
                  <button className="btn btn--ghost btn--sm btn--full" onClick={() => { setOtpSent(false); setOtpCode(''); setSuccess(''); }}>
                    ← Изменить номер
                  </button>
                </>
              )}
            </div>
          )}

          {/* ── Email ────────────────────────────────────────────────────── */}
          <button
            type="button"
            className={`method-btn${activeMethod === 'email' ? ' active' : ''}`}
            onClick={() => pickMethod('email')}
          >
            По Email
          </button>
          {activeMethod === 'email' && (
            <div className="method-form">
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
                {loading ? 'Вход...' : 'Войти'}
              </button>
              <div style={{ textAlign: 'center', marginTop: 8, fontSize: '0.85rem' }}>
                <span onClick={() => onNavigate('forgot')} style={{ color: 'var(--primary)', cursor: 'pointer' }}>
                  Забыл пароль?
                </span>
              </div>
            </div>
          )}

          {/* ── SMS ── временно отключено (2026-06-07): нужен provider integration ──
              <button type="button" className={`method-btn${activeMethod === 'sms' ? ' active' : ''}`} onClick={() => pickMethod('sms')}>По SMS</button>
              {activeMethod === 'sms' && (<div className="method-form"><PhoneLogin onSuccess={(jwt) => onLogin(jwt)} /></div>)}
          */}
        </div>

        <div className="auth-links">
          Нет аккаунта?{' '}
          <span
            onClick={() => { setRegStep('form'); setRegCode(''); setError(''); setSuccess(''); setMode('register'); }}
            style={{ color: 'var(--primary)', fontWeight: 600, cursor: 'pointer' }}
          >Зарегистрироваться</span>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { AuthPage });
