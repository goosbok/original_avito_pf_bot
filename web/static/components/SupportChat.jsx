// SupportChat — root-level floating chat widget.
// Listens for `support-chat-send` custom events from other pages so any component
// can pre-send a message and open the panel (used by OrderDetail "Связаться по заказу").
// Dedup strategy: optimistic messages carry _optimistic; on every poll, drop optimistic
// rows whose (direction, text) matches an incoming real row.
const { useState: useSCState, useEffect: useSCEffect, useRef: useSCRef } = React;

function nowHHMM() {
  return new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function SupportChat() {
  const [chatOpen, setChatOpen] = useSCState(false);
  const [messages, setMessages] = useSCState([]);
  const [input, setInput] = useSCState('');
  const [unread, setUnread] = useSCState(0);
  const [sending, setSending] = useSCState(false);
  const msgEndRef = useSCRef(null);
  const lastIdRef = useSCRef(0);
  const pollRef = useSCRef(null);
  const chatOpenRef = useSCRef(false);
  chatOpenRef.current = chatOpen;

  const mergeIncoming = (msgs) => {
    setMessages(prev => {
      const incomingIds = new Set(msgs.map(m => m.id));
      const filtered = prev.filter(m => {
        // Drop real messages already present in incoming batch (race-safe dedupe by id).
        if (!m._optimistic && incomingIds.has(m.id)) return false;
        // Drop optimistic messages whose (direction, text) matches an incoming real message.
        if (m._optimistic && msgs.some(r => r.direction === m.direction && r.text === m.text)) return false;
        return true;
      });
      return [...filtered, ...msgs];
    });
  };

  const loadMessages = async (since = 0) => {
    try {
      const msgs = await api.get('/api/support/messages?since_id=' + since);
      if (msgs.__unauthorized) return;
      if (msgs.length > 0) {
        mergeIncoming(msgs);
        lastIdRef.current = msgs[msgs.length - 1].id;
        if (!chatOpenRef.current) {
          const adminCount = msgs.filter(m => m.direction === 'admin').length;
          if (adminCount > 0) setUnread(u => u + adminCount);
        }
      }
    } catch (_) {}
  };

  useSCEffect(() => {
    loadMessages(0);
    pollRef.current = setInterval(() => loadMessages(lastIdRef.current), 3000);
    return () => clearInterval(pollRef.current);
  }, []);

  useSCEffect(() => {
    if (chatOpen) setUnread(0);
  }, [chatOpen]);

  useSCEffect(() => {
    if (msgEndRef.current) {
      msgEndRef.current.scrollTop = msgEndRef.current.scrollHeight;
    }
  }, [messages, chatOpen]);

  const sendMessageWithText = async (text) => {
    if (!text || sending) return;
    setSending(true);
    const optMsg = {
      id: `opt-${Date.now()}-${Math.random()}`,
      direction: 'user',
      text,
      created_at: nowHHMM(),
      _optimistic: true,
    };
    setMessages(m => [...m, optMsg]);
    try {
      await api.post('/api/support/messages', { text });
      const msgs = await api.get('/api/support/messages?since_id=' + lastIdRef.current);
      if (msgs && msgs.length > 0) {
        mergeIncoming(msgs);
        lastIdRef.current = msgs[msgs.length - 1].id;
      }
    } catch (_) {
      setMessages(m => m.filter(x => x.id !== optMsg.id));
    } finally {
      setSending(false);
    }
  };

  const sendMessage = () => {
    const text = input.trim();
    if (!text) return;
    setInput('');
    sendMessageWithText(text);
  };

  // External trigger: window.dispatchEvent(new CustomEvent('support-chat-send', { detail: { text } }))
  useSCEffect(() => {
    const handler = (e) => {
      const text = e?.detail?.text;
      if (!text) return;
      setChatOpen(true);
      sendMessageWithText(text);
    };
    window.addEventListener('support-chat-send', handler);
    return () => window.removeEventListener('support-chat-send', handler);
  }, []);

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
                <div className="chat-msg__time">{typeof m.created_at === 'string' ? (m.created_at.length > 5 ? m.created_at.slice(11, 16) : m.created_at) : m.created_at}</div>
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

Object.assign(window, { SupportChat });
