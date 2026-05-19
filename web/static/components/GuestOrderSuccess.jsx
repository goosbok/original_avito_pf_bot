// GuestOrderSuccess — polls payment status, shows order number + TP instructions
const { useState: useGOSState, useEffect: useGOSEffect, useRef: useGOSRef } = React;

const SUPPORT_LINK = 'https://t.me/avito_pf_otzizi';
const MAX_POLLS = 30;
const POLL_INTERVAL_MS = 2000;

function GuestOrderSuccess({ guestOrderId, onNavigate }) {
  const [state, setState] = useGOSState('polling'); // polling | paid | failed | timeout
  const [orderId, setOrderId] = useGOSState(null);
  const polls = useGOSRef(0);

  useGOSEffect(() => {
    if (!guestOrderId) { setState('failed'); return; }

    const timer = setInterval(async () => {
      polls.current += 1;
      if (polls.current > MAX_POLLS) {
        clearInterval(timer);
        setState('timeout');
        return;
      }
      try {
        const data = await api.get(`/api/guest-orders/${guestOrderId}/status`);
        if (data.status === 'paid') {
          clearInterval(timer);
          setOrderId(data.order_id || guestOrderId);
          setState('paid');
        } else if (data.status === 'failed') {
          clearInterval(timer);
          setState('failed');
        }
      } catch (_) {}
    }, POLL_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [guestOrderId]);

  if (state === 'polling') return (
    <div className="page-wrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div style={{ textAlign: 'center', padding: 40 }}>
        <div style={{ fontSize: '2.5rem', marginBottom: 16 }}>⏳</div>
        <h2 style={{ marginBottom: 8 }}>Проверяем оплату...</h2>
        <p style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>Это займёт несколько секунд</p>
      </div>
    </div>
  );

  if (state === 'paid') return (
    <div className="page-wrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div style={{ maxWidth: 460, padding: '0 20px', width: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>✅</div>
          <h2 style={{ marginBottom: 6 }}>Оплата прошла! Заказ принят</h2>
          <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>Спасибо, заказ передан в работу.</p>
        </div>

        <div style={{ background: 'var(--primary-dim)', borderRadius: 8, padding: '14px 18px', marginBottom: 20 }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--primary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Ваш заказ</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)' }}>#{orderId}</div>
        </div>

        <div className="card" style={{ padding: '18px 20px', marginBottom: 16 }}>
          <div style={{ fontWeight: 700, fontSize: '0.9rem', marginBottom: 14 }}>📞 Как узнать статус заказа</div>
          {[
            <React.Fragment key={0}>Напишите в <a href={SUPPORT_LINK} target="_blank" rel="noopener" style={{ color: 'var(--primary)', fontWeight: 700 }}>@avito_pf_otzizi</a></React.Fragment>,
            <React.Fragment key={1}>Назовите ваш <strong>номер телефона</strong> (и номер заказа <strong>#{orderId}</strong> — по желанию)</React.Fragment>,
            <React.Fragment key={2}>Мы найдём заказ и ответим в течение рабочего дня</React.Fragment>,
          ].map((text, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: i < 2 ? 12 : 0 }}>
              <div style={{ width: 22, height: 22, background: 'var(--primary)', color: '#fff', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontWeight: 700, flexShrink: 0, marginTop: 1 }}>{i + 1}</div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-1)', lineHeight: 1.5 }}>{text}</div>
            </div>
          ))}
        </div>

        <a href={SUPPORT_LINK} target="_blank" rel="noopener"
          style={{ display: 'block', background: 'var(--primary)', color: '#fff', textDecoration: 'none', textAlign: 'center', padding: '11px 0', borderRadius: 8, fontWeight: 600, fontSize: '0.9rem', marginBottom: 10 }}>
          Написать в поддержку
        </a>
        <div style={{ textAlign: 'center' }}>
          <span style={{ color: 'var(--primary)', fontSize: '0.875rem', cursor: 'pointer' }} onClick={() => onNavigate('landing')}>← На главную</span>
        </div>
      </div>
    </div>
  );

  // failed or timeout
  return (
    <div className="page-wrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div style={{ maxWidth: 400, padding: '0 20px', width: '100%', textAlign: 'center' }}>
        <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>❌</div>
        <h2 style={{ marginBottom: 8 }}>Оплата не прошла</h2>
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', marginBottom: 24 }}>
          Платёж был отменён или время ожидания истекло. Попробуйте ещё раз или напишите в поддержку.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button className="btn btn--primary btn--lg btn--full" onClick={() => onNavigate('guest-order-pf')}>
            Попробовать снова
          </button>
          <a href={SUPPORT_LINK} target="_blank" rel="noopener"
            style={{ display: 'block', border: '1.5px solid var(--primary)', color: 'var(--primary)', textDecoration: 'none', textAlign: 'center', padding: '11px 0', borderRadius: 8, fontWeight: 600, fontSize: '0.9rem' }}>
            Написать в поддержку
          </a>
          <span style={{ color: 'var(--primary)', fontSize: '0.875rem', cursor: 'pointer' }} onClick={() => onNavigate('landing')}>← На главную</span>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { GuestOrderSuccess });
