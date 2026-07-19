// Referral — партнерская программа: ссылки-кампании, статистика, история начислений.
const { useState: useRefState, useEffect: useRefEffect } = React;

function ReferralPage({ user, botConfig, onNavigate }) {
  const [data, setData] = useRefState(null);
  const [bonuses, setBonuses] = useRefState([]);
  const [slug, setSlug] = useRefState('');
  const [busy, setBusy] = useRefState(false);
  const [error, setError] = useRefState('');
  const [copied, setCopied] = useRefState('');

  const load = async () => {
    try {
      const d = await api.get('/api/me/referral');
      if (d.__unauthorized) return onNavigate('auth');
      setData(d);
      const b = await api.get('/api/me/referral/bonuses');
      if (!b.__unauthorized) setBonuses(b);
    } catch (e) { setError(e.message || 'Ошибка загрузки'); }
  };
  useRefEffect(() => { load(); }, []);

  const refCode = (l) => `${user.user_id}-${l.slug}`;
  const siteLink = (l) => `${window.location.origin}/?ref=${refCode(l)}`;
  const botLink = (l) => `${(botConfig && botConfig.bot_url) || 'https://t.me/AVITOPF_bot'}?start=ref_${refCode(l)}`;

  const copy = async (text, key) => {
    try { await navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(''), 1500); }
    catch (e) { setError('Не удалось скопировать'); }
  };

  const createLink = async () => {
    setBusy(true); setError('');
    try {
      await api.post('/api/me/referral/links', { slug: slug.trim().toLowerCase() });
      setSlug('');
      await load();
    } catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };

  // «Случайная» лишь подставляет валидный слаг в поле — ссылка создаётся
  // только после явного нажатия «Создать».
  const fillRandomSlug = () => {
    const abc = 'abcdefghijklmnopqrstuvwxyz0123456789';
    let s = '';
    for (let i = 0; i < 8; i++) s += abc[Math.floor(Math.random() * abc.length)];
    setSlug(s);
    setError('');
  };

  const hide = async (id) => {
    if (!confirm('Скрыть ссылку? Она уйдёт в «Скрытые»: новых по ней не привести, но начисления по уже приведённым рефералам продолжатся. Вернуть можно в любой момент.')) return;
    setBusy(true); setError('');
    try { await api.delete('/api/me/referral/links/' + id); await load(); }
    catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };

  const restore = async (id) => {
    setBusy(true); setError('');
    try { await api.post('/api/me/referral/links/' + id + '/restore'); await load(); }
    catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };

  if (!data) return <div className="page"><div style={{ color: 'var(--text-3)' }}>Загрузка...</div></div>;

  const active = data.links.filter(l => !l.archived_at);
  const hidden = data.links.filter(l => l.archived_at);

  return (
    <div className="page" style={{ paddingTop: 20 }}>
      <h1 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: 8 }}>🤝 Партнерка</h1>

      <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>Как это работает</div>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-2)' }}>
          Делитесь ссылкой — получайте <strong>{data.percent}%</strong> с каждого
          пополнения приведенных пользователей на баланс сервиса. Пожизненно.
        </div>
        <div style={{ display: 'flex', gap: 24, marginTop: 12, fontSize: '0.875rem' }}>
          <div>Рефералов: <strong>{data.referrals_count}</strong></div>
          <div>Заработано: <strong style={{ color: 'var(--primary)' }}>{data.total_earned.toLocaleString('ru-RU')} ₽</strong></div>
        </div>
      </div>

      {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>Новая ссылка</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input className="input" style={{ flex: '1 1 180px' }} placeholder="своя метка (латиница, 3-32)"
                 value={slug} onChange={e => setSlug(e.target.value)} disabled={busy} />
          <button className="btn btn--primary" onClick={createLink}
                  disabled={busy || slug.trim().length < 3}>Создать</button>
          <button className="btn btn--ghost" onClick={fillRandomSlug}
                  disabled={busy}>🎲 Случайная</button>
        </div>
      </div>

      <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>Мои ссылки</h3>
        {active.length === 0
          ? <div style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>Пока нет — создайте первую выше.</div>
          : active.map(l => (
            <div key={l.id} style={{ borderTop: '1px solid var(--border)', padding: '12px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                <strong>{l.slug}</strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-3)' }}>
                  {l.effective_percent}% · клики: {l.clicks} · регистрации: {l.registrations} · заработано: {l.earned.toLocaleString('ru-RU')} ₽
                </span>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                <button className="btn btn--ghost btn--sm" onClick={() => copy(siteLink(l), 'site' + l.id)}>
                  {copied === 'site' + l.id ? '✓ Скопировано' : '🌐 Ссылка на сайт'}
                </button>
                <button className="btn btn--ghost btn--sm" onClick={() => copy(botLink(l), 'bot' + l.id)}>
                  {copied === 'bot' + l.id ? '✓ Скопировано' : '🤖 Ссылка на бота'}
                </button>
                <button className="btn btn--ghost btn--sm" onClick={() => hide(l.id)} disabled={busy}>Скрыть</button>
              </div>
            </div>
          ))}
      </div>

      {hidden.length > 0 && (
        <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
          <h3 style={{ fontSize: '1rem', marginBottom: 4 }}>Скрытые ссылки</h3>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-3)', marginBottom: 6 }}>
            Новых рефералов по ним не привести, но начисления по уже приведённым продолжаются. Можно вернуть в активные.
          </div>
          {hidden.map(l => (
            <div key={l.id} style={{ borderTop: '1px solid var(--border)', padding: '12px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                <strong style={{ color: 'var(--text-3)' }}>{l.slug}</strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-3)' }}>
                  {l.effective_percent}% · клики: {l.clicks} · регистрации: {l.registrations} · заработано: {l.earned.toLocaleString('ru-RU')} ₽
                </span>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <button className="btn btn--ghost btn--sm" onClick={() => restore(l.id)} disabled={busy}>Показать</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card" style={{ padding: '16px 20px' }}>
        <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>История начислений</h3>
        {bonuses.length === 0
          ? <div style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>Начислений пока нет.</div>
          : bonuses.map(b => (
            <div key={b.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid var(--border)', fontSize: '0.875rem' }}>
              <span>{formatDate ? formatDate(b.created_at) : b.created_at} · реферал #{b.referred_user_id}{b.link_slug ? ` · ${b.link_slug}` : ''} · {b.percent}%</span>
              <strong style={{ color: 'var(--primary)' }}>+{b.amount.toLocaleString('ru-RU')} ₽</strong>
            </div>
          ))}
      </div>
    </div>
  );
}

Object.assign(window, { ReferralPage });
