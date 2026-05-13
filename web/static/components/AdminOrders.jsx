// AdminOrders — admin view of all orders with status edit.
const { useState: useAdmOState, useEffect: useAdmOEffect } = React;

const ADMIN_STATUSES = ['Posted', 'Pending', 'Completed', 'Cancelled'];

function AdminOrders({ onNavigate }) {
  const [statusFilter, setStatusFilter] = useAdmOState('all');
  const [page, setPage] = useAdmOState(1);
  const [items, setItems] = useAdmOState([]);
  const [total, setTotal] = useAdmOState(0);
  const [loading, setLoading] = useAdmOState(true);
  const [busyId, setBusyId] = useAdmOState(null);

  const load = async (p, sf) => {
    setLoading(true);
    let url = `/api/admin/orders?page=${p}&page_size=20`;
    if (sf && sf !== 'all') url += `&status=${sf}`;
    try {
      const data = await api.get(url);
      if (!data.__unauthorized) {
        setItems(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (_) {} finally { setLoading(false); }
  };

  useAdmOEffect(() => { load(page, statusFilter); }, [page, statusFilter]);

  const setStatus = async (orderId, nextStatus) => {
    setBusyId(orderId);
    try {
      await api.post(`/api/admin/orders/${orderId}/status`, { status: nextStatus });
      await load(page, statusFilter);
    } catch (e) { alert(e.message || 'Не удалось изменить статус'); }
    finally { setBusyId(null); }
  };

  const totalPages = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="page-wrap">
      <div className="container" style={{ padding: '28px 20px 80px' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: 16 }}>Заказы</h1>

        <div className="orders-filters" style={{ marginBottom: 16 }}>
          {['all', ...ADMIN_STATUSES].map(s => (
            <button
              key={s}
              className={`filter-tab${statusFilter === s ? ' active' : ''}`}
              onClick={() => { setStatusFilter(s); setPage(1); }}
            >{s === 'all' ? 'Все' : s}</button>
          ))}
        </div>

        {loading
          ? <div style={{ color: 'var(--text-3)' }}>Загрузка...</div>
          : (
            <div className="card" style={{ overflow: 'hidden' }}>
              <table className="orders-table">
                <thead>
                  <tr><th>#</th><th>Юзер</th><th>Услуга</th><th>Сумма</th><th>Статус</th><th>Дата</th><th>Действия</th></tr>
                </thead>
                <tbody>
                  {items.map(o => (
                    <tr key={o.order_id}>
                      <td style={{ color: 'var(--text-3)', fontWeight: 600 }}>#{o.order_id}</td>
                      <td>{o.user_name ? '@' + o.user_name : '#' + o.user_id}</td>
                      <td>{o.position_name}</td>
                      <td style={{ fontWeight: 700 }}>{o.price.toLocaleString('ru-RU')} ₽</td>
                      <td><StatusBadge status={o.status} /></td>
                      <td style={{ color: 'var(--text-3)', fontSize: '0.8rem' }}>{o.date || '—'}</td>
                      <td>
                        <select
                          className="input"
                          value={o.status}
                          onChange={e => setStatus(o.order_id, e.target.value)}
                          disabled={busyId === o.order_id}
                          style={{ padding: '4px 8px', fontSize: '0.8rem', minWidth: 130 }}
                        >
                          {ADMIN_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                  {items.length === 0 && (
                    <tr><td colSpan="7" style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)' }}>Заказов нет</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )
        }

        {totalPages > 1 && (
          <div className="pagination" style={{ marginTop: 14 }}>
            <button className="pagination__btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Назад</button>
            <span className="pagination__info">Стр. {page} из {totalPages}</span>
            <button className="pagination__btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Вперёд →</button>
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { AdminOrders });
