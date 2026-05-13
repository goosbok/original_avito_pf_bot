// Profile page — show linked providers, allow linking email + TG
const { useState: useProfileState, useEffect: useProfileEffect } = React;

function ProfilePage({ user, onNavigate }) {
  const [providers, setProviders] = useProfileState([]);
  const [emailInput, setEmailInput] = useProfileState('');
  const [emailPass, setEmailPass] = useProfileState('');
  const [tgInput, setTgInput] = useProfileState('');
  const [tgCode, setTgCode] = useProfileState('');
  const [tgStep, setTgStep] = useProfileState('idle'); // idle | sent | done
  const [emailStatus, setEmailStatus] = useProfileState(''); // '' | 'loading' | 'success' | 'error'
  const [emailError, setEmailError] = useProfileState('');
  const [tgError, setTgError] = useProfileState('');

  useProfileEffect(() => {
    api.get('/api/me/providers').then(data => {
      if (!data.__unauthorized) setProviders(data);
    }).catch(() => {});
  }, []);

  const emailProvider = providers.find(p => p.provider === 'email');
  const tgProvider = providers.find(p => p.provider === 'telegram');

  const handleLinkEmail = async () => {
    if (!emailInput || !emailPass) return setEmailError('Заполните email и пароль');
    if (emailPass.length < 8) return setEmailError('Пароль — минимум 8 символов');
    setEmailStatus('loading'); setEmailError('');
    try {
      await api.post('/api/auth/link/email', { email: emailInput, password: emailPass, first_name: null });
      setEmailStatus('success');
      setProviders(prev => [...prev, { provider: 'email', identifier: emailInput, created_at: new Date().toISOString(), last_used_at: null }]);
    } catch (e) {
      setEmailStatus('error');
      if (e.status === 409) setEmailError('Email уже привязан к другому аккаунту');
      else setEmailError(e.message || 'Ошибка привязки');
    }
  };

  const isValidPhone = (raw) => {
    const cleaned = (raw || '').replace(/[^\d+]/g, '');
    if (/^\+\d{10,15}$/.test(cleaned)) return true;
    if (/^\d{10,11}$/.test(cleaned)) return true;
    return false;
  };

  const handleRequestTgCode = async () => {
    if (!tgInput) return;
    if (!isValidPhone(tgInput)) {
      setTgError('Введите номер телефона, например +79001234567');
      return;
    }
    setTgError('');
    try {
      await api.post('/api/auth/link/telegram/request-code', { identifier: tgInput });
      setTgStep('sent');
    } catch (e) {
      if (e.status === 429) {
        const sec = e.retry_after;
        setTgError(sec
          ? `Подождите ${sec} секунд перед повторной отправкой`
          : 'Подождите перед повторной отправкой');
      } else if (e.status === 400) {
        // Backend message already mentions /connect; bot deep-link rendered separately.
        setTgError(e.message || 'Не удалось найти ваш Telegram по этому номеру.');
      } else if (e.status === 502) {
        setTgError('Не удалось отправить код через Telegram. Попробуйте позже.');
      } else {
        setTgError(e.message || 'Ошибка отправки кода');
      }
    }
  };

  const handleVerifyTg = async () => {
    if (!tgCode || tgCode.length < 6) return;
    setTgError('');
    try {
      await api.post('/api/auth/link/telegram/verify-code', { identifier: tgInput, code: tgCode });
      setTgStep('done');
      setProviders(prev => [...prev, { provider: 'telegram', identifier: tgInput, created_at: new Date().toISOString(), last_used_at: null }]);
    } catch (e) {
      if (e.status === 410) setTgError('Код истёк — запросите новый');
      else if (e.status === 401) setTgError('Неверный код');
      else if (e.status === 409) setTgError('Telegram уже привязан к другому аккаунту');
      else setTgError(e.message || 'Ошибка проверки кода');
    }
  };

  const ProviderCard = ({ title, icon, linked, linkedLabel, children }) => (
    <div className="card" style={{ padding: '20px 24px', marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: linked ? 0 : 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 10, background: 'var(--primary-dim)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '0.7rem', fontWeight: 800, color: 'var(--primary)'
          }}>{icon}</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.9375rem' }}>{title}</div>
            {linked && <div style={{ fontSize: '0.8rem', color: 'var(--text-3)', marginTop: 2 }}>{linkedLabel}</div>}
          </div>
        </div>
        {linked
          ? <span className="badge badge--completed">✓ Привязан</span>
          : <span className="badge badge--muted">Не привязан</span>
        }
      </div>
      {!linked && <div style={{ marginTop: 16 }}>{children}</div>}
    </div>
  );

  return (
    <div className="page-wrap">
      <div style={{ padding: '28px 0 60px' }}>
        <div className="container" style={{ maxWidth: 600 }}>

          <button className="order-back" onClick={() => onNavigate('cabinet')}>← Назад в кабинет</button>

          <h2 style={{ marginBottom: 6 }}>Профиль</h2>
          <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', marginBottom: 28 }}>
            Управляйте способами входа в аккаунт
          </p>

          <div className="card" style={{ padding: '20px 24px', marginBottom: 24, display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{
              width: 52, height: 52, borderRadius: '50%', background: 'var(--primary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontSize: '1.25rem', fontWeight: 800, flexShrink: 0
            }}>
              {(user?.first_name || '?')[0].toUpperCase()}
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem' }}>{user?.first_name || 'Пользователь'}</div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-3)' }}>@{user?.user_name || 'username'}</div>
            </div>
          </div>

          <h3 style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
            Способы входа
          </h3>

          <ProviderCard
            title="Email и пароль" icon="Em"
            linked={!!emailProvider}
            linkedLabel={emailProvider?.identifier || ''}
          >
            {emailStatus === 'success' ? (
              <div className="alert alert--success">✅ Email успешно привязан</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {emailError && <div className="alert alert--error">{emailError}</div>}
                <div className="form-field">
                  <label className="form-label">Email</label>
                  <input className="input" type="email" placeholder="you@example.com" value={emailInput} onChange={e => setEmailInput(e.target.value)} />
                </div>
                <div className="form-field">
                  <label className="form-label">Пароль</label>
                  <input className="input" type="password" placeholder="Минимум 8 символов" value={emailPass} onChange={e => setEmailPass(e.target.value)} />
                  <div className="form-hint">Придумайте пароль для входа через email</div>
                </div>
                <button className="btn btn--primary" onClick={handleLinkEmail} disabled={emailStatus === 'loading'}>
                  {emailStatus === 'loading' ? 'Привязываем...' : 'Привязать email'}
                </button>
              </div>
            )}
          </ProviderCard>

          <ProviderCard
            title="Telegram" icon="TG"
            linked={!!tgProvider || tgStep === 'done'}
            linkedLabel={tgProvider?.identifier || tgInput || ''}
          >
            {tgStep === 'done' ? (
              <div className="alert alert--success">✅ Telegram успешно привязан</div>
            ) : tgStep === 'idle' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {tgError && (
                  <div className="alert alert--error">
                    {tgError}
                    <div style={{ marginTop: 8, fontSize: '0.875rem' }}>
                      <a href="https://t.me/AVITOPF_bot" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary)', fontWeight: 600 }}>
                        Открыть @AVITOPF_bot
                      </a>
                    </div>
                  </div>
                )}
                <div className="form-field">
                  <label className="form-label">Номер телефона</label>
                  <input
                    className="input"
                    type="tel"
                    inputMode="tel"
                    placeholder="+7 900 123-45-67"
                    value={tgInput}
                    onChange={e => setTgInput(e.target.value)}
                  />
                  <div className="form-hint">
                    Если бот ещё не знает ваш номер, отправьте <code>/connect</code> боту{' '}
                    <a href="https://t.me/AVITOPF_bot" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary)', fontWeight: 600 }}>@AVITOPF_bot</a>
                  </div>
                </div>
                <button className="btn btn--secondary" onClick={handleRequestTgCode} disabled={!tgInput}>
                  ✈ Получить код в Telegram
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {tgError && <div className="alert alert--error">{tgError}</div>}
                <div className="alert alert--info">Код отправлен в Telegram на {tgInput}</div>
                <div className="form-field">
                  <label className="form-label">6-значный код</label>
                  <input
                    className="input" placeholder="123456" value={tgCode} maxLength={6}
                    onChange={e => setTgCode(e.target.value.replace(/\D/g, ''))}
                    style={{ textAlign: 'center', fontSize: '1.25rem', letterSpacing: '0.15em', fontWeight: 700 }}
                    autoFocus
                  />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn--ghost btn--sm" onClick={() => setTgStep('idle')}>← Назад</button>
                  <button className="btn btn--primary" style={{ flex: 1 }} onClick={handleVerifyTg} disabled={tgCode.length < 6}>
                    Подтвердить
                  </button>
                </div>
              </div>
            )}
          </ProviderCard>

        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ProfilePage });
