// Order detail page — service-agnostic shell + per-service detail renderers.
// To add a new service: define a *Detail component and register it in
// SERVICE_DETAIL_RENDERERS by service type key returned from detectServiceType().
const { useState: useODState } = React;

function odParseLinks(s) {
  if (!s) return [];
  return String(s).split(',')
    .map(l => l.trim().replace(/^['"\[\] ]+|['"\[\] ]+$/g, ''))
    .filter(l => l.startsWith('http'));
}

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

// --- Avito PF specific details ---
function AvitoPFDetail({ order }) {
  const links = odParseLinks(order.links);
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
  const links = odParseLinks(order.links);
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

function OrderDetailPage({ order, onNavigate }) {
  if (!order) {
    return (
      <div className="page-wrap">
        <div className="container" style={{ padding: '60px 20px', textAlign: 'center' }}>
          <p style={{ color: 'var(--text-3)', marginBottom: 16 }}>Заказ не выбран.</p>
          <button className="btn btn--primary" onClick={() => onNavigate('orders')}>К списку заказов</button>
        </div>
      </div>
    );
  }

  const serviceType = detectServiceType(order);
  const DetailComponent = SERVICE_DETAIL_RENDERERS[serviceType] || GenericDetail;

  const handleContactSupport = () => {
    const text = `У меня возникли проблемы с заказом #${order.order_id}`;
    window.dispatchEvent(new CustomEvent('support-chat-send', { detail: { text } }));
  };

  return (
    <div className="page-wrap">
      <div className="container" style={{ padding: '28px 20px 80px', maxWidth: 760 }}>
        <button className="order-back" onClick={() => onNavigate('orders')}>← К списку заказов</button>

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
                {order.date ? `Создан: ${order.date}` : ''}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <StatusBadge status={order.status} />
              <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)', marginTop: 10, letterSpacing: '-0.03em' }}>
                {order.price.toLocaleString('ru-RU')} ₽
              </div>
            </div>
          </div>

          <button className="btn btn--secondary btn--full" onClick={handleContactSupport}>
            💬 Связаться с поддержкой по этому заказу
          </button>
        </div>

        <DetailComponent order={order} />
      </div>
    </div>
  );
}

Object.assign(window, { OrderDetailPage });
