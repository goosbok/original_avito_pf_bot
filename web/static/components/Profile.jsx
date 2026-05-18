// Profile page — show linked providers, allow linking email + TG
const { useState: useProfileState, useEffect: useProfileEffect } = React;

// IMPORTANT: defined at module scope (not inside ProfilePage). Defining it
// inside the parent created a NEW component type on every parent render,
// which made React unmount/remount the inputs underneath — focus dropped
// after each keystroke (https://react.dev/learn/preserving-and-resetting-state).
function ProviderCard({ title, icon, linked, linkedLabel, children, linkedChildren }) {
  return (
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
      {linked && linkedChildren && <div style={{ marginTop: 16 }}>{linkedChildren}</div>}
    </div>
  );
}

function ProfilePage({ user, onNavigate, botConfig }) {
  const [providers, setProviders] = useProfileState([]);
  const [emailInput, setEmailInput] = useProfileState('');
  const [emailPass, setEmailPass] = useProfileState('');
  const [emailConfirm, setEmailConfirm] = useProfileState('');
  const [emailCode, setEmailCode] = useProfileState('');
  const [emailStep, setEmailStep] = useProfileState('idle'); // idle | sent | done
  const [emailLoading, setEmailLoading] = useProfileState(false);
  const [emailError, setEmailError] = useProfileState('');
  const [changePwOpen, setChangePwOpen] = useProfileState(false);
  const [changePwCurrent, setChangePwCurrent] = useProfileState('');
  const [changePwNew, setChangePwNew] = useProfileState('');
  const [changePwConfirm, setChangePwConfirm] = useProfileState('');
  const [changePwLoading, setChangePwLoading] = useProfileState(false);
  const [changePwError, setChangePwError] = useProfileState('');
  const [changePwSuccess, setChangePwSuccess] = useProfileState(false);
  const [tgInput, setTgInput] = useProfileState('');
  const [tgCode, setTgCode] = useProfileState('');
  const [tgStep, setTgStep] = useProfileState('idle'); // idle | sent | done
  const [tgError, setTgError] = useProfileState('');

  useProfileEffect(() => {
    api.get('/api/me/providers').then(data => {
      if (!data.__unauthorized) setProviders(data);
    }).catch(() => {});
  }, []);

  const emailProvider = providers.find(p => p.provider === 'email');
  const tgProvider = providers.find(p => p.provider === 'telegram');

  const handleLinkEmailRequest = async () => {
    if (!emailInput || !emailPass) return setEmailError('Заполните email и пароль');
    if (emailPass.length < 8) return setEmailError('Пароль — минимум 8 символов');
    if (emailPass !== emailConfirm) return setEmailError('Пароли не совпадают');
    setEmailLoading(true); setEmailError('');
    try {
      await api.post('/api/auth/link/email/request', { email: emailInput, password: emailPass, password_confirm: emailConfirm });
      setEmailStep('sent');
    } catch (e) {
      if (e.status === 409) setEmailError('Email уже привязан к другому аккаунту');
      else if (e.status === 429) setEmailError('Подождите перед повторной отправкой');
      else setEmailError(e.message || 'Ошибка отправки кода');
    } finally {
      setEmailLoading(false);
    }
  };

  const handleLinkEmailVerify = async () => {
    if (!emailCode || emailCode.length < 6) return;
    setEmailLoading(true); setEmailError('');
    try {
      await api.post('/api/auth/link/email/verify', { email: emailInput, code: emailCode });
      setEmailStep('done');
      setProviders(prev => [...prev, { provider: 'email', identifier: emailInput, created_at: new Date().toISOString(), last_used_at: null }]);
    } catch (e) {
      if (e.status === 410) setEmailError('Код истёк — запросите новый');
      else if (e.status === 401) setEmailError('Неверный код');
      else if (e.status === 409) setEmailError('Email уже привязан к другому аккаунту');
      else setEmailError(e.message || 'Ошибка проверки кода');
    } finally {
      setEmailLoading(false);
    }
  };

  const handleChangePassword = async () => {
    if (!changePwCurrent || !changePwNew) return setChangePwError('Заполните все поля');
    if (changePwNew.length < 8) return setChangePwError('Новый пароль — минимум 8 символов');
    if (changePwNew !== changePwConfirm) return setChangePwError('Пароли не совпадают');
    setChangePwLoading(true); setChangePwError('');
    try {
      await api.post('/api/auth/change-password', {
        current_password: changePwCurrent,
        new_password: changePwNew,
        new_password_confirm: changePwConfirm,
      });
      setChangePwSuccess(true);
      setChangePwOpen(false);
      setChangePwCurrent(''); setChangePwNew(''); setChangePwConfirm('');
    } catch (e) {
      if (e.status === 401) setChangePwError('Неверный текущий пароль');
      else setChangePwError(e.message || 'Ошибка смены пароля');
    } finally {
      setChangePwLoading(false);
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
      else if (e.status === 409) setTgError(
        'Этот Telegram уже привязан к другому аккаунту. ' +
        'Войдите в тот аккаунт по номеру и отвяжите Telegram там, ' +
        'либо напишите в поддержку — поможем разобраться.'
      );
      else setTgError(e.message || 'Ошибка проверки кода');
    }
  };


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
            linkedChildren={emailProvider && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {changePwSuccess && !changePwOpen && (
                  <div className="alert alert--success">Пароль изменён</div>
                )}
                {!changePwOpen ? (
                  <button className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start' }}
                    onClick={() => { setChangePwOpen(true); setChangePwSuccess(false); setChangePwError(''); }}>
                    Сменить пароль
                  </button>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {changePwError && <div className="alert alert--error">{changePwError}</div>}
                    <div className="form-field">
                      <label className="form-label">Текущий пароль</label>
                      <input className="input" type="password" placeholder="Текущий пароль"
                        value={changePwCurrent} onChange={e => setChangePwCurrent(e.target.value)} />
                    </div>
                    <div className="form-field">
                      <label className="form-label">Новый пароль</label>
                      <input className="input" type="password" placeholder="Минимум 8 символов"
                        value={changePwNew} onChange={e => setChangePwNew(e.target.value)} />
                    </div>
                    <div className="form-field">
                      <label className="form-label">Повторите новый пароль</label>
                      <input className="input" type="password" placeholder="Повторите пароль"
                        value={changePwConfirm} onChange={e => setChangePwConfirm(e.target.value)} />
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn--ghost btn--sm"
                        onClick={() => { setChangePwOpen(false); setChangePwError(''); }}>
                        Отмена
                      </button>
                      <button className="btn btn--primary" style={{ flex: 1 }}
                        onClick={handleChangePassword} disabled={changePwLoading}>
                        {changePwLoading ? 'Сохраняем...' : 'Сохранить'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          >
            {emailStep === 'done' ? (
              <div className="alert alert--success">✅ Email успешно привязан</div>
            ) : emailStep === 'idle' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {emailError && <div className="alert alert--error">{emailError}</div>}
                <div className="form-field">
                  <label className="form-label">Email</label>
                  <input className="input" type="email" placeholder="you@example.com" value={emailInput} onChange={e => setEmailInput(e.target.value)} />
                </div>
                <div className="form-field">
                  <label className="form-label">Пароль</label>
                  <input className="input" type="password" placeholder="Минимум 8 символов" value={emailPass} onChange={e => setEmailPass(e.target.value)} />
                </div>
                <div className="form-field">
                  <label className="form-label">Повторите пароль</label>
                  <input className="input" type="password" placeholder="Повторите пароль" value={emailConfirm} onChange={e => setEmailConfirm(e.target.value)} />
                  <div className="form-hint">Придумайте пароль для входа через email</div>
                </div>
                <button className="btn btn--primary" onClick={handleLinkEmailRequest} disabled={emailLoading}>
                  {emailLoading ? 'Отправляем код...' : 'Привязать email'}
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {emailError && <div className="alert alert--error">{emailError}</div>}
                <div className="alert alert--info">Код подтверждения отправлен на {emailInput}</div>
                <div className="form-field">
                  <label className="form-label">6-значный код</label>
                  <input
                    className="input" placeholder="123456" value={emailCode} maxLength={6}
                    onChange={e => setEmailCode(e.target.value.replace(/\D/g, ''))}
                    style={{ textAlign: 'center', fontSize: '1.25rem', letterSpacing: '0.15em', fontWeight: 700 }}
                    autoFocus
                  />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn--ghost btn--sm" onClick={() => { setEmailStep('idle'); setEmailError(''); }}>← Назад</button>
                  <button className="btn btn--primary" style={{ flex: 1 }} onClick={handleLinkEmailVerify} disabled={emailCode.length < 6 || emailLoading}>
                    {emailLoading ? 'Проверяем...' : 'Подтвердить'}
                  </button>
                </div>
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
                      <a href={(botConfig && botConfig.bot_connect_url) || 'https://t.me/AVITOPF_bot?start=connect'} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary)', fontWeight: 600 }}>
                        Открыть @{(botConfig && botConfig.bot_username) || 'AVITOPF_bot'} и отправить /connect
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
                    Если бот ещё не знает ваш номер,{' '}
                    <a href={(botConfig && botConfig.bot_connect_url) || 'https://t.me/AVITOPF_bot?start=connect'} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary)', fontWeight: 600 }}>откройте @{(botConfig && botConfig.bot_username) || 'AVITOPF_bot'}</a>
                    {' '}— он сразу попросит поделиться контактом
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
