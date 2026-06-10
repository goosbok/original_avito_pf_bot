// Order detail page — universal for all statuses (unpaid / paid / done / failed /
// payment_failed / cancelled). Polls /payment-status every 5s while 'unpaid'.
// Terminal statuses show "Повторить заказ" with prefill.
const { useState: useODState, useEffect: useODEffect, useRef: useODRef } = React;

function detectServiceType(order) {
  const pn = String(order.position_name || '');
  if (/^\d+\/\d+$/.test(pn)) return 'avito-pf';
  if (pn === 'Авито ПФ') return 'avito-pf';
  return 'generic';
}

function serviceDisplayName(serviceType, order) {
  if (serviceType === 'avito-pf') return 'Авито ПФ';
  return order.position_name || '—';
}

const TERMINAL_STATUSES = ['done', 'failed', 'payment_failed', 'cancelled'];

// --- Avito PF specific details ---
function AvitoPFDetail({ order }) {
  const links = order.links || [];
  const m = String(order.position_name || '').match(/^(\d+)\/(\d+)$/);
  const days = m ? Number(m[1]) : null;
  const viewsPerDay = m ? Number(m[2]) : null;
  const totalViews = (viewsPerDay != null && days != null && links.length > 0)
    ? viewsPerDay * days * links.length
    : (viewsPerDay != null && days != null ? viewsPerDay * days : null);

  const params = [
    days != null && { label: 'Дней накрутки', value: `${days}` },
    viewsPerDay != null && { label: 'Просмотров в день', value: `${viewsPerDay}` },
    { label: 'Запросы контактов', value: order.contacts ? 'Да' : 'Нет' },
    links.length > 0 && { label: 'Объявлений в заказе', value: `${links.length}` },
    totalViews != null && { label: 'Всего просмотров', value: totalViews.toLocaleString('ru-RU') },
    { label: 'Цена за просмотр', value: (viewsPerDay && days && links.length)
        ? `${Math.round(order.price / totalViews)} ₽`
        : '—' },
  ].filter(Boolean);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="card" style={{ padding: '20px 24px' }}>
        <h3 style={{ marginBottom: 16, fontSize: '1rem' }}>Параметры накрутки</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16 }}>
          {params.map((p, i) => (
            <div key={i}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4, fontWeight: 600 }}>{p.label}</div>
              <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-1)' }}>{p.value}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ padding: '20px 24px' }}>
        <h3 style={{ marginBottom: 12, fontSize: '1rem' }}>
          Объявления {links.length > 0 && <span style={{ color: 'var(--text-3)', fontWeight: 500 }}>· {links.length}</span>}
        </h3>
        {links.length === 0 ? (
          <div style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>Ссылок нет</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {links.map((l, i) => (
              <a
                key={i} href={l} target="_blank" rel="noopener"
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 14px', background: 'var(--surface-2)',
                  borderRadius: 'var(--radius-sm)', fontSize: '0.875rem',
                  wordBreak: 'break-all', color: 'var(--primary)', textDecoration: 'none',
                  border: '1px solid var(--border)', gap: 12,
                }}
              >
                <span style={{ flex: 1 }}>{l.replace('https://www.avito.ru', 'avito.ru')}</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-3)', flexShrink: 0 }}>↗</span>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// --- Fallback for unknown services ---
function GenericDetail({ order }) {
  const links = order.links || [];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="card" style={{ padding: '20px 24px' }}>
        <h3 style={{ marginBottom: 12, fontSize: '1rem' }}>Параметры</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: '0.875rem', color: 'var(--text-2)' }}>
          <div><strong>Тариф:</strong> {order.position_name || '—'}</div>
          <div><strong>Контакты:</strong> {order.contacts ? 'Да' : 'Нет'}</div>
          <div><strong>Статус:</strong> {order.status}</div>
        </div>
      </div>
      {links.length > 0 && (
        <div className="card" style={{ padding: '20px 24px' }}>
          <h3 style={{ marginBottom: 12, fontSize: '1rem' }}>Ссылки · {links.length}</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {links.map((l, i) => (
              <a key={i} href={l} target="_blank" rel="noopener"
                 style={{ fontSize: '0.8125rem', wordBreak: 'break-all', color: 'var(--primary)' }}>
                {l}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Registry — add new service renderers here.
const SERVICE_DETAIL_RENDERERS = {
  'avito-pf': AvitoPFDetail,
  'generic':  GenericDetail,
};

function formatMmSs(seconds) {
  if (seconds == null || seconds < 0) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function OrderDetailPage({ order: payload, orderId: orderIdProp, user, balance, onNavigate }) {
  // Accept either { order_id, ... } payload from old callsites OR orderId prop.
  const orderId = orderIdProp != null
    ? orderIdProp
    : (payload && (payload.order_id != null ? payload.order_id : payload.increment));

  const [order, setOrder] = useODState(() => (payload && payload.status) ? payload : null);
  const [timeRemaining, setTimeRemaining] = useODState(null);
  const [loadError, setLoadError] = useODState(null);
  const [payLoading, setPayLoading] = useODState(false);
  const [payError, setPayError] = useODState('');
  const payRef = useODRef(false);
  const pollTimerRef = useODRef(null);
  const mountedRef = useODRef(true);

  // Fetch full order detail once.
  useODEffect(() => {
    if (!orderId) return;
    let cancelled = false;
    api.get(`/api/orders/pf/${orderId}`).then(data => {
      if (cancelled || !mountedRef.current) return;
      if (data && !data.__unauthorized && data.order_id) {
        setOrder(data);
      } else if (data && data.__unauthorized) {
        // Public endpoint should never 401, but guard anyway.
      } else {
        setLoadError('Не удалось загрузить заказ');
      }
    }).catch(e => {
      if (!cancelled && mountedRef.current) setLoadError(e.message || 'Не удалось загрузить заказ');
    });
    return () => { cancelled = true; };
  }, [orderId]);

  // Poll payment-status while unpaid. Stop on terminal status.
  useODEffect(() => {
    mountedRef.current = true;
    if (!orderId) return () => { mountedRef.current = false; };

    const stop = () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };

    const tick = async () => {
      try {
        const data = await api.get(`/api/orders/pf/${orderId}/payment-status`);
        if (!mountedRef.current) return;
        if (data && !data.__unauthorized) {
          if (data.time_remaining_seconds != null) {
            setTimeRemaining(data.time_remaining_seconds);
          }
          if (data.status && data.status !== (order && order.status)) {
            // Status changed → refetch full order.
            try {
              const fresh = await api.get(`/api/orders/pf/${orderId}`);
              if (mountedRef.current && fresh && !fresh.__unauthorized && fresh.order_id) {
                setOrder(fresh);
              }
            } catch (_) {}
          }
          if (data.status && data.status !== 'unpaid') {
            stop();
            return;
          }
        }
      } catch (_) {
        // Network blip — keep polling.
      }
      if (mountedRef.current) {
        pollTimerRef.current = setTimeout(tick, 5000);
      }
    };

    // Initial poll immediately so we get time_remaining_seconds right away.
    tick();

    return () => {
      mountedRef.current = false;
      stop();
    };
  }, [orderId]);

  if (!orderId) {
    return (
      <div className="page-wrap">
        <div className="container" style={{ padding: '60px 20px', textAlign: 'center' }}>
          <p style={{ color: 'var(--text-3)', marginBottom: 16 }}>Заказ не выбран.</p>
          <button className="btn btn--primary" onClick={() => onNavigate(user ? 'orders' : 'order-new')}>
            {user ? 'К списку заказов' : 'Создать заказ'}
          </button>
        </div>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="page-wrap">
        <div className="container" style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--text-3)' }}>
          {loadError ? loadError : 'Загрузка заказа...'}
        </div>
      </div>
    );
  }

  const serviceType = detectServiceType(order);
  const DetailComponent = SERVICE_DETAIL_RENDERERS[serviceType] || GenericDetail;
  const isUnpaid = order.status === 'unpaid';
  const isTerminal = TERMINAL_STATUSES.includes(order.status);
  // "Повторить заказ" доступно для любого ушедшего из unpaid статуса —
  // в работе (paid), выполнен (done), неудача, отменён и т.д.
  const canRepeat = !isUnpaid;

  const handleContactSupport = () => {
    const text = `У меня возникли проблемы с заказом #${order.order_id}`;
    window.dispatchEvent(new CustomEvent('support-chat-send', { detail: { text } }));
  };

  const handleRepeat = () => {
    try {
      const linksArr = order.links || [];
      const m = String(order.position_name || '').match(/^(\d+)\/(\d+)$/);
      const daysVal = m ? Number(m[1]) : null;
      const fixVal = m ? Number(m[2]) : 30;
      sessionStorage.setItem('order_prefill', JSON.stringify({
        links: linksArr,
        days: daysVal,
        fix_count: fixVal,
        contacts: !!order.contacts,
      }));
    } catch (_) {}
    onNavigate('order-new');
  };

  const handleBack = () => {
    if (user) onNavigate('orders');
    else onNavigate('order-new');
  };

  // Pay actions for unpaid orders. available_methods не возвращается GET /pf/{id} —
  // вычисляем здесь: yookassa всегда, balance только если залогинен и хватает денег.
  const balanceAvailable = !!user && Number(balance || 0) >= Number(order.price || 0);
  const handlePay = async (method) => {
    if (payRef.current) return;
    payRef.current = true;
    setPayLoading(true); setPayError('');
    try {
      const data = await api.post(`/api/orders/pf/${orderId}/pay`, { method });
      if (method === 'yookassa') {
        if (data && data.confirmation_url) {
          window.location.href = data.confirmation_url;
        } else {
          setPayError('Не удалось получить ссылку оплаты');
        }
      } else {
        // balance — backend перевёл в paid, перечитаем заказ.
        const fresh = await api.get(`/api/orders/pf/${orderId}`);
        if (fresh && !fresh.__unauthorized && fresh.order_id) setOrder(fresh);
      }
    } catch (e) {
      if (e.status === 400) setPayError(e.message || 'Недостаточно средств');
      else if (e.status === 409) setPayError(e.message || 'Срок оплаты истёк или статус изменён');
      else setPayError(e.message || 'Ошибка оплаты');
    } finally {
      setPayLoading(false);
      payRef.current = false;
    }
  };

  return (
    <div className="page-wrap">
      <div className="container" style={{ padding: '28px 20px 80px', maxWidth: 760 }}>
        <button className="order-back" onClick={handleBack}>
          ← {user ? 'К списку заказов' : 'К новому заказу'}
        </button>

        {/* Summary */}
        <div className="card" style={{ padding: '24px 28px', marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
            <div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-3)', marginBottom: 4, fontWeight: 600 }}>
                Заказ #{order.order_id}
              </div>
              <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: 6, letterSpacing: '-0.02em' }}>
                {serviceDisplayName(serviceType, order)}
              </h1>
              <div style={{ color: 'var(--text-3)', fontSize: '0.8125rem' }}>
                {order.date ? `Создан: ${typeof formatDisplay === 'function' ? formatDisplay(order.date) : order.date}` : ''}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <StatusBadge status={order.status} />
              <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)', marginTop: 10, letterSpacing: '-0.03em' }}>
                {Number(order.price || 0).toLocaleString('ru-RU')} ₽
              </div>
            </div>
          </div>

          {isUnpaid && timeRemaining != null && timeRemaining > 0 && (
            <div className="alert alert--info" style={{ marginBottom: 12 }}>
              ⏳ Осталось на оплату: <strong>{formatMmSs(timeRemaining)}</strong>
            </div>
          )}

          {isUnpaid && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
              {payError && <div className="alert alert--error">{payError}</div>}
              {balanceAvailable && (
                <button
                  className="btn btn--primary btn--full"
                  onClick={() => handlePay('balance')}
                  disabled={payLoading}
                >
                  {payLoading ? 'Оплачиваем...' : `Оплатить с баланса (${Number(balance).toLocaleString('ru-RU')} ₽)`}
                </button>
              )}
              <button
                className={`btn ${balanceAvailable ? 'btn--secondary' : 'btn--primary'} btn--full`}
                onClick={() => handlePay('yookassa')}
                disabled={payLoading}
              >
                {payLoading ? 'Перенаправляем...' : 'Оплатить картой (ЮKassa)'}
              </button>
            </div>
          )}

          {canRepeat && (
            <button className="btn btn--primary btn--full" onClick={handleRepeat} style={{ marginBottom: 10 }}>
              Повторить заказ
            </button>
          )}

          <button className="btn btn--secondary btn--full" onClick={handleContactSupport}>
            💬 Написать в поддержку
          </button>
        </div>

        <DetailComponent order={order} />
      </div>
    </div>
  );
}

Object.assign(window, { OrderDetailPage });
