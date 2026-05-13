// AdminUsers — search + detail drawer with balance-credit and VIP toggle.
const { useState: useAdmUState, useEffect: useAdmUEffect } = React;

function AdminUsers({ onNavigate }) {
  const [q, setQ] = useAdmUState('');
  const [items, setItems] = useAdmUState([]);
  const [loading, setLoading] = useAdmUState(true);
  const [selected, setSelected] = useAdmUState(null);

  const load = async (search) => {
    setLoading(true);
    try {
      const data = await api.get('/api/admin/users?page=1&page_size=50' + (search ? `&q=${encodeURIComponent(search)}` : ''));
      if (!data.__unauthorized) setItems(data.items || []);
    } catch (_) {} finally { setLoading(false); }
  };

  useAdmUEffect(() => { load(''); }, []);

  return (
    <div className="page-wrap">
      <div className="container" style={{ padding: '28px 20px 80px', maxWidth: 1100 }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: 16 }}>Пользователи</h1>

        <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
          <input
            className="input"
            placeholder="Поиск по id, username, имени"
            value={q}
            onChange={e => setQ(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load(q)}
            style={{ flex: 1 }}
          />
          <button className="btn btn--primary" onClick={() => load(q)}>Искать</button>
        </div>

        {loading
          ? <div style={{ color: 'var(--text-3)' }}>Загрузка...</div>
          : (
            <div className="card" style={{ overflow: 'hidden' }}>
              <table className="orders-table">
                <thead>
                  <tr><th>#</th><th>Username</th><th>Имя</th><th>Баланс</th><th>VIP</th><th>Регистрация</th></tr>
                </thead>
                <tbody>
                  {items.map(u => (
                    <tr key={u.user_id} style={{ cursor: 'pointer' }} onClick={() => setSelected(u.user_id)}>
                      <td style={{ color: 'var(--text-3)', fontWeight: 600 }}>#{u.user_id}</td>
                      <td>{u.user_name ? '@' + u.user_name : '—'}</td>
                      <td>{u.first_name || '—'}</td>
                      <td style={{ fontWeight: 700, color: 'var(--primary)' }}>{u.balance.toLocaleString('ru-RU')} ₽</td>
                      <td>{u.is_vip ? '⭐' : ''}</td>
                      <td style={{ color: 'var(--text-3)', fontSize: '0.8rem' }}>{u.reg_date ? u.reg_date.slice(0, 10) : '—'}</td>
                    </tr>
                  ))}
                  {items.length === 0 && (
                    <tr><td colSpan="6" style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)' }}>Ничего не нашли</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )
        }

        {selected && (
          <AdminUserDrawer
            userId={selected}
            onClose={() => setSelected(null)}
            onUserChanged={() => load(q)}
          />
        )}
      </div>
    </div>
  );
}

function AdminUserDrawer({ userId, onClose, onUserChanged }) {
  const [data, setData] = useAdmUState(null);
  const [delta, setDelta] = useAdmUState(1000);
  const [reason, setReason] = useAdmUState('');
  const [busy, setBusy] = useAdmUState(false);
  const [error, setError] = useAdmUState('');
  const [okMsg, setOkMsg] = useAdmUState('');

  const reload = async () => {
    try {
      const fresh = await api.get('/api/admin/users/' + userId);
      if (!fresh.__unauthorized) setData(fresh);
    } catch (e) { setError(e.message || 'Ошибка загрузки'); }
  };

  useAdmUEffect(() => { reload(); }, [userId]);

  const credit = async () => {
    if (!delta || delta <= 0) return setError('Сумма должна быть > 0');
    if (!reason.trim()) return setError('Укажите причину начисления');
    setBusy(true); setError(''); setOkMsg('');
    try {
      const res = await api.post('/api/admin/users/' + userId + '/balance', { delta: Number(delta), reason: reason.trim() });
      setOkMsg(`Начислено ${res.balance_after - res.balance_before} ₽. Новый баланс: ${res.balance_after} ₽.`);
      setReason('');
      await reload();
      onUserChanged && onUserChanged();
    } catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };

  const toggleVip = async () => {
    if (!data) return;
    setBusy(true); setError('');
    try {
      await api.post('/api/admin/users/' + userId + '/vip', { is_vip: !data.is_vip });
      await reload();
      onUserChanged && onUserChanged();
    } catch (e) { setError(e.message || 'Ошибка'); }
    finally { setBusy(false); }
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 250, display: 'flex', justifyContent: 'flex-end' }}
      onClick={onClose}
    >
      <div
        style={{ width: 'min(560px, 100%)', background: 'var(--surface)', borderLeft: '1px solid var(--border)', padding: '24px 28px', overflowY: 'auto', boxShadow: 'var(--shadow-lg)' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 16 }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 800 }}>Пользователь #{userId}</h2>
          <button className="btn btn--ghost btn--sm" onClick={onClose}>✕</button>
        </div>
        {!data ? <div style={{ color: 'var(--text-3)' }}>Загрузка...</div> : (
          <>
            <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
              <div style={{ marginBottom: 8 }}><strong>{data.first_name || '—'}</strong> {data.user_name ? '· @' + data.user_name : ''}</div>
              <div style={{ color: 'var(--text-3)', fontSize: '0.8rem' }}>Регистрация: {data.reg_date ? data.reg_date.slice(0, 10) : '—'}</div>
              <div style={{ marginTop: 10, fontSize: '0.875rem' }}>
                Баланс: <strong style={{ color: 'var(--primary)' }}>{data.balance.toLocaleString('ru-RU')} ₽</strong> · VIP: {data.is_vip ? '⭐ да' : 'нет'}
              </div>
              <div style={{ marginTop: 10, fontSize: '0.78rem', color: 'var(--text-3)' }}>
                Привязки: {data.providers.length === 0 ? 'нет' : data.providers.map(p => `${p.provider}:${p.identifier}`).join(', ')}
              </div>
            </div>

            {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}
            {okMsg && <div className="alert alert--success" style={{ marginBottom: 12 }}>{okMsg}</div>}

            <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
              <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>Ручное пополнение</h3>
              <div className="form-field" style={{ marginBottom: 10 }}>
                <label className="form-label">Сумма (₽)</label>
                <input className="input" type="number" min={1} value={delta} onChange={e => setDelta(Number(e.target.value))} />
              </div>
              <div className="form-field" style={{ marginBottom: 12 }}>
                <label className="form-label">Причина (для аудита)</label>
                <input className="input" type="text" placeholder="Например: компенсация заказа #42" value={reason} onChange={e => setReason(e.target.value)} />
              </div>
              <button className="btn btn--primary btn--full" onClick={credit} disabled={busy}>
                {busy ? 'Начисляем...' : `+ Начислить ${Number(delta || 0).toLocaleString('ru-RU')} ₽`}
              </button>
            </div>

            <div className="card" style={{ padding: '16px 20px', marginBottom: 16 }}>
              <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>VIP</h3>
              <button className="btn btn--ghost btn--full" onClick={toggleVip} disabled={busy}>
                {data.is_vip ? 'Убрать VIP' : 'Сделать VIP'}
              </button>
            </div>

            <div className="card" style={{ padding: '16px 20px' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: 10 }}>Последние заказы</h3>
              {data.recent_orders.length === 0
                ? <div style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>Заказов нет</div>
                : data.recent_orders.map(o => (
                    <div key={o.order_id} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid var(--border)' }}>
                      <span>#{o.order_id} · {o.position_name} · {o.status}</span>
                      <span style={{ fontWeight: 700 }}>{o.price.toLocaleString('ru-RU')} ₽</span>
                    </div>
                ))
              }
            </div>
          </>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { AdminUsers });
