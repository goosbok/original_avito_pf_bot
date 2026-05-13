// Orders history page with real API + client-side filter + server-side pagination
const { useState: useOrdersState, useEffect: useOrdersEffect } = React;

const STATUS_FILTERS = [
  { key: 'all',       label: 'Все' },
  { key: 'Posted',    label: 'В работе' },
  { key: 'Completed', label: 'Завершённые' },
  { key: 'Cancelled', label: 'Отменённые' },
];

const PAGE_SIZE = 20;

function parseLinksStr(s) {
  if (!s) return [];
  return String(s).split(',')
    .map(l => l.trim().replace(/^['"\[\] ]+|['"\[\] ]+$/g, ''))
    .filter(l => l.startsWith('http'));
}

function OrderMobileCard({ order: o, onNavigate }) {
  return (
    <div style={{ borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
         onClick={() => onNavigate('order-detail', o)}>
      <div style={{ padding: '14px 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{displayServiceName(o)}</div>
            <div style={{ color: 'var(--text-3)', fontSize: '0.75rem', marginTop: 2 }}>
              #{o.order_id} · {o.date || '—'}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <StatusBadge status={o.status} />
            <div style={{ fontWeight: 700, color: 'var(--primary)', marginTop: 5, fontSize: '0.9rem' }}>
              {o.price.toLocaleString('ru-RU')} ₽
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--primary)', fontWeight: 600 }}>
            Подробнее →
          </span>
        </div>
      </div>
    </div>
  );
}

function OrdersPage({ onNavigate }) {
  const [orders, setOrders] = useOrdersState([]);
  const [total, setTotal] = useOrdersState(0);
  const [filter, setFilter] = useOrdersState('all');
  const [page, setPage] = useOrdersState(1);
  const [loading, setLoading] = useOrdersState(true);

  const loadOrders = async (p = 1) => {
    setLoading(true);
    try {
      const data = await api.get(`/api/orders?page=${p}&page_size=${PAGE_SIZE}`);
      if (!data.__unauthorized) {
        setOrders(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (_) {} finally { setLoading(false); }
  };

  useOrdersEffect(() => { loadOrders(page); }, [page]);

  const filtered = filter === 'all' ? orders : orders.filter(o => o.status === filter);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleFilter = (key) => { setFilter(key); };
  const handlePage = (p) => { setPage(p); loadOrders(p); };

  return (
    <div className="page-wrap">
      <div className="orders-page">
        <div className="container">

          <button className="order-back" onClick={() => onNavigate('cabinet')}>← Назад в кабинет</button>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
            <h2>История заказов</h2>
            <button className="btn btn--primary btn--sm" onClick={() => onNavigate('order-pf')}>
              + Новый заказ
            </button>
          </div>

          <div className="orders-filters">
            {STATUS_FILTERS.map(f => (
              <button
                key={f.key}
                className={`filter-tab${filter === f.key ? ' active' : ''}`}
                onClick={() => handleFilter(f.key)}
              >
                {f.label}
                {f.key !== 'all' && (
                  <span style={{ marginLeft: 6, opacity: 0.7 }}>
                    ({orders.filter(o => o.status === f.key).length})
                  </span>
                )}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)' }}>Загрузка...</div>
          ) : filtered.length === 0 ? (
            <div className="card">
              <div className="empty-state">
                <div className="empty-state__icon" style={{ fontSize: '1.5rem' }}>—</div>
                <div className="empty-state__title">Заказов не найдено</div>
                <div className="empty-state__desc">
                  {filter === 'all' ? 'Вы ещё не сделали ни одного заказа' : 'Нет заказов с таким статусом'}
                </div>
                <button className="btn btn--primary" onClick={() => onNavigate('cabinet')}>Выбрать услугу</button>
              </div>
            </div>
          ) : (
            <>
              <div className="card desktop-only" style={{ overflow: 'hidden' }}>
                <table className="orders-table">
                  <thead>
                    <tr><th>#</th><th>Услуга</th><th>Сумма</th><th>Статус</th><th>Дата</th><th>Ссылки</th></tr>
                  </thead>
                  <tbody>
                    {filtered.map(o => {
                      const links = parseLinksStr(o.links);
                      return (
                        <tr key={o.order_id} style={{ cursor: 'pointer' }} onClick={() => onNavigate('order-detail', o)}>
                          <td style={{ color: 'var(--text-3)', fontWeight: 600 }}>#{o.order_id}</td>
                          <td style={{ fontWeight: 600 }}>{displayServiceName(o)}</td>
                          <td><span style={{ fontWeight: 700 }}>{o.price.toLocaleString('ru-RU')} ₽</span></td>
                          <td><StatusBadge status={o.status} /></td>
                          <td style={{ color: 'var(--text-3)', fontSize: '0.8125rem' }}>
                            {o.date || '—'}
                          </td>
                          <td style={{ color: 'var(--text-3)', fontSize: '0.75rem' }}>
                            {links.length > 0 ? `${links.length} ссылк.` : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="card mobile-only" style={{ overflow: 'hidden' }}>
                {filtered.map(o => <OrderMobileCard key={o.order_id} order={o} onNavigate={onNavigate} />)}
              </div>

              {totalPages > 1 && (
                <div className="pagination">
                  <button className="pagination__btn" disabled={page <= 1} onClick={() => handlePage(page - 1)}>← Назад</button>
                  <span className="pagination__info">Страница {page} из {totalPages}</span>
                  <button className="pagination__btn" disabled={page >= totalPages} onClick={() => handlePage(page + 1)}>Вперёд →</button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { OrdersPage });
