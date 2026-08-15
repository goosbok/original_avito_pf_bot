// Referral — партнерская программа: ссылки-кампании, статистика, история начислений.
const { useState: useRefState, useEffect: useRefEffect } = React;

function ReferralPage({ user, botConfig, onNavigate, refreshBalance }) {
  const [data, setData] = useRefState(null);
  const [bonuses, setBonuses] = useRefState([]);
  const [slug, setSlug] = useRefState('');
  const [busy, setBusy] = useRefState(false);
  const [error, setError] = useRefState('');
  const [copied, setCopied] = useRefState('');
  const [tab, setTab] = useRefState('active');   // 'active' | 'hidden'
  const [page, setPage] = useRefState(0);

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

  // Вывод на карту делается вручную поддержкой: открываем чат с готовым сообщением.
  const withdrawToCard = () => {
    const text = 'хочу бабки на карту вывести';
    window.dispatchEvent(new CustomEvent('support-chat-send', { detail: { text } }));
  };

  const withdraw = async () => {
    setBusy(true); setError('');
    try {
      await api.post('/api/me/referral/withdraw', {});
      setData(d => ({ ...d, referral_balance: 0 }));
      refreshBalance();
    } catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };

  if (!data) return <div className="page-wrap"><div className="container" style={{ paddingTop: 20 }}><div style={{ color: 'var(--text-3)' }}>Загрузка...</div></div></div>;

  const active = data.links.filter(l => !l.archived_at);
  const hidden = data.links.filter(l => l.archived_at);

  const PAGE_SIZE = 5;
  const shown = tab === 'active' ? active : hidden;
  const pageCount = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageItems = shown.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);
  const switchTab = (t) => { setTab(t); setPage(0); };

  return (
    <div className="page-wrap">
    <div className="container" style={{ paddingTop: 20, paddingBottom: 96 }}>
      <h1 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: 8 }}>🤝 Пригласи друга</h1>

      <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>Как это работает</div>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-2)', display: 'grid', gap: 8 }}>
          <div>
            Делитесь ссылкой и получайте <strong>{data.percent}%</strong> с каждого
            пополнения приглашённых пользователей на реферальный баланс.
          </div>
          <div>
            <strong>Пожизненно:</strong> процент начисляется с каждого их платежа, а не только
            с первого. Чем больше общий объём пополнений от ваших рефералов, тем выше
            процент — до 30% с каждого платежа.
          </div>
          <div>
            Реферальный баланс можно вывести на основной счёт для оплаты наших услуг
            или на банковскую карту.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 24, marginTop: 12, fontSize: '0.875rem', flexWrap: 'wrap' }}>
          <div>Рефералов: <strong>{data.referrals_count}</strong></div>
          <div>Заработано: <strong style={{ color: 'var(--primary)', whiteSpace: 'nowrap' }}>{data.total_earned.toLocaleString('ru-RU')} ₽</strong></div>
          <div>Доступно к выводу: <strong style={{ color: 'var(--primary)', whiteSpace: 'nowrap' }}>{data.referral_balance.toLocaleString('ru-RU')} ₽</strong></div>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <button className="btn btn--primary btn--sm" onClick={withdrawToCard}
                  disabled={busy || data.referral_balance === 0}>
            Вывести на карту
          </button>
          <button className="btn btn--ghost btn--sm" onClick={withdraw}
                  disabled={busy || data.referral_balance === 0}>
            Перевести на баланс
          </button>
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
        <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
          <button className={'btn btn--sm ' + (tab === 'active' ? 'btn--primary' : 'btn--ghost')}
                  onClick={() => switchTab('active')}>Активные ({active.length})</button>
          <button className={'btn btn--sm ' + (tab === 'hidden' ? 'btn--primary' : 'btn--ghost')}
                  onClick={() => switchTab('hidden')}>Скрытые ({hidden.length})</button>
        </div>

        {tab === 'hidden' && hidden.length > 0 && (
          <div style={{ fontSize: '0.78rem', color: 'var(--text-3)', marginBottom: 6 }}>
            Новых рефералов по ним не привести, но начисления по уже приведённым продолжаются. Можно вернуть в активные.
          </div>
        )}

        {shown.length === 0
          ? <div style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>
              {tab === 'active' ? 'Пока нет — создайте первую выше.' : 'Скрытых ссылок нет.'}
            </div>
          : pageItems.map(l => (
            <div key={l.id} style={{ borderTop: '1px solid var(--border)', padding: '12px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                <strong style={tab === 'hidden' ? { color: 'var(--text-3)' } : undefined}>{l.slug}</strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-3)' }}>
                  {l.effective_percent}% · клики: {l.clicks} · регистрации: {l.registrations} · заработано: <span style={{ whiteSpace: 'nowrap' }}>{l.earned.toLocaleString('ru-RU')} ₽</span>
                </span>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                {tab === 'active' ? (
                  <>
                    <button className="btn btn--ghost btn--sm" onClick={() => copy(siteLink(l), 'site' + l.id)}>
                      {copied === 'site' + l.id ? '✓ Скопировано' : '🌐 Ссылка на сайт'}
                    </button>
                    <button className="btn btn--ghost btn--sm" onClick={() => copy(botLink(l), 'bot' + l.id)}>
                      {copied === 'bot' + l.id ? '✓ Скопировано' : '🤖 Ссылка на бота'}
                    </button>
                    <button className="btn btn--ghost btn--sm" onClick={() => hide(l.id)} disabled={busy}>Скрыть</button>
                  </>
                ) : (
                  <button className="btn btn--ghost btn--sm" onClick={() => restore(l.id)} disabled={busy}>Показать</button>
                )}
              </div>
            </div>
          ))}

        {pageCount > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, marginTop: 12, fontSize: '0.85rem' }}>
            <button className="btn btn--ghost btn--sm" disabled={safePage === 0}
                    onClick={() => setPage(safePage - 1)}>← Назад</button>
            <span style={{ color: 'var(--text-3)' }}>{safePage + 1} / {pageCount}</span>
            <button className="btn btn--ghost btn--sm" disabled={safePage >= pageCount - 1}
                    onClick={() => setPage(safePage + 1)}>Вперёд →</button>
          </div>
        )}
      </div>

      <div className="card" style={{ padding: '16px 20px' }}>
        <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>История начислений</h3>
        {bonuses.length === 0
          ? <div style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>Начислений пока нет.</div>
          : bonuses.map(b => (
            <div key={b.id} style={{ padding: '8px 0', borderTop: '1px solid var(--border)', fontSize: '0.875rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span>{formatDate ? formatDate(b.created_at) : b.created_at}</span>
                <strong style={{ color: 'var(--primary)', whiteSpace: 'nowrap', flexShrink: 0 }}>+{b.amount.toLocaleString('ru-RU')} ₽</strong>
              </div>
              <div style={{ color: 'var(--text-3)', marginTop: 2 }}>реферал #{b.referred_user_id}{b.link_slug ? ` · ${b.link_slug}` : ''} · {b.percent}%</div>
            </div>
          ))}
      </div>
    </div>
    </div>
  );
}

Object.assign(window, { ReferralPage });
