// Cabinet — dashboard: balance, catalog, orders, refill, support chat
const { useState: useCabinetState, useEffect: useCabinetEffect, useRef: useCabinetRef } = React;

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

function SupportChat({ chatOpen, setChatOpen }) {
  const [messages, setMessages] = useCabinetState([]);
  const [input, setInput] = useCabinetState('');
  const [unread, setUnread] = useCabinetState(0);
  const [sending, setSending] = useCabinetState(false);
  const msgEndRef = useCabinetRef(null);
  const lastIdRef = useCabinetRef(0);
  const pollRef = useCabinetRef(null);

  const loadMessages = async (since = 0) => {
    try {
      const msgs = await api.get('/api/support/messages?since_id=' + since);
      if (msgs.__unauthorized) return;
      if (msgs.length > 0) {
        setMessages(prev => [...prev, ...msgs]);
        lastIdRef.current = msgs[msgs.length - 1].id;
        if (!chatOpen) setUnread(u => u + msgs.filter(m => m.direction === 'admin').length);
      }
    } catch (_) {}
  };

  useCabinetEffect(() => {
    loadMessages(0);
    pollRef.current = setInterval(() => loadMessages(lastIdRef.current), 3000);
    return () => clearInterval(pollRef.current);
  }, []);

  useCabinetEffect(() => {
    if (chatOpen) setUnread(0);
  }, [chatOpen]);

  useCabinetEffect(() => {
    if (msgEndRef.current) {
      msgEndRef.current.scrollTop = msgEndRef.current.scrollHeight;
    }
  }, [messages, chatOpen]);

  const sendMessage = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput('');
    setSending(true);
    const optimistic = {
      id: Date.now(),
      direction: 'user',
      text,
      created_at: new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    };
    setMessages(m => [...m, optimistic]);
    try {
      await api.post('/api/support/messages', { text });
    } catch (_) {}
    setSending(false);
  };

  return (
    <div className="chat-widget">
      {chatOpen && (
        <div className="chat-panel">
          <div className="chat-panel__header">
            <div className="chat-panel__header-avatar" style={{ fontWeight: 700, fontSize: '0.875rem' }}>ТП</div>
            <div className="chat-panel__header-info">
              <div className="chat-panel__header-name">Поддержка</div>
              <div className="chat-panel__header-status">● Онлайн</div>
            </div>
            <button className="chat-panel__close" onClick={() => setChatOpen(false)}>✕</button>
          </div>
          <div className="chat-messages" ref={msgEndRef}>
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: '0.8125rem', padding: '20px 0' }}>
                Напишите ваш вопрос — поддержка ответит в Telegram
              </div>
            )}
            {messages.map(m => (
              <div key={m.id} className={`chat-msg chat-msg--${m.direction}`}>
                <div className="chat-msg__bubble">{m.text}</div>
                <div className="chat-msg__time">{typeof m.created_at === 'string' ? m.created_at.slice(11, 16) : m.created_at}</div>
              </div>
            ))}
          </div>
          <div className="chat-input-row">
            <input
              className="chat-input"
              placeholder="Сообщение..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
            />
            <button className="chat-send-btn" onClick={sendMessage} title="Отправить" disabled={sending}>➤</button>
          </div>
        </div>
      )}
      <button className="chat-widget__btn" onClick={() => setChatOpen(v => !v)} title="Поддержка">
        {chatOpen ? '×' : 'Чат'}
        {!chatOpen && unread > 0 && <span className="chat-widget__badge">{unread}</span>}
      </button>
    </div>
  );
}

function CabinetPage({ user, balance, setBalance, refreshBalance, onNavigate }) {
  const [recentOrders, setRecentOrders] = useCabinetState([]);
  const [refillAmount, setRefillAmount] = useCabinetState(1000);
  const [refillStatus, setRefillStatus] = useCabinetState(null); // null | 'pending' | 'polling' | 'success' | 'error'
  const [refillPaymentId, setRefillPaymentId] = useCabinetState(null);
  const [chatOpen, setChatOpen] = useCabinetState(false);

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

          {/* Welcome strip + Balance widget */}
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

            {/* Balance card */}
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
                  className="input"
                  type="number"
                  min={100}
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
                <div className="balance-status" style={{ marginTop: 8, padding: '8px 12px', fontSize: '0.8rem', background: 'var(--status-cancel-bg)', color: 'var(--status-cancel-text)' }}>
                  ❌ Ошибка оплаты. Попробуйте снова.
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
                          <tr key={o.order_id}>
                            <td style={{ color: 'var(--text-3)', fontWeight: 600 }}>#{o.order_id}</td>
                            <td style={{ fontWeight: 600 }}>{o.position_name}</td>
                            <td style={{ fontWeight: 700 }}>{o.price.toLocaleString('ru-RU')} ₽</td>
                            <td><StatusBadge status={o.status} /></td>
                            <td style={{ color: 'var(--text-3)' }}>{o.date ? new Date(o.date).toLocaleDateString('ru-RU') : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mobile-only">
                    {recentOrders.map(o => (
                      <div key={o.order_id} className="order-card-mobile">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{o.position_name}</div>
                            <div style={{ color: 'var(--text-3)', fontSize: '0.75rem', marginTop: 2 }}>#{o.order_id} · {o.date ? new Date(o.date).toLocaleDateString('ru-RU') : '—'}</div>
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

      <SupportChat chatOpen={chatOpen} setChatOpen={setChatOpen} />
    </div>
  );
}

Object.assign(window, { CabinetPage, StatusBadge });
