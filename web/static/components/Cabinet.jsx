// Cabinet — dashboard: balance, catalog, recent orders, refill.
// SupportChat is mounted at the app root (web/static/components/SupportChat.jsx).
const { useState: useCabinetState, useEffect: useCabinetEffect } = React;

const SERVICES = [
  { id: 'pf',      abbr: 'ПФ',  name: 'Авито ПФ',    desc: 'Просмотры, лайки, контакты для объявлений', price: 'от 6 ₽/ПФ', available: true,  route: 'order-pf' },
  { id: 'reviews', abbr: 'ОТЗ', name: 'Отзывы',       desc: 'Накрутка / удаление: Авито, ВК, Яндекс, 2ГИС, Google', price: 'по тарифу', available: true,  route: null },
  { id: 'ypf',     abbr: 'ЯПФ', name: 'Яндекс ПФ',   desc: 'Поведенческие факторы для Яндекс', price: null, badge: 'В разработке', available: false, route: null },
  { id: 'seo',     abbr: 'SEO', name: 'SEO-буст',     desc: 'Ссылочное продвижение и рост позиций', price: null, badge: 'Скоро', available: false, route: null },
  { id: 'copy',    abbr: 'КП',  name: 'Копирайтинг', desc: 'Тексты для объявлений и карточек', price: null, badge: 'Скоро', available: false, route: null },
  { id: 'smm',     abbr: 'SMM', name: 'SMM',          desc: 'Ведение соцсетей и создание контента', price: null, badge: 'Скоро', available: false, route: null },
];

const PRESETS = [500, 1000, 2000, 5000];

function StatusBadge({ status }) {
  const map = { Posted: 'posted', Completed: 'completed', Cancelled: 'cancelled', Pending: 'pending' };
  const labels = { Posted: 'В работе', Completed: 'Завершён', Cancelled: 'Отменён', Pending: 'Ожидание' };
  return <span className={`badge badge--${map[status] || 'muted'}`}>{labels[status] || status}</span>;
}

// Backend stores Авито PF orders with position_name like "7/30" (days/views).
// Display nicer service name in tables.
function displayServiceName(o) {
  if (/^\d+\/\d+$/.test(String(o.position_name || ''))) return 'Авито ПФ';
  return o.position_name || '—';
}

