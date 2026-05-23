// NotificationsPage — full list view for all notifications (up to API limit of 50).
const { useState: useNotifState, useEffect: useNotifEffect } = React;

function formatNotifTime(iso) {
  if (!iso) return '';
  const s = String(iso);
  const dt = s.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if (!dt) return s;
  return `${dt[3]}.${dt[2]}.${dt[1]} ${dt[4]}:${dt[5]}`;
}

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
              <div className="notif-page__time">{formatNotifTime(n.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
