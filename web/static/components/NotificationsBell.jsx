// NotificationsBell — bell icon with unread badge + dropdown panel of recent notifications.
// Polls /api/notifications periodically; marks all as read when the panel opens.
const { useState: useBellState, useEffect: useBellEffect, useRef: useBellRef } = React;

function NotificationsBell({ pollMs = 30000 }) {
  const [items, setItems] = useBellState([]);
  const [unread, setUnread] = useBellState(0);
  const [open, setOpen] = useBellState(false);
  const panelRef = useBellRef(null);

  const fetchNow = async () => {
    try {
      const data = await api.get('/api/notifications');
      if (data && data.__unauthorized) return;
      setItems((data && data.items) || []);
      setUnread((data && data.unread_count) || 0);
    } catch (e) { /* swallow — bell is non-critical */ }
  };

  useBellEffect(() => {
    fetchNow();
    const t = setInterval(fetchNow, pollMs);
    return () => clearInterval(t);
  }, [pollMs]);

  // Close on outside click
  useBellEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const onToggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) {
      try {
        await api.post('/api/notifications/mark-all-read', {});
        setUnread(0);
        const nowIso = new Date().toISOString();
        setItems(items.map(i => i.read_at ? i : { ...i, read_at: nowIso }));
      } catch (e) { /* swallow */ }
    }
  };

  const formatTime = (iso) => {
    if (!iso) return '';
    const m = String(iso).match(/(\d{2}):(\d{2}):\d{2}/);
    return m ? `${m[1]}:${m[2]}` : '';
  };

  return (
    <div className="bell" ref={panelRef}>
      <button className="bell__btn" onClick={onToggle} aria-label="Уведомления">
        🔔
        {unread > 0 && (
          <span className="bell__badge">{unread > 99 ? '99+' : unread}</span>
        )}
      </button>
      {open && (
        <div className="bell__panel">
          {items.length === 0 ? (
            <div className="bell__empty">Уведомлений пока нет</div>
          ) : items.map(n => (
            <div
              key={n.id}
              className={`bell__item ${n.read_at ? '' : 'bell__item--unread'}`}
            >
              <div className="bell__item-text">{n.text}</div>
              <div className="bell__item-time">{formatTime(n.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
