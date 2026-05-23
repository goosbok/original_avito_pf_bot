// NotificationsBell — bell icon with unread badge + dropdown panel of recent notifications.
// Polls /api/notifications periodically; marks all as read when the panel opens.
// Dropdown shows up to DROPDOWN_LIMIT recent items + footer link to full notifications page.
const { useState: useBellState, useEffect: useBellEffect, useRef: useBellRef } = React;

const DROPDOWN_LIMIT = 5;

function BellIcon() {
  return (
    <svg
      className="bell__icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 8a6 6 0 0 1 12 0c0 4.5 1.2 6.2 2 7H4c.8-.8 2-2.5 2-7Z" />
      <path d="M10 19a2 2 0 0 0 4 0" />
    </svg>
  );
}

function NotificationsBell({ pollMs = 30000, onNavigate }) {
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

  const onViewAll = () => {
    setOpen(false);
    if (typeof onNavigate === 'function') onNavigate('notifications');
  };

  // formatTime — глобал из /dates.js, корректно конвертирует ISO+UTC в MSK.

  const visible = items.slice(0, DROPDOWN_LIMIT);

  return (
    <div className="bell" ref={panelRef}>
      <button className="bell__btn" onClick={onToggle} aria-label="Уведомления">
        <BellIcon />
        {unread > 0 && (
          <span className="bell__badge">{unread > 99 ? '99+' : unread}</span>
        )}
      </button>
      {open && (
        <div className="bell__panel">
          {visible.length === 0 ? (
            <div className="bell__empty">Уведомлений пока нет</div>
          ) : (
            <>
              <div className="bell__list">
                {visible.map(n => (
                  <div
                    key={n.id}
                    className={`bell__item ${n.read_at ? '' : 'bell__item--unread'}`}
                  >
                    <div className="bell__item-text">{n.text}</div>
                    <div className="bell__item-time">{formatTime(n.created_at)}</div>
                  </div>
                ))}
              </div>
              <button className="bell__footer" onClick={onViewAll}>
                Посмотреть все
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
