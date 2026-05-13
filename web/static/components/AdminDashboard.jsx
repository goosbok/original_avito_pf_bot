// AdminDashboard — at-a-glance numbers, nav shortcuts.
const { useState: useAdmDState, useEffect: useAdmDEffect } = React;

function AdminDashboard({ onNavigate }) {
  const [stats, setStats] = useAdmDState(null);
  const [error, setError] = useAdmDState('');

  useAdmDEffect(() => {
    api.get('/api/admin/stats')
      .then(data => { if (!data.__unauthorized) setStats(data); })
      .catch(e => setError(e.message || 'Ошибка загрузки статистики'));
  }, []);

  const cards = stats ? [
    { label: 'Всего пользователей', value: stats.users_total,           cta: 'admin-users',   ctaLabel: 'Открыть' },
    { label: 'Регистраций сегодня', value: stats.users_registered_today, cta: 'admin-users',   ctaLabel: 'Юзеры' },
    { label: 'Заказов сегодня',     value: stats.orders_today,           cta: 'admin-orders',  ctaLabel: 'Заказы' },
    { label: 'Выручка сегодня',     value: `${stats.revenue_today.toLocaleString('ru-RU')} ₽`, cta: 'admin-orders', ctaLabel: 'Заказы' },
    { label: 'Открытых чатов',      value: stats.open_support_threads,   cta: 'admin-support', ctaLabel: 'Ответить' },
  ] : [];

  return (
    <div className="page-wrap">
      <div className="container" style={{ padding: '28px 20px 80px' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: 4 }}>Админ-дашборд</h1>
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', marginBottom: 24 }}>
          Быстрые цифры за сегодня. Кликни карточку, чтобы перейти к разделу.
        </p>

        {error && <div className="alert alert--error" style={{ marginBottom: 16 }}>{error}</div>}
        {!stats && !error && <div style={{ color: 'var(--text-3)' }}>Загрузка...</div>}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
          {cards.map((c, i) => (
            <div
              key={i}
              className="card card--hover"
              onClick={() => onNavigate(c.cta)}
              style={{ padding: '20px 22px', cursor: 'pointer' }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                {c.label}
              </div>
              <div style={{ fontSize: '1.85rem', fontWeight: 800, color: 'var(--primary)', letterSpacing: '-0.03em', marginBottom: 10 }}>
                {c.value}
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--primary)', fontWeight: 700 }}>
                {c.ctaLabel} →
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { AdminDashboard });
