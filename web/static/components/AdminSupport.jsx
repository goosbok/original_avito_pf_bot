// AdminSupport — list of user threads with unanswered badge + reply form.
const { useState: useAdmSState, useEffect: useAdmSEffect } = React;

function AdminSupport({ onNavigate }) {
  const [threads, setThreads] = useAdmSState([]);
  const [selected, setSelected] = useAdmSState(null);
  const [messages, setMessages] = useAdmSState([]);
  const [reply, setReply] = useAdmSState('');
  const [sending, setSending] = useAdmSState(false);
  const [error, setError] = useAdmSState('');

  const loadThreads = async () => {
    try {
      const data = await api.get('/api/admin/support/threads');
      if (!data.__unauthorized) setThreads(data.threads || []);
    } catch (e) { setError(e.message || 'Ошибка'); }
  };

  const loadThread = async (uid) => {
    try {
      const data = await api.get('/api/admin/support/threads/' + uid);
      if (!data.__unauthorized) setMessages(data);
    } catch (e) { setError(e.message || 'Ошибка'); }
  };

  useAdmSEffect(() => { loadThreads(); }, []);
  useAdmSEffect(() => {
    if (selected) loadThread(selected);
    else setMessages([]);
  }, [selected]);

  const send = async () => {
    if (!reply.trim() || !selected) return;
    setSending(true); setError('');
    try {
      await api.post(`/api/admin/support/threads/${selected}/reply`, { text: reply.trim() });
      setReply('');
      await loadThread(selected);
      await loadThreads();
    } catch (e) { setError(e.message || 'Не отправилось'); }
    finally { setSending(false); }
  };

  const sel = threads.find(t => t.user_id === selected);

  return (
    <div className="page-wrap">
      <div className="container" style={{ padding: '20px 20px 80px', maxWidth: 1100 }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: 16 }}>Поддержка</h1>

        {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16, alignItems: 'start' }}>
          {/* Threads list */}
          <div className="card" style={{ overflow: 'hidden', maxHeight: '70vh', overflowY: 'auto' }}>
            {threads.length === 0 && <div style={{ padding: 24, color: 'var(--text-3)' }}>Чатов нет</div>}
            {threads.map(t => (
              <div
                key={t.user_id}
                onClick={() => setSelected(t.user_id)}
                style={{
                  padding: '12px 14px',
                  borderBottom: '1px solid var(--border)',
                  cursor: 'pointer',
                  background: selected === t.user_id ? 'var(--primary-dim)' : 'transparent',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <strong style={{ fontSize: '0.875rem' }}>{t.user_name ? '@' + t.user_name : '#' + t.user_id}</strong>
                  {t.has_unanswered && <span className="badge badge--posted" style={{ fontSize: '0.65rem' }}>● новый</span>}
                </div>
                <div style={{ color: 'var(--text-2)', fontSize: '0.78rem', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {t.last_message_text}
                </div>
                <div style={{ color: 'var(--text-3)', fontSize: '0.68rem', marginTop: 4 }}>
                  {t.last_message_at ? t.last_message_at.slice(0, 16).replace('T', ' ') : ''} · {t.message_count} сообщ.
                </div>
              </div>
            ))}
          </div>

          {/* Thread view */}
          <div className="card" style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', maxHeight: '70vh' }}>
            {!selected ? (
              <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)' }}>Выберите чат слева</div>
            ) : (
              <>
                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', background: 'var(--surface-2)' }}>
                  <strong>{sel ? (sel.user_name ? '@' + sel.user_name : '#' + sel.user_id) : ''}</strong>
                  {sel && sel.first_name && <span style={{ color: 'var(--text-3)', marginLeft: 8 }}>({sel.first_name})</span>}
                </div>
                <div style={{ flex: 1, overflowY: 'auto', padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {messages.map(m => (
                    <div key={m.id} className={`chat-msg chat-msg--${m.direction}`}>
                      <div className="chat-msg__bubble">{m.text}</div>
                      <div className="chat-msg__time">{m.created_at ? m.created_at.slice(11, 16) : ''}</div>
                    </div>
                  ))}
                </div>
                <div className="chat-input-row" style={{ borderTop: '1px solid var(--border)', padding: 12 }}>
                  <input
                    className="chat-input"
                    placeholder="Ответ пользователю..."
                    value={reply}
                    onChange={e => setReply(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && send()}
                  />
                  <button className="chat-send-btn" onClick={send} disabled={sending || !reply.trim()}>➤</button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { AdminSupport });