function CabinetPage({ user, balance, setBalance, refreshBalance, onNavigate }) {
  const [recentOrders, setRecentOrders] = useCabinetState([]);
  const [refillAmount, setRefillAmount] = useCabinetState(1000);
  const [refillStatus, setRefillStatus] = useCabinetState(null);
  const [refillPaymentId, setRefillPaymentId] = useCabinetState(null);

  const openSupportForRefill = () => {
    const text = `Хочу пополнить баланс на ${Number(refillAmount).toLocaleString('ru-RU')} ₽, но через сайт не получается. Помогите, пожалуйста.`;
    window.dispatchEvent(new CustomEvent('support-chat-send', { detail: { text } }));
  };

  useCabinetEffect(() => {
    api.get('/api/orders?page=1&page_size=5').then(data => {
      if (!data.__unauthorized) setRecentOrders(data.items || []);
    }).catch(() => {});
  }, []);

  const handleRefill = async () => {
    if (!refillAmount || refillAmount < 100) return;
    setRefillStatus('pending');
    try {
      const data = await api.post('/api/refill', { amount: Number(refillAmount) });
      setRefillPaymentId(data.payment_id);
      window.open(data.payment_url, '_blank');
      setRefillStatus('polling');
    } catch (e) {
      // Backend logs error + alerts admins. Client sees generic message only.
      setRefillStatus('error');
    }
  };

  const checkRefillStatus = async () => {
    if (!refillPaymentId) return;
    try {
      const data = await api.get(`/api/refill/${refillPaymentId}/status`);
      if (data.status === 'succeeded') {
        setRefillStatus('success');
        refreshBalance();
        setTimeout(() => { setRefillStatus(null); setRefillPaymentId(null); }, 4000);
      } else if (data.status === 'failed') {
        setRefillStatus('error');
      }
    } catch (_) {}
  };

  const handleServiceClick = (service) => {
    if (!service.available) return;
    if (service.route) onNavigate(service.route);
    else alert(`Услуга "${service.name}" — оформление через менеджера в Telegram`);
  };

  return (
    <div className="page-wrap">
      <div className="cabinet">
        <div className="container">

          <div className="cabinet-top-row" style={{
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
            gap: 16, flexWrap: 'wrap', marginBottom: 28
          }}>
            <div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: 4 }}>
                Привет, {user.first_name}
              </h2>
              <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>
                Личный кабинет · Управляйте заказами и балансом
              </p>
            </div>

            <div className="card cabinet-balance-card" style={{ padding: '16px 20px', minWidth: 260, flex: '0 0 auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Баланс</span>
                <span style={{ fontSize: '1.375rem', fontWeight: 800, color: 'var(--primary)' }}>{balance.toLocaleString('ru-RU')} ₽</span>
              </div>
              <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                {PRESETS.slice(0, 3).map(p => (
                  <button
                    key={p}
                    className={`balance-preset${refillAmount === p ? ' active' : ''}`}
                    style={{ flex: 1, fontSize: '0.75rem', padding: '5px 4px' }}
                    onClick={() => setRefillAmount(p)}
                  >
                    {p.toLocaleString('ru-RU')} ₽
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="input" type="number" min={100}
                  value={refillAmount}
                  onChange={e => setRefillAmount(Number(e.target.value))}
                  placeholder="Сумма"
                  style={{ flex: 1, padding: '8px 10px', fontSize: '0.875rem' }}
                />
                <button
                  className="btn btn--primary btn--sm"
                  onClick={handleRefill}
                  disabled={refillStatus === 'pending' || refillStatus === 'polling' || !refillAmount || refillAmount < 100}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  {refillStatus === 'pending' ? '...' : 'Пополнить'}
                </button>
              </div>
              {refillStatus === 'polling' && (
                <div className="balance-status balance-status--pending" style={{ marginTop: 8, padding: '8px 12px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>⏳ Ожидаем оплаты</span>
                  <button
                    className="btn btn--ghost btn--sm"
                    onClick={checkRefillStatus}
                    style={{ fontSize: '0.75rem', padding: '3px 8px' }}
                  >Проверить</button>
                </div>
              )}
              {refillStatus === 'success' && (
                <div className="balance-status balance-status--success" style={{ marginTop: 8, padding: '8px 12px', fontSize: '0.8rem' }}>
                  ✅ {refillAmount.toLocaleString('ru-RU')} ₽ зачислено!
                </div>
              )}
              {refillStatus === 'error' && (
                <div
                  className="balance-status"
                  style={{
                    marginTop: 8, padding: '8px 12px', fontSize: '0.8rem',
                    background: 'var(--status-cancel-bg)', color: 'var(--status-cancel-text)',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                  }}
                >
                  <span>❌ Произошла ошибка</span>
                  <button
                    className="btn btn--sm"
                    onClick={openSupportForRefill}
                    style={{
                      fontSize: '0.7rem', padding: '3px 10px', whiteSpace: 'nowrap',
                      background: 'var(--status-cancel-text)', color: '#fff', borderColor: 'transparent',
                    }}
                  >Пополнить через поддержку</button>
                </div>
              )}
            </div>
          </div>

          {/* Catalog */}
          <div className="cabinet__section">
            <div className="section-header">
              <span className="section-title">Услуги</span>
            </div>
            <div className="catalog-grid">
              {SERVICES.map(s => (
                <div
                  key={s.id}
                  className={`card service-card card--hover${!s.available ? ' service-card--disabled' : ''}`}
                  onClick={() => handleServiceClick(s)}
                  style={{ cursor: s.available ? 'pointer' : 'default' }}
                >
                  <div style={{ width: 38, height: 38, borderRadius: 8, background: s.available ? 'var(--primary-dim)' : 'var(--surface-3)', color: s.available ? 'var(--primary)' : 'var(--text-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontWeight: 800, letterSpacing: '-0.01em' }}>{s.abbr}</div>
                  <div className="service-card__name">{s.name}</div>
                  <div className="service-card__desc">{s.desc}</div>
                  <div className="service-card__footer">
                    {s.available
                      ? <span className="service-card__price">{s.price}</span>
                      : <span className="badge badge--muted" style={{ fontSize: '0.7rem' }}>{s.badge}</span>
                    }
                    {s.available && <span style={{ fontSize: '0.75rem', color: 'var(--primary)', fontWeight: 700 }}>Заказать →</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Recent orders */}
          <div className="cabinet__section">
            <div className="section-header">
              <span className="section-title">Последние заказы</span>
              <button className="btn btn--ghost btn--sm" onClick={() => onNavigate('orders')}>
                Все заказы →
              </button>
            </div>
            <div className="card" style={{ overflow: 'hidden' }}>
              {recentOrders.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state__icon">📭</div>
                  <div className="empty-state__title">Заказов ещё нет</div>
                  <div className="empty-state__desc">Выберите услугу из каталога выше</div>
                </div>
              ) : (
                <>
                  <div className="desktop-only">
                    <table className="orders-table">
                      <thead>
                        <tr>
                          <th>#</th><th>Услуга</th><th>Сумма</th><th>Статус</th><th>Дата</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recentOrders.map(o => (
                          <tr key={o.order_id} style={{ cursor: 'pointer' }} onClick={() => onNavigate('order-detail', o)}>
                            <td style={{ color: 'var(--text-3)', fontWeight: 600 }}>#{o.order_id}</td>
                            <td style={{ fontWeight: 600 }}>{displayServiceName(o)}</td>
                            <td style={{ fontWeight: 700 }}>{o.price.toLocaleString('ru-RU')} ₽</td>
                            <td><StatusBadge status={o.status} /></td>
                            <td style={{ color: 'var(--text-3)' }}>{o.date || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mobile-only">
                    {recentOrders.map(o => (
                      <div key={o.order_id} className="order-card-mobile" style={{ cursor: 'pointer' }} onClick={() => onNavigate('order-detail', o)}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{displayServiceName(o)}</div>
                            <div style={{ color: 'var(--text-3)', fontSize: '0.75rem', marginTop: 2 }}>#{o.order_id} · {o.date || '—'}</div>
                          </div>
                          <StatusBadge status={o.status} />
                        </div>
                        <div style={{ fontWeight: 700, color: 'var(--primary)' }}>{o.price.toLocaleString('ru-RU')} ₽</div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

Object.assign(window, { CabinetPage, StatusBadge, displayServiceName });
