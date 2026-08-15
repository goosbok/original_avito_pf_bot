// NotificationsPage — full list view for all notifications (up to API limit of 50).
// Использует window.formatDisplay из /dates.js — ISO+UTC → "dd.mm.yyyy HH:MM" в MSK.
const { useState: useNotifState, useEffect: useNotifEffect } = React;

function NotificationsPage({ onNavigate }) {
  const [items, setItems] = useNotifState([]);
  const [loading, setLoading] = useNotifState(true);

  useNotifEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await api.get('/api/notifications');
        if (!alive) return;
        if (data && data.__unauthorized) return;
        setItems((data && data.items) || []);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  return (
    <main className="container" style={{ paddingTop: 24, paddingBottom: 40 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <h1 style={{ margin: 0, fontSize: '1.5rem' }}>Уведомления</h1>
        <button className="btn btn--ghost" onClick={() => onNavigate('cabinet')}>← В кабинет</button>
      </div>

      {loading ? (
        <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '40px 0' }}>Загрузка…</div>
      ) : items.length === 0 ? (
        <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '40px 0' }}>
          Уведомлений пока нет
        </div>
      ) : (
        <div className="notif-page">
          {items.map(n => (
            <div
              key={n.id}
              className={`notif-page__item ${n.read_at ? '' : 'notif-page__item--unread'}`}
            >
              <div className="notif-page__text">{n.text}</div>
              <div className="notif-page__time">{formatDisplay(n.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
