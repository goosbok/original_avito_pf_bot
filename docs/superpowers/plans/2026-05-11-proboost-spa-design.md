# ProBoost SPA — Full Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the multi-page static HTML web with a full React SPA implementing the ProBoost design from `/Users/belikov/Downloads/avito_pf (1)/`, wired to real backend APIs, then verify end-to-end order creation with TG admin notification.

**Architecture:** A single `index.html` bootstraps React + Babel from CDN and loads component scripts in dependency order. Each component file is `type="text/babel"` (transpiled in-browser, no build step). A shared `api.js` exposes `window.api` for authenticated HTTP calls with JWT from localStorage. The old multi-page HTML files are deleted; all routing is client-side React state.

**Tech Stack:** React 18 (CDN UMD), Babel Standalone 7 (CDN), plain fetch() for API, JWT in localStorage, FastAPI backend already running at port 8000.

**API Endpoints (all already implemented in backend):**
- `POST /api/auth/email/login` → `{access_token}`
- `POST /api/auth/email/register` → `{access_token}`
- `POST /api/auth/telegram/request-code` (204)
- `POST /api/auth/telegram/verify-code` → `{access_token}`
- `GET /api/me` → `{user_id, user_name, first_name, balance}`
- `GET /api/me/providers` → `[{provider, identifier, created_at, last_used_at}]`
- `POST /api/auth/link/email` (204) — link email to existing session
- `POST /api/auth/link/telegram/request-code` (204)
- `POST /api/auth/link/telegram/verify-code` (204)
- `GET /api/orders?page=1&page_size=20` → `{items:[{order_id,price,position_name,status,links,date,contacts}], total, page, page_size}`
- `POST /api/orders/pf` `{links:[str], days:int, fix_count:int, contacts:bool}` → `{order_id, total_price, status}`
- `GET /api/orders/pf/price` → `{price_per_unit:int}`
- `POST /api/refill` `{amount:int}` → `{payment_id, payment_url}`
- `GET /api/refill/{payment_id}/status` → `{payment_id, status:"pending"|"succeeded"|"failed"}`
- `GET /api/support/messages?since_id=0` → `[{id, direction, text, created_at}]`
- `POST /api/support/messages` `{text:str}` (204)

**Key notes:**
- `fix_count` in API = "просмотров в день" in UI; both are ≥5
- `OrderItem.links` returns comma-separated string, needs parsing to array
- `views_per_day`/`days` are NOT returned by the orders list API; show `—` in table
- JWT stored in `localStorage.getItem('access_token')`
- Auth header: `Authorization: Bearer <token>`
- The design files live at `/Users/belikov/Downloads/avito_pf (1)/`

---

## File Map

**Create:**
- `web/static/platform.css` — design tokens + component styles (copy from design)
- `web/static/tweaks-panel.jsx` — dev-mode tweaks shell (copy from design)
- `web/static/api.js` — global `window.api` HTTP client with JWT injection
- `web/static/components/AppHeader.jsx` — sticky nav (copy from design, no API)
- `web/static/components/Landing.jsx` — landing page (copy from design, no API)
- `web/static/components/Auth.jsx` — login/register/TG OTP with real API
- `web/static/components/Cabinet.jsx` — dashboard with real API (balance, orders, refill, support)
- `web/static/components/OrderForm.jsx` — PF order form with real API
- `web/static/components/Orders.jsx` — order history with real API + pagination
- `web/static/components/Profile.jsx` — provider linking with real API
- `web/static/app.jsx` — root app: session restore, routing, API integration

**Modify:**
- `web/static/index.html` — replace old simple HTML with SPA bootstrap

**Delete:**
- `web/static/login.html`
- `web/static/login_telegram.html`
- `web/static/register.html`
- `web/static/cabinet.html`
- `web/static/orders.html`
- `web/static/pf-order.html`

---

## Task 1: CSS + tweaks panel + index.html bootstrap

**Files:**
- Create: `web/static/platform.css`
- Create: `web/static/tweaks-panel.jsx`
- Modify: `web/static/index.html`

- [ ] **Step 1: Copy CSS from design**

```bash
cp "/Users/belikov/Downloads/avito_pf (1)/platform.css" \
   web/static/platform.css
```

Verify: `wc -l web/static/platform.css` → should be ~518 lines.

- [ ] **Step 2: Copy tweaks panel from design**

```bash
cp "/Users/belikov/Downloads/avito_pf (1)/tweaks-panel.jsx" \
   web/static/tweaks-panel.jsx
```

Verify: `head -5 web/static/tweaks-panel.jsx` → should show `// tweaks-panel.jsx`.

- [ ] **Step 3: Create components directory**

```bash
mkdir -p web/static/components
```

- [ ] **Step 4: Write index.html (SPA bootstrap)**

Replace `web/static/index.html` with this content:

```html
<!DOCTYPE html>
<html lang="ru" data-theme="light" data-variant="classic">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ProBoost — Платформа цифрового продвижения</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/platform.css" />
</head>
<body>
  <div id="root"></div>

  <!-- API helper (must be before Babel scripts) -->
  <script src="/api.js"></script>

  <!-- React + Babel -->
  <script src="https://unpkg.com/react@18.3.1/umd/react.development.js" integrity="sha384-hD6/rw4ppMLGNu3tX5cjIb+uRZ7UkRJ6BPkLpg4hAu/6onKUg4lLsHAs9EBPT82L" crossorigin="anonymous"></script>
  <script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js" integrity="sha384-u6aeetuaXnQ38mYT8rp6sbXaQe3NL9t+IBXmnYxwkUI2Hw4bsp2Wvmx4yRQF1uAm" crossorigin="anonymous"></script>
  <script src="https://unpkg.com/@babel/standalone@7.29.0/babel.min.js" integrity="sha384-m08KidiNqLdpJqLq95G/LEi8Qvjl/xUYll3QILypMoQ65QorJ9Lvtp2RXYGBFj1y" crossorigin="anonymous"></script>

  <!-- Shared helpers (loads first — defines TweaksPanel, etc.) -->
  <script type="text/babel" src="/tweaks-panel.jsx"></script>

  <!-- Components (dependency order — imported by app.jsx) -->
  <script type="text/babel" src="/components/AppHeader.jsx"></script>
  <script type="text/babel" src="/components/Landing.jsx"></script>
  <script type="text/babel" src="/components/Auth.jsx"></script>
  <script type="text/babel" src="/components/Cabinet.jsx"></script>
  <script type="text/babel" src="/components/OrderForm.jsx"></script>
  <script type="text/babel" src="/components/Orders.jsx"></script>
  <script type="text/babel" src="/components/Profile.jsx"></script>

  <!-- Root app (last — uses all components) -->
  <script type="text/babel" src="/app.jsx"></script>
</body>
</html>
```

- [ ] **Step 5: Commit**

```bash
git add web/static/platform.css web/static/tweaks-panel.jsx \
        web/static/index.html web/static/components/
git commit -m "feat: SPA scaffold — CSS, tweaks panel, index.html bootstrap"
```

---

## Task 2: AppHeader and Landing (pure UI, no API)

**Files:**
- Create: `web/static/components/AppHeader.jsx`
- Create: `web/static/components/Landing.jsx`

- [ ] **Step 1: Copy AppHeader from design**

```bash
cp "/Users/belikov/Downloads/avito_pf (1)/components/AppHeader.jsx" \
   web/static/components/AppHeader.jsx
```

No changes needed — the component uses only props (route, user, balance, brandName, theme, callbacks). Verify last line: `Object.assign(window, { AppHeader });`

- [ ] **Step 2: Copy Landing from design**

```bash
cp "/Users/belikov/Downloads/avito_pf (1)/components/Landing.jsx" \
   web/static/components/Landing.jsx
```

No changes needed. Verify last line: `Object.assign(window, { LandingPage });`

- [ ] **Step 3: Commit**

```bash
git add web/static/components/AppHeader.jsx \
        web/static/components/Landing.jsx
git commit -m "feat: add AppHeader and Landing components (design copy)"
```

---

## Task 3: api.js — shared HTTP client

**Files:**
- Create: `web/static/api.js`

- [ ] **Step 1: Write api.js**

Create `web/static/api.js` with this exact content:

```javascript
// Global HTTP client — injected before React components load.
// Uses JWT from localStorage. Exposes window.api for all components.
window.api = {
  _token() { return localStorage.getItem('access_token'); },

  async get(path) {
    const token = this._token();
    const res = await fetch(path, {
      headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    });
    if (res.status === 401) return { __unauthorized: true };
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const e = new Error(err.detail || 'Request failed');
      e.status = res.status;
      throw e;
    }
    return res.json();
  },

  async post(path, body) {
    const token = this._token();
    const res = await fetch(path, {
      method: 'POST',
      headers: Object.assign(
        { 'Content-Type': 'application/json' },
        token ? { 'Authorization': 'Bearer ' + token } : {}
      ),
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const e = new Error(err.detail || 'Request failed');
      e.status = res.status;
      throw e;
    }
    if (res.status === 204) return null;
    return res.json();
  }
};
```

- [ ] **Step 2: Commit**

```bash
git add web/static/api.js
git commit -m "feat: add api.js — global JWT-aware HTTP client"
```

---

## Task 4: Auth.jsx — login / register / TG OTP with real API

**Files:**
- Create: `web/static/components/Auth.jsx`

The design's Auth.jsx uses mock `simulate()`. Replace with real `api.post()` calls.
`onLogin` now receives a JWT token string (not a user object) — `app.jsx` will fetch /api/me after receiving it.

- [ ] **Step 1: Write Auth.jsx**

Create `web/static/components/Auth.jsx`:

```jsx
// Auth screens: Email login, Telegram OTP login, Email register
const { useState } = React;

const AuthPage = ({ mode: initialMode, onLogin, onNavigate }) => {
  const [mode, setMode] = useState(initialMode || 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [tgId, setTgId] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleEmailLogin = async () => {
    if (!email || !password) return setError('Заполните все поля');
    setLoading(true); setError('');
    try {
      const data = await api.post('/api/auth/email/login', { email, password });
      onLogin(data.access_token);
    } catch (e) {
      setError(e.status === 401 ? 'Неверный email или пароль' : (e.message || 'Ошибка входа'));
    } finally { setLoading(false); }
  };

  const handleRegister = async () => {
    if (!email || !password) return setError('Заполните все поля');
    if (password.length < 8) return setError('Пароль — минимум 8 символов');
    setLoading(true); setError('');
    try {
      const data = await api.post('/api/auth/email/register', {
        email, password, first_name: name || null
      });
      onLogin(data.access_token);
    } catch (e) {
      if (e.status === 409) setError('Email уже зарегистрирован');
      else setError(e.message || 'Ошибка регистрации');
    } finally { setLoading(false); }
  };

  const handleRequestOtp = async () => {
    if (!tgId) return setError('Введите username или телефон');
    setLoading(true); setError(''); setSuccess('');
    try {
      await api.post('/api/auth/telegram/request-code', { identifier: tgId });
      setOtpSent(true);
      setSuccess('Код отправлен в Telegram');
    } catch (e) {
      if (e.status === 429) setError('Подождите перед повторной отправкой');
      else if (e.status === 400) setError(e.message || 'Пользователь не найден в Telegram');
      else setError(e.message || 'Ошибка отправки кода');
    } finally { setLoading(false); }
  };

  const handleVerifyOtp = async () => {
    if (!otpCode || otpCode.length < 6) return setError('Введите 6-значный код');
    setLoading(true); setError('');
    try {
      const data = await api.post('/api/auth/telegram/verify-code', {
        identifier: tgId, code: otpCode
      });
      onLogin(data.access_token);
    } catch (e) {
      if (e.status === 410) setError('Код истёк — запросите новый');
      else if (e.status === 401) setError('Неверный код');
      else setError(e.message || 'Ошибка проверки кода');
    } finally { setLoading(false); }
  };

  const logoMark = (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <div style={{
        width: 48, height: 48, borderRadius: 14, background: 'var(--primary)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '1rem', fontWeight: 900, color: '#fff'
      }}>PB</div>
    </div>
  );

  if (mode === 'login-tg') return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Вход через Telegram</h2>
        <p className="auth-card__sub">Введите username или номер телефона — мы отправим код</p>
        <div className="auth-form">
          {error && <div className="alert alert--error">{error}</div>}
          {success && <div className="alert alert--success">{success}</div>}
          {!otpSent ? (
            <>
              <div className="form-field">
                <label className="form-label">Username или телефон</label>
                <input
                  className="input"
                  placeholder="@username или +79001234567"
                  value={tgId}
                  onChange={e => setTgId(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleRequestOtp()}
                />
              </div>
              <button className="btn btn--primary btn--lg btn--full" onClick={handleRequestOtp} disabled={loading}>
                {loading ? 'Отправка...' : 'Получить код в Telegram'}
              </button>
            </>
          ) : (
            <>
              <div className="form-field">
                <label className="form-label">6-значный код из Telegram</label>
                <input
                  className="input"
                  placeholder="123456"
                  value={otpCode}
                  maxLength={6}
                  onChange={e => setOtpCode(e.target.value.replace(/\D/g, ''))}
                  onKeyDown={e => e.key === 'Enter' && handleVerifyOtp()}
                  style={{ textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.2em', fontWeight: 700 }}
                  autoFocus
                />
                <div className="form-hint">Код действителен 10 минут</div>
              </div>
              <button className="btn btn--primary btn--lg btn--full" onClick={handleVerifyOtp} disabled={loading}>
                {loading ? 'Проверка...' : 'Войти →'}
              </button>
              <button className="btn btn--ghost btn--sm btn--full" onClick={() => { setOtpSent(false); setOtpCode(''); setSuccess(''); }}>
                ← Изменить username
              </button>
            </>
          )}
        </div>
        <div className="auth-links">
          <span onClick={() => setMode('login')} style={{ cursor: 'pointer', color: 'var(--primary)', fontWeight: 600 }}>
            Войти через Email
          </span>
          {' · '}
          <span onClick={() => onNavigate('landing')} style={{ cursor: 'pointer' }}>На главную</span>
        </div>
      </div>
    </div>
  );

  if (mode === 'register') return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Создать аккаунт</h2>
        <p className="auth-card__sub">Email + пароль. Позже можно привязать Telegram.</p>
        <div className="auth-form">
          {error && <div className="alert alert--error">{error}</div>}
          <div className="form-field">
            <label className="form-label">Имя (необязательно)</label>
            <input className="input" placeholder="Алексей" value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-label">Email</label>
            <input className="input" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-label">Пароль</label>
            <input
              className="input" type="password" placeholder="Минимум 8 символов"
              value={password} onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleRegister()}
            />
            <div className="form-hint">Минимум 8 символов</div>
          </div>
          <button className="btn btn--primary btn--lg btn--full" onClick={handleRegister} disabled={loading}>
            {loading ? 'Создание аккаунта...' : 'Создать аккаунт →'}
          </button>
          <div className="auth-divider"><span>или</span></div>
          <button className="btn btn--ghost btn--full" onClick={() => setMode('login-tg')}>
            Войти через Telegram
          </button>
        </div>
        <div className="auth-links">
          Уже есть аккаунт?{' '}
          <span onClick={() => setMode('login')} style={{ color: 'var(--primary)', fontWeight: 600, cursor: 'pointer' }}>Войти</span>
        </div>
      </div>
    </div>
  );

  // Default: Email login
  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="auth-card__logo">{logoMark}</div>
        <h2 className="auth-card__title">Добро пожаловать</h2>
        <p className="auth-card__sub">Войдите в личный кабинет</p>
        <div className="auth-form">
          {error && <div className="alert alert--error">{error}</div>}
          <button className="btn btn--secondary btn--lg btn--full" onClick={() => setMode('login-tg')}>
            Войти через Telegram
          </button>
          <div className="auth-divider"><span>или через email</span></div>
          <div className="form-field">
            <label className="form-label">Email</label>
            <input className="input" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-label">Пароль</label>
            <input
              className="input" type="password" placeholder="Ваш пароль"
              value={password} onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleEmailLogin()}
            />
          </div>
          <button className="btn btn--primary btn--lg btn--full" onClick={handleEmailLogin} disabled={loading}>
            {loading ? 'Вход...' : 'Войти →'}
          </button>
        </div>
        <div className="auth-links">
          Нет аккаунта?{' '}
          <span onClick={() => setMode('register')} style={{ color: 'var(--primary)', fontWeight: 600, cursor: 'pointer' }}>Зарегистрироваться</span>
          {' · '}
          <span onClick={() => onNavigate('landing')} style={{ cursor: 'pointer' }}>На главную</span>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { AuthPage });
```

- [ ] **Step 2: Commit**

```bash
git add web/static/components/Auth.jsx
git commit -m "feat: Auth — real API login/register/TG OTP"
```

---

## Task 5: Cabinet.jsx — dashboard with real API

**Files:**
- Create: `web/static/components/Cabinet.jsx`

Key differences from design mock:
- On mount: fetch `/api/orders?page=1&page_size=5` for recent orders
- Refill: POST `/api/refill` → open payment_url in new tab, poll `/api/refill/{id}/status`
- Support chat: real `GET /POST /api/support/messages` with 3s polling

- [ ] **Step 1: Write Cabinet.jsx**

Create `web/static/components/Cabinet.jsx`:

```jsx
// Cabinet — dashboard: balance, catalog, orders, refill, support chat
const { useState: useCabinetState, useEffect: useCabinetEffect, useRef: useCabinetRef } = React;

const SERVICES = [
  { id: 'pf',      abbr: 'ПФ',  name: 'Авито ПФ',    desc: 'Просмотры, лайки, контакты для объявлений', price: 'от 6 ₽/ПФ', available: true,  route: 'order-pf' },
  { id: 'reviews', abbr: 'ОТЗ', name: 'Отзывы',       desc: 'Накрутка / удаление: Авито, ВК, Яндекс, 2ГИС, Google', price: 'по тарифу', available: true,  route: null },
  { id: 'ypf',     abbr: 'ЯПФ', name: 'Яндекс ПФ',   desc: 'Поведенческие факторы для Яндекс', price: null, badge: 'В разработке', available: false, route: null },
  { id: 'seo',     abbr: 'SEO', name: 'SEO-буст',     desc: 'Ссылочное продвижение и рост позиций', price: null, badge: 'Скоро', available: false, route: null },
  { id: 'copy',    abbr: 'КП',  name: 'Копирайтинг', desc: 'Тексты для объявлений и карточек', price: null, badge: 'Скоро', available: false, route: null },
  { id: 'smm',     abbr: 'SMM', name: 'SMM',          desc: 'Ведение соцсетей и создание контента', price: null, badge: 'Скоро', available: false, route: null },
];

const PRESETS = [500, 1000, 2000, 5000];

function StatusBadge({ status }) {
  const map = { Posted: 'posted', Completed: 'completed', Cancelled: 'cancelled', Pending: 'pending' };
  const labels = { Posted: 'В работе', Completed: 'Завершён', Cancelled: 'Отменён', Pending: 'Ожидание' };
  return <span className={`badge badge--${map[status] || 'muted'}`}>{labels[status] || status}</span>;
}

function SupportChat({ chatOpen, setChatOpen }) {
  const [messages, setMessages] = useCabinetState([]);
  const [input, setInput] = useCabinetState('');
  const [unread, setUnread] = useCabinetState(0);
  const [sending, setSending] = useCabinetState(false);
  const msgEndRef = useCabinetRef(null);
  const lastIdRef = useCabinetRef(0);
  const pollRef = useCabinetRef(null);

  const loadMessages = async (since = 0) => {
    try {
      const msgs = await api.get('/api/support/messages?since_id=' + since);
      if (msgs.__unauthorized) return;
      if (msgs.length > 0) {
        setMessages(prev => [...prev, ...msgs]);
        lastIdRef.current = msgs[msgs.length - 1].id;
        if (!chatOpen) setUnread(u => u + msgs.filter(m => m.direction === 'admin').length);
      }
    } catch (_) {}
  };

  useCabinetEffect(() => {
    loadMessages(0);
    pollRef.current = setInterval(() => loadMessages(lastIdRef.current), 3000);
    return () => clearInterval(pollRef.current);
  }, []);

  useCabinetEffect(() => {
    if (chatOpen) setUnread(0);
  }, [chatOpen]);

  useCabinetEffect(() => {
    if (msgEndRef.current) {
      msgEndRef.current.scrollTop = msgEndRef.current.scrollHeight;
    }
  }, [messages, chatOpen]);

  const sendMessage = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput('');
    setSending(true);
    const optimistic = {
      id: Date.now(),
      direction: 'user',
      text,
      created_at: new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    };
    setMessages(m => [...m, optimistic]);
    try {
      await api.post('/api/support/messages', { text });
    } catch (_) {}
    setSending(false);
  };

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
                <div className="chat-msg__time">{typeof m.created_at === 'string' ? m.created_at.slice(11, 16) : m.created_at}</div>
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

function CabinetPage({ user, balance, setBalance, refreshBalance, onNavigate }) {
  const [recentOrders, setRecentOrders] = useCabinetState([]);
  const [refillAmount, setRefillAmount] = useCabinetState(1000);
  const [refillStatus, setRefillStatus] = useCabinetState(null); // null | 'pending' | 'polling' | 'success' | 'error'
  const [refillPaymentId, setRefillPaymentId] = useCabinetState(null);
  const [chatOpen, setChatOpen] = useCabinetState(false);

  useCabinetEffect(() => {
    api.get('/api/orders?page=1&page_size=5').then(data => {
      if (!data.__unauthorized) setRecentOrders(data.items || []);
    }).catch(() => {});
  }, []);

  const handleRefill = async () => {
    if (!refillAmount || refillAmount < 100) return;
    setRefillStatus('pending');
    try {
      const data = await api.post('/api/refill', { amount: Number(refillAmount) });
      setRefillPaymentId(data.payment_id);
      window.open(data.payment_url, '_blank');
      setRefillStatus('polling');
    } catch (e) {
      setRefillStatus('error');
    }
  };

  const checkRefillStatus = async () => {
    if (!refillPaymentId) return;
    try {
      const data = await api.get(`/api/refill/${refillPaymentId}/status`);
      if (data.status === 'succeeded') {
        setRefillStatus('success');
        refreshBalance();
        setTimeout(() => { setRefillStatus(null); setRefillPaymentId(null); }, 4000);
      } else if (data.status === 'failed') {
        setRefillStatus('error');
      }
    } catch (_) {}
  };

  const handleServiceClick = (service) => {
    if (!service.available) return;
    if (service.route) onNavigate(service.route);
    else alert(`Услуга "${service.name}" — оформление через менеджера в Telegram`);
  };

  return (
    <div className="page-wrap">
      <div className="cabinet">
        <div className="container">

          {/* Welcome strip + Balance widget */}
          <div className="cabinet-top-row" style={{
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
            gap: 16, flexWrap: 'wrap', marginBottom: 28
          }}>
            <div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: 4 }}>
                Привет, {user.first_name}
              </h2>
              <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>
                Личный кабинет · Управляйте заказами и балансом
              </p>
            </div>

            {/* Balance card */}
            <div className="card cabinet-balance-card" style={{ padding: '16px 20px', minWidth: 260, flex: '0 0 auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Баланс</span>
                <span style={{ fontSize: '1.375rem', fontWeight: 800, color: 'var(--primary)' }}>{balance.toLocaleString('ru-RU')} ₽</span>
              </div>
              <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                {PRESETS.slice(0, 3).map(p => (
                  <button
                    key={p}
                    className={`balance-preset${refillAmount === p ? ' active' : ''}`}
                    style={{ flex: 1, fontSize: '0.75rem', padding: '5px 4px' }}
                    onClick={() => setRefillAmount(p)}
                  >
                    {p.toLocaleString('ru-RU')} ₽
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="input"
                  type="number"
                  min={100}
                  value={refillAmount}
                  onChange={e => setRefillAmount(Number(e.target.value))}
                  placeholder="Сумма"
                  style={{ flex: 1, padding: '8px 10px', fontSize: '0.875rem' }}
                />
                <button
                  className="btn btn--primary btn--sm"
                  onClick={handleRefill}
                  disabled={refillStatus === 'pending' || refillStatus === 'polling' || !refillAmount || refillAmount < 100}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  {refillStatus === 'pending' ? '...' : 'Пополнить'}
                </button>
              </div>
              {refillStatus === 'polling' && (
                <div className="balance-status balance-status--pending" style={{ marginTop: 8, padding: '8px 12px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>⏳ Ожидаем оплаты</span>
                  <button
                    className="btn btn--ghost btn--sm"
                    onClick={checkRefillStatus}
                    style={{ fontSize: '0.75rem', padding: '3px 8px' }}
                  >Проверить</button>
                </div>
              )}
              {refillStatus === 'success' && (
                <div className="balance-status balance-status--success" style={{ marginTop: 8, padding: '8px 12px', fontSize: '0.8rem' }}>
                  ✅ {refillAmount.toLocaleString('ru-RU')} ₽ зачислено!
                </div>
              )}
              {refillStatus === 'error' && (
                <div className="balance-status" style={{ marginTop: 8, padding: '8px 12px', fontSize: '0.8rem', background: 'var(--status-cancel-bg)', color: 'var(--status-cancel-text)' }}>
                  ❌ Ошибка оплаты. Попробуйте снова.
                </div>
              )}
            </div>
          </div>

          {/* Catalog */}
          <div className="cabinet__section">
            <div className="section-header">
              <span className="section-title">Услуги</span>
            </div>
            <div className="catalog-grid">
              {SERVICES.map(s => (
                <div
                  key={s.id}
                  className={`card service-card card--hover${!s.available ? ' service-card--disabled' : ''}`}
                  onClick={() => handleServiceClick(s)}
                  style={{ cursor: s.available ? 'pointer' : 'default' }}
                >
                  <div style={{ width: 38, height: 38, borderRadius: 8, background: s.available ? 'var(--primary-dim)' : 'var(--surface-3)', color: s.available ? 'var(--primary)' : 'var(--text-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontWeight: 800, letterSpacing: '-0.01em' }}>{s.abbr}</div>
                  <div className="service-card__name">{s.name}</div>
                  <div className="service-card__desc">{s.desc}</div>
                  <div className="service-card__footer">
                    {s.available
                      ? <span className="service-card__price">{s.price}</span>
                      : <span className="badge badge--muted" style={{ fontSize: '0.7rem' }}>{s.badge}</span>
                    }
                    {s.available && <span style={{ fontSize: '0.75rem', color: 'var(--primary)', fontWeight: 700 }}>Заказать →</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Recent orders */}
          <div className="cabinet__section">
            <div className="section-header">
              <span className="section-title">Последние заказы</span>
              <button className="btn btn--ghost btn--sm" onClick={() => onNavigate('orders')}>
                Все заказы →
              </button>
            </div>
            <div className="card" style={{ overflow: 'hidden' }}>
              {recentOrders.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state__icon">📭</div>
                  <div className="empty-state__title">Заказов ещё нет</div>
                  <div className="empty-state__desc">Выберите услугу из каталога выше</div>
                </div>
              ) : (
                <>
                  <div className="desktop-only">
                    <table className="orders-table">
                      <thead>
                        <tr>
                          <th>#</th><th>Услуга</th><th>Сумма</th><th>Статус</th><th>Дата</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recentOrders.map(o => (
                          <tr key={o.order_id}>
                            <td style={{ color: 'var(--text-3)', fontWeight: 600 }}>#{o.order_id}</td>
                            <td style={{ fontWeight: 600 }}>{o.position_name}</td>
                            <td style={{ fontWeight: 700 }}>{o.price.toLocaleString('ru-RU')} ₽</td>
                            <td><StatusBadge status={o.status} /></td>
                            <td style={{ color: 'var(--text-3)' }}>{o.date ? new Date(o.date).toLocaleDateString('ru-RU') : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mobile-only">
                    {recentOrders.map(o => (
                      <div key={o.order_id} className="order-card-mobile">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{o.position_name}</div>
                            <div style={{ color: 'var(--text-3)', fontSize: '0.75rem', marginTop: 2 }}>#{o.order_id} · {o.date ? new Date(o.date).toLocaleDateString('ru-RU') : '—'}</div>
                          </div>
                          <StatusBadge status={o.status} />
                        </div>
                        <div style={{ fontWeight: 700, color: 'var(--primary)' }}>{o.price.toLocaleString('ru-RU')} ₽</div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

        </div>
      </div>

      <SupportChat chatOpen={chatOpen} setChatOpen={setChatOpen} />
    </div>
  );
}

Object.assign(window, { CabinetPage, StatusBadge });
```

- [ ] **Step 2: Commit**

```bash
git add web/static/components/Cabinet.jsx
git commit -m "feat: Cabinet — real API (orders, refill redirect, support chat)"
```

---

## Task 6: OrderForm.jsx — PF order with real API

**Files:**
- Create: `web/static/components/OrderForm.jsx`

Key differences from design:
- On mount: GET `/api/orders/pf/price` → set `pricePerUnit` state
- On submit: POST `/api/orders/pf` with `{links: urlList, days, fix_count: views, contacts}`
- `onOrderPlaced(totalPrice)` — tells app.jsx to subtract from balance
- Price formula: `views * days * max(urlCount,1) * pricePerUnit`
- The slider label "Просмотров в день" maps to `fix_count` in the API (both ≥5)

- [ ] **Step 1: Write OrderForm.jsx**

Create `web/static/components/OrderForm.jsx`:

```jsx
// PF Order Form — two-column layout with real API
const { useState: useOrderState, useEffect: useOrderEffect } = React;

function parseUrls(text) {
  if (!text) return [];
  return text.split(/(?=https:\/\/)/g).map(u => u.trim()).filter(u => u.startsWith('https://'));
}

function SliderField({ label, min, max, step, value, onChange, suffix = '', hint }) {
  return (
    <div className="form-field">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <label className="form-label" style={{ margin: 0 }}>{label}</label>
        <span style={{ fontWeight: 800, color: 'var(--primary)', fontSize: '1.05rem', letterSpacing: '-0.02em' }}>{value}{suffix}</span>
      </div>
      <div className="slider-row">
        <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(Number(e.target.value))} />
        <input
          type="number" className="slider-num" min={min} max={max} step={step} value={value}
          onChange={e => { let v = Number(e.target.value); if (v < min) v = min; if (v > max) v = max; onChange(v); }}
        />
      </div>
      <div className="slider-labels"><span>{min}{suffix}</span><span>{max}{suffix}</span></div>
      {hint && <div className="form-hint" style={{ marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function OrderFormPage({ balance, onNavigate, onOrderPlaced }) {
  const [urls, setUrls] = useOrderState('');
  const [views, setViews] = useOrderState(30);  // maps to fix_count in API
  const [days, setDays] = useOrderState(7);
  const [contacts, setContacts] = useOrderState(false);
  const [startDate, setStartDate] = useOrderState(() => {
    const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().split('T')[0];
  });
  const [pricePerUnit, setPricePerUnit] = useOrderState(6);
  const [loading, setLoading] = useOrderState(false);
  const [error, setError] = useOrderState('');
  const [submitted, setSubmitted] = useOrderState(false);
  const [submittedPrice, setSubmittedPrice] = useOrderState(0);

  useOrderEffect(() => {
    api.get('/api/orders/pf/price').then(data => {
      if (!data.__unauthorized) setPricePerUnit(data.price_per_unit || 6);
    }).catch(() => {});
  }, []);

  const urlList = parseUrls(urls);
  const urlCount = urlList.length;
  const totalPrice = views * days * Math.max(urlCount, 1) * pricePerUnit;

  const handleSubmit = async () => {
    if (urlCount === 0) return setError('Вставьте хотя бы одну ссылку на объявление');
    if (totalPrice > balance) return setError(`Недостаточно средств. Нужно ${totalPrice.toLocaleString('ru-RU')} ₽, на балансе ${balance.toLocaleString('ru-RU')} ₽`);
    setError(''); setLoading(true);
    try {
      await api.post('/api/orders/pf', {
        links: urlList,
        days,
        fix_count: views,
        contacts
      });
      setSubmittedPrice(totalPrice);
      setSubmitted(true);
      onOrderPlaced && onOrderPlaced(totalPrice);
      setTimeout(() => onNavigate('cabinet'), 2200);
    } catch (e) {
      if (e.status === 402) setError(e.message || 'Недостаточно средств');
      else setError(e.message || 'Ошибка создания заказа');
    } finally { setLoading(false); }
  };

  if (submitted) return (
    <div className="page-wrap" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div style={{ textAlign: 'center', padding: 40, maxWidth: 400 }}>
        <div style={{ fontSize: '3rem', marginBottom: 16 }}>✅</div>
        <h2 style={{ marginBottom: 8 }}>Заказ принят!</h2>
        <p style={{ color: 'var(--text-2)', marginBottom: 6 }}>Списано <strong style={{ color: 'var(--primary)' }}>{submittedPrice.toLocaleString('ru-RU')} ₽</strong></p>
        <p style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>Возвращаем в кабинет...</p>
      </div>
    </div>
  );

  return (
    <div className="page-wrap">
      <div className="order-page">
        <div className="container" style={{ maxWidth: 900 }}>

          <button className="order-back" onClick={() => onNavigate('cabinet')}>← Назад в кабинет</button>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>Авито ПФ</h1>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-3)' }}>
              Поведенческие факторы · {pricePerUnit} ₽ за просмотр
            </span>
          </div>

          {error && <div className="alert alert--error" style={{ marginBottom: 16 }}>{error}</div>}

          <div className="order-two-col" style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, alignItems: 'start' }}>

            {/* LEFT */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="card" style={{ padding: '14px 18px', borderLeft: '3px solid var(--primary)' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 700, marginBottom: 5, color: 'var(--text-1)' }}>Рекомендация</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-2)', lineHeight: 1.65 }}>
                  Начните с <strong>15–30 просм./день без контактов</strong> в течение недели.
                  После оживления органики постепенно добавляйте 5–8 контактов.
                  Резкий рост контактов может временно снизить позиции.
                </div>
              </div>

              <div className="card" style={{ padding: '18px 20px' }}>
                <div className="form-field">
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
                    <label className="form-label" style={{ margin: 0, fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-1)' }}>
                      Ссылки на объявления
                    </label>
                    {urlCount > 0 && (
                      <span className="badge badge--new">✓ {urlCount} {urlCount === 1 ? 'объявление' : urlCount < 5 ? 'объявления' : 'объявлений'}</span>
                    )}
                  </div>
                  <textarea
                    className="textarea input-mono"
                    rows={8}
                    placeholder={"https://www.avito.ru/moskva/uslugi/...\nhttps://www.avito.ru/spb/uslugi/...\n\nВставьте ссылки построчно или через пробел —\nкаждый https:// распознаётся как отдельное объявление"}
                    value={urls}
                    onChange={e => setUrls(e.target.value)}
                    style={{ minHeight: 180 }}
                  />
                  {urlCount === 0 && urls.length > 5 && (
                    <div style={{ fontSize: '0.8rem', color: 'var(--status-cancel-text)', marginTop: 6 }}>
                      ⚠ Ссылки должны начинаться с https://
                    </div>
                  )}
                  <div className="form-hint" style={{ marginTop: 6 }}>
                    Каждый https:// — отдельное объявление. Цена умножается на количество.
                  </div>
                </div>
              </div>
            </div>

            {/* RIGHT */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="card" style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>
                <SliderField
                  label="Просмотров в день"
                  min={5} max={500} step={5}
                  value={views} onChange={setViews}
                  hint="Рекомендуем 15–50 для начала"
                />
                <div style={{ height: 1, background: 'var(--border)' }} />
                <SliderField
                  label="Количество дней"
                  min={1} max={30} step={1}
                  value={days} onChange={setDays} suffix=" дн."
                  hint="Лучше крутить непрерывно от 7 дней"
                />
                <div style={{ height: 1, background: 'var(--border)' }} />
                <div className="form-field">
                  <label className="form-label">Дата начала</label>
                  <input
                    type="date" className="input"
                    value={startDate}
                    min={new Date().toISOString().split('T')[0]}
                    onChange={e => setStartDate(e.target.value)}
                  />
                  <div className="form-hint">Запуск на следующий день или до 04:00 МСК — сегодня</div>
                </div>
                <div style={{ height: 1, background: 'var(--border)' }} />
                <div className="toggle-row" onClick={() => setContacts(v => !v)} style={{ userSelect: 'none', cursor: 'pointer' }}>
                  <div className={`toggle${contacts ? ' on' : ''}`} />
                  <div>
                    <div className="toggle-label" style={{ fontSize: '0.875rem' }}>Запросы контактов</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginTop: 2 }}>Включать постепенно</div>
                  </div>
                </div>
              </div>

              {/* Price preview */}
              <div style={{ background: 'var(--surface)', border: '1.5px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                <div style={{ background: 'var(--primary-dim)', borderBottom: '1px solid rgba(0,136,204,0.15)', padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Стоимость заказа</span>
                  <span style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)', letterSpacing: '-0.03em' }}>{totalPrice.toLocaleString('ru-RU')} ₽</span>
                </div>
                <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {[
                    { label: 'Просмотров в день', val: views },
                    { label: 'Количество дней',   val: days },
                    { label: 'Объявлений',         val: Math.max(urlCount, 1) },
                    { label: 'Цена за просмотр',  val: `${pricePerUnit} ₽` },
                  ].map((row, i, arr) => (
                    <div key={i}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.8125rem', color: 'var(--text-2)' }}>{row.label}</span>
                        <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-1)' }}>× {row.val}</span>
                      </div>
                      {i < arr.length - 1 && <div style={{ height: 1, background: 'var(--border)', marginTop: 8 }} />}
                    </div>
                  ))}
                </div>
                <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: totalPrice > balance ? 'rgba(220,53,69,0.05)' : 'var(--surface-2)' }}>
                  <span style={{ fontSize: '0.8rem', color: totalPrice > balance ? 'var(--status-cancel-text)' : 'var(--text-3)' }}>
                    {totalPrice > balance ? '⚠ Недостаточно средств' : 'Остаток на балансе'}
                  </span>
                  <span style={{ fontSize: '0.875rem', fontWeight: 700, color: totalPrice > balance ? 'var(--status-cancel-text)' : 'var(--text-2)' }}>
                    {Math.max(0, balance - totalPrice).toLocaleString('ru-RU')} ₽
                  </span>
                </div>
              </div>

              <button
                className="btn btn--primary btn--lg btn--full desktop-only"
                onClick={handleSubmit}
                disabled={loading || urlCount === 0}
                style={{ fontSize: '0.9375rem' }}
              >
                {loading ? 'Размещаем заказ...' : 'Разместить заказ'}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile sticky footer */}
        <div className="order-sticky-footer">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-2)' }}>Итого:</span>
            <span style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--primary)' }}>{totalPrice.toLocaleString('ru-RU')} ₽</span>
          </div>
          <button className="btn btn--primary btn--lg btn--full" onClick={handleSubmit} disabled={loading || urlCount === 0}>
            {loading ? 'Размещаем...' : 'Разместить заказ'}
          </button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { OrderFormPage, SliderField });
```

- [ ] **Step 2: Commit**

```bash
git add web/static/components/OrderForm.jsx
git commit -m "feat: OrderForm — real API (price fetch, PF order creation)"
```

---

## Task 7: Orders.jsx — history with real API + pagination

**Files:**
- Create: `web/static/components/Orders.jsx`

Note: API returns `links` as a comma-separated string. `views_per_day` and `days` are not in the API response — show `—` for the Параметры column.

- [ ] **Step 1: Write Orders.jsx**

Create `web/static/components/Orders.jsx`:

```jsx
// Orders history page with real API + client-side filter + server-side pagination
const { useState: useOrdersState, useEffect: useOrdersEffect } = React;

const STATUS_FILTERS = [
  { key: 'all',       label: 'Все' },
  { key: 'Posted',    label: 'В работе' },
  { key: 'Completed', label: 'Завершённые' },
  { key: 'Cancelled', label: 'Отменённые' },
];

const PAGE_SIZE = 20;

function parseLinksStr(s) {
  if (!s) return [];
  return String(s).split(',')
    .map(l => l.trim().replace(/^['"\[\] ]+|['"\[\] ]+$/g, ''))
    .filter(l => l.startsWith('http'));
}

function OrderAccordionCard({ order: o }) {
  const [open, setOpen] = useOrdersState(false);
  const links = parseLinksStr(o.links);
  return (
    <div style={{ borderBottom: '1px solid var(--border)', cursor: 'pointer' }} onClick={() => setOpen(v => !v)}>
      <div style={{ padding: '14px 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{o.position_name}</div>
            <div style={{ color: 'var(--text-3)', fontSize: '0.75rem', marginTop: 2 }}>
              #{o.order_id} · {o.date ? new Date(o.date).toLocaleDateString('ru-RU') : '—'}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <StatusBadge status={o.status} />
            <div style={{ fontWeight: 700, color: 'var(--primary)', marginTop: 5, fontSize: '0.9rem' }}>
              {o.price.toLocaleString('ru-RU')} ₽
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--primary)' }}>
            {open ? '▲ Скрыть' : '▼ Подробнее'}
          </span>
        </div>
      </div>
      {open && (
        <div style={{ padding: '0 16px 16px', borderTop: '1px solid var(--border)', paddingTop: 12 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: '0.8125rem', color: 'var(--text-2)' }}>
            <div><strong>Контакты:</strong> {o.contacts ? 'Да' : 'Нет'}</div>
            {links.length > 0 && (
              <div>
                <strong>Ссылки ({links.length}):</strong>
                <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {links.map((l, i) => (
                    <a key={i} href={l} target="_blank" rel="noopener"
                       style={{ fontSize: '0.75rem', wordBreak: 'break-all', color: 'var(--primary)' }}
                       onClick={e => e.stopPropagation()}>
                      {l.replace('https://www.avito.ru', 'avito.ru')}
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function OrdersPage({ onNavigate }) {
  const [orders, setOrders] = useOrdersState([]);
  const [total, setTotal] = useOrdersState(0);
  const [filter, setFilter] = useOrdersState('all');
  const [page, setPage] = useOrdersState(1);
  const [loading, setLoading] = useOrdersState(true);

  const loadOrders = async (p = 1) => {
    setLoading(true);
    try {
      const data = await api.get(`/api/orders?page=${p}&page_size=${PAGE_SIZE}`);
      if (!data.__unauthorized) {
        setOrders(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (_) {} finally { setLoading(false); }
  };

  useOrdersEffect(() => { loadOrders(page); }, [page]);

  const filtered = filter === 'all' ? orders : orders.filter(o => o.status === filter);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleFilter = (key) => { setFilter(key); };
  const handlePage = (p) => { setPage(p); loadOrders(p); };

  return (
    <div className="page-wrap">
      <div className="orders-page">
        <div className="container">

          <button className="order-back" onClick={() => onNavigate('cabinet')}>← Назад в кабинет</button>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
            <h2>История заказов</h2>
            <button className="btn btn--primary btn--sm" onClick={() => onNavigate('order-pf')}>
              + Новый заказ
            </button>
          </div>

          <div className="orders-filters">
            {STATUS_FILTERS.map(f => (
              <button
                key={f.key}
                className={`filter-tab${filter === f.key ? ' active' : ''}`}
                onClick={() => handleFilter(f.key)}
              >
                {f.label}
                {f.key !== 'all' && (
                  <span style={{ marginLeft: 6, opacity: 0.7 }}>
                    ({orders.filter(o => o.status === f.key).length})
                  </span>
                )}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)' }}>Загрузка...</div>
          ) : filtered.length === 0 ? (
            <div className="card">
              <div className="empty-state">
                <div className="empty-state__icon" style={{ fontSize: '1.5rem' }}>—</div>
                <div className="empty-state__title">Заказов не найдено</div>
                <div className="empty-state__desc">
                  {filter === 'all' ? 'Вы ещё не сделали ни одного заказа' : 'Нет заказов с таким статусом'}
                </div>
                <button className="btn btn--primary" onClick={() => onNavigate('cabinet')}>Выбрать услугу</button>
              </div>
            </div>
          ) : (
            <>
              <div className="card desktop-only" style={{ overflow: 'hidden' }}>
                <table className="orders-table">
                  <thead>
                    <tr><th>#</th><th>Услуга</th><th>Сумма</th><th>Статус</th><th>Дата</th><th>Ссылки</th></tr>
                  </thead>
                  <tbody>
                    {filtered.map(o => {
                      const links = parseLinksStr(o.links);
                      return (
                        <tr key={o.order_id}>
                          <td style={{ color: 'var(--text-3)', fontWeight: 600 }}>#{o.order_id}</td>
                          <td style={{ fontWeight: 600 }}>{o.position_name}</td>
                          <td><span style={{ fontWeight: 700 }}>{o.price.toLocaleString('ru-RU')} ₽</span></td>
                          <td><StatusBadge status={o.status} /></td>
                          <td style={{ color: 'var(--text-3)', fontSize: '0.8125rem' }}>
                            {o.date ? new Date(o.date).toLocaleDateString('ru-RU') : '—'}
                          </td>
                          <td style={{ color: 'var(--text-3)', fontSize: '0.75rem' }}>
                            {links.length > 0 ? `${links.length} ссылк.` : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="card mobile-only" style={{ overflow: 'hidden' }}>
                {filtered.map(o => <OrderAccordionCard key={o.order_id} order={o} />)}
              </div>

              {totalPages > 1 && (
                <div className="pagination">
                  <button className="pagination__btn" disabled={page <= 1} onClick={() => handlePage(page - 1)}>← Назад</button>
                  <span className="pagination__info">Страница {page} из {totalPages}</span>
                  <button className="pagination__btn" disabled={page >= totalPages} onClick={() => handlePage(page + 1)}>Вперёд →</button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { OrdersPage });
```

- [ ] **Step 2: Commit**

```bash
git add web/static/components/Orders.jsx
git commit -m "feat: Orders — real API with pagination and link parsing"
```

---

## Task 8: Profile.jsx — provider linking with real API

**Files:**
- Create: `web/static/components/Profile.jsx`

Uses `/api/me/providers` to show linked providers. Links email via `POST /api/auth/link/email`. Links Telegram via `POST /api/auth/link/telegram/request-code` then `POST /api/auth/link/telegram/verify-code`.

- [ ] **Step 1: Write Profile.jsx**

Create `web/static/components/Profile.jsx`:

```jsx
// Profile page — show linked providers, allow linking email + TG
const { useState: useProfileState, useEffect: useProfileEffect } = React;

function ProfilePage({ user, onNavigate }) {
  const [providers, setProviders] = useProfileState([]);
  const [emailInput, setEmailInput] = useProfileState('');
  const [emailPass, setEmailPass] = useProfileState('');
  const [tgInput, setTgInput] = useProfileState('');
  const [tgCode, setTgCode] = useProfileState('');
  const [tgStep, setTgStep] = useProfileState('idle'); // idle | sent | done
  const [emailStatus, setEmailStatus] = useProfileState(''); // '' | 'loading' | 'success' | 'error'
  const [emailError, setEmailError] = useProfileState('');
  const [tgError, setTgError] = useProfileState('');

  useProfileEffect(() => {
    api.get('/api/me/providers').then(data => {
      if (!data.__unauthorized) setProviders(data);
    }).catch(() => {});
  }, []);

  const emailProvider = providers.find(p => p.provider === 'email');
  const tgProvider = providers.find(p => p.provider === 'telegram');

  const handleLinkEmail = async () => {
    if (!emailInput || !emailPass) return setEmailError('Заполните email и пароль');
    if (emailPass.length < 8) return setEmailError('Пароль — минимум 8 символов');
    setEmailStatus('loading'); setEmailError('');
    try {
      await api.post('/api/auth/link/email', { email: emailInput, password: emailPass, first_name: null });
      setEmailStatus('success');
      setProviders(prev => [...prev, { provider: 'email', identifier: emailInput, created_at: new Date().toISOString(), last_used_at: null }]);
    } catch (e) {
      setEmailStatus('error');
      if (e.status === 409) setEmailError('Email уже привязан к другому аккаунту');
      else setEmailError(e.message || 'Ошибка привязки');
    }
  };

  const handleRequestTgCode = async () => {
    if (!tgInput) return;
    setTgError('');
    try {
      await api.post('/api/auth/link/telegram/request-code', { identifier: tgInput });
      setTgStep('sent');
    } catch (e) {
      if (e.status === 429) setTgError('Подождите перед повторной отправкой');
      else setTgError(e.message || 'Ошибка отправки кода');
    }
  };

  const handleVerifyTg = async () => {
    if (!tgCode || tgCode.length < 6) return;
    setTgError('');
    try {
      await api.post('/api/auth/link/telegram/verify-code', { identifier: tgInput, code: tgCode });
      setTgStep('done');
      setProviders(prev => [...prev, { provider: 'telegram', identifier: tgInput, created_at: new Date().toISOString(), last_used_at: null }]);
    } catch (e) {
      if (e.status === 410) setTgError('Код истёк — запросите новый');
      else if (e.status === 401) setTgError('Неверный код');
      else if (e.status === 409) setTgError('Telegram уже привязан к другому аккаунту');
      else setTgError(e.message || 'Ошибка проверки кода');
    }
  };

  const ProviderCard = ({ title, icon, linked, linkedLabel, children }) => (
    <div className="card" style={{ padding: '20px 24px', marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: linked ? 0 : 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 10, background: 'var(--primary-dim)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '0.7rem', fontWeight: 800, color: 'var(--primary)'
          }}>{icon}</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.9375rem' }}>{title}</div>
            {linked && <div style={{ fontSize: '0.8rem', color: 'var(--text-3)', marginTop: 2 }}>{linkedLabel}</div>}
          </div>
        </div>
        {linked
          ? <span className="badge badge--completed">✓ Привязан</span>
          : <span className="badge badge--muted">Не привязан</span>
        }
      </div>
      {!linked && <div style={{ marginTop: 16 }}>{children}</div>}
    </div>
  );

  return (
    <div className="page-wrap">
      <div style={{ padding: '28px 0 60px' }}>
        <div className="container" style={{ maxWidth: 600 }}>

          <button className="order-back" onClick={() => onNavigate('cabinet')}>← Назад в кабинет</button>

          <h2 style={{ marginBottom: 6 }}>Профиль</h2>
          <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', marginBottom: 28 }}>
            Управляйте способами входа в аккаунт
          </p>

          <div className="card" style={{ padding: '20px 24px', marginBottom: 24, display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{
              width: 52, height: 52, borderRadius: '50%', background: 'var(--primary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontSize: '1.25rem', fontWeight: 800, flexShrink: 0
            }}>
              {(user?.first_name || '?')[0].toUpperCase()}
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem' }}>{user?.first_name || 'Пользователь'}</div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-3)' }}>@{user?.user_name || 'username'}</div>
            </div>
          </div>

          <h3 style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
            Способы входа
          </h3>

          <ProviderCard
            title="Email и пароль" icon="Em"
            linked={!!emailProvider}
            linkedLabel={emailProvider?.identifier || ''}
          >
            {emailStatus === 'success' ? (
              <div className="alert alert--success">✅ Email успешно привязан</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {emailError && <div className="alert alert--error">{emailError}</div>}
                <div className="form-field">
                  <label className="form-label">Email</label>
                  <input className="input" type="email" placeholder="you@example.com" value={emailInput} onChange={e => setEmailInput(e.target.value)} />
                </div>
                <div className="form-field">
                  <label className="form-label">Пароль</label>
                  <input className="input" type="password" placeholder="Минимум 8 символов" value={emailPass} onChange={e => setEmailPass(e.target.value)} />
                  <div className="form-hint">Придумайте пароль для входа через email</div>
                </div>
                <button className="btn btn--primary" onClick={handleLinkEmail} disabled={emailStatus === 'loading'}>
                  {emailStatus === 'loading' ? 'Привязываем...' : 'Привязать email'}
                </button>
              </div>
            )}
          </ProviderCard>

          <ProviderCard
            title="Telegram" icon="TG"
            linked={!!tgProvider || tgStep === 'done'}
            linkedLabel={tgProvider?.identifier || tgInput || ''}
          >
            {tgStep === 'done' ? (
              <div className="alert alert--success">✅ Telegram успешно привязан</div>
            ) : tgStep === 'idle' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {tgError && <div className="alert alert--error">{tgError}</div>}
                <div className="form-field">
                  <label className="form-label">Username или номер телефона</label>
                  <input className="input" placeholder="@username или +79001234567" value={tgInput} onChange={e => setTgInput(e.target.value)} />
                </div>
                <button className="btn btn--secondary" onClick={handleRequestTgCode} disabled={!tgInput}>
                  ✈ Получить код в Telegram
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {tgError && <div className="alert alert--error">{tgError}</div>}
                <div className="alert alert--info">Код отправлен в Telegram на {tgInput}</div>
                <div className="form-field">
                  <label className="form-label">6-значный код</label>
                  <input
                    className="input" placeholder="123456" value={tgCode} maxLength={6}
                    onChange={e => setTgCode(e.target.value.replace(/\D/g, ''))}
                    style={{ textAlign: 'center', fontSize: '1.25rem', letterSpacing: '0.15em', fontWeight: 700 }}
                    autoFocus
                  />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn--ghost btn--sm" onClick={() => setTgStep('idle')}>← Назад</button>
                  <button className="btn btn--primary" style={{ flex: 1 }} onClick={handleVerifyTg} disabled={tgCode.length < 6}>
                    Подтвердить
                  </button>
                </div>
              </div>
            )}
          </ProviderCard>

          <div className="card" style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--primary-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontWeight: 800, color: 'var(--primary)' }}>REF</div>
              <div style={{ fontWeight: 700 }}>Реферальная программа</div>
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-2)', marginBottom: 14, lineHeight: 1.6 }}>
              Приглашайте друзей и получайте бонус при каждом их пополнении баланса.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                className="input" readOnly
                value={`https://proboost.app/ref/${user?.user_name || 'user'}`}
                style={{ flex: 1, fontSize: '0.8125rem', color: 'var(--text-2)' }}
                onClick={e => e.target.select()}
              />
              <button
                className="btn btn--secondary btn--sm"
                onClick={() => navigator.clipboard?.writeText(`https://proboost.app/ref/${user?.user_name || 'user'}`)}
              >Скопировать</button>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ProfilePage });
```

- [ ] **Step 2: Commit**

```bash
git add web/static/components/Profile.jsx
git commit -m "feat: Profile — real API provider listing + link email/TG"
```

---

## Task 9: app.jsx — root with session restore and API auth

**Files:**
- Create: `web/static/app.jsx`

Root responsibilities: restore JWT session on page load, expose `api` to all components (already done in `api.js`), manage routing and user state, refresh balance after order placement.

- [ ] **Step 1: Write app.jsx**

Create `web/static/app.jsx`:

```jsx
// app.jsx — root state, session restore, routing
const { useState, useEffect } = React;

const TWEAK_DEFAULTS = {
  theme: 'light',
  variant: 'classic',
  brandName: 'ProBoost',
  accentColor: '#0088cc'
};

function App() {
  const [tweaks, setTweaks] = useState(TWEAK_DEFAULTS);
  const [route, setRoute] = useState('landing');
  const [authMode, setAuthMode] = useState('login');
  const [user, setUser] = useState(null);
  const [balance, setBalance] = useState(0);
  const [appLoading, setAppLoading] = useState(true);

  // Apply theme + variant to <html>
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', tweaks.theme);
    document.documentElement.setAttribute('data-variant', tweaks.variant);
    if (tweaks.accentColor) {
      document.documentElement.style.setProperty('--primary', tweaks.accentColor);
    }
  }, [tweaks]);

  // Restore session from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) { setAppLoading(false); return; }
    api.get('/api/me').then(data => {
      if (data.__unauthorized) {
        localStorage.removeItem('access_token');
      } else {
        setUser({ first_name: data.first_name, user_name: data.user_name, user_id: data.user_id });
        setBalance(data.balance);
        setRoute('cabinet');
      }
    }).catch(() => {
      localStorage.removeItem('access_token');
    }).finally(() => setAppLoading(false));
  }, []);

  const refreshBalance = () => {
    api.get('/api/me').then(data => {
      if (!data.__unauthorized) setBalance(data.balance);
    }).catch(() => {});
  };

  const setTweak = (key, val) => {
    setTweaks(prev => typeof key === 'object' ? { ...prev, ...key } : { ...prev, [key]: val });
  };

  const handleLogin = (token) => {
    localStorage.setItem('access_token', token);
    api.get('/api/me').then(data => {
      setUser({ first_name: data.first_name, user_name: data.user_name, user_id: data.user_id });
      setBalance(data.balance);
      setRoute('cabinet');
    }).catch(() => {
      localStorage.removeItem('access_token');
    });
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    setUser(null);
    setBalance(0);
    setRoute('landing');
  };

  const handleNavigate = (target) => {
    if (['cabinet', 'order-pf', 'orders', 'profile'].includes(target) && !user) {
      setAuthMode('login');
      setRoute('auth');
      return;
    }
    if (['login', 'register', 'login-tg'].includes(target)) {
      setAuthMode(target);
      setRoute('auth');
      return;
    }
    setRoute(target);
  };

  const handleOrderPlaced = (price) => {
    setBalance(b => b - price);
  };

  if (appLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', color: 'var(--text-3)' }}>
      Загрузка...
    </div>
  );

  const headerProps = {
    route, user, balance,
    brandName: tweaks.brandName,
    theme: tweaks.theme,
    onToggleTheme: () => setTweak('theme', tweaks.theme === 'dark' ? 'light' : 'dark'),
    onNavigate: handleNavigate,
    onLogout: handleLogout,
  };

  const renderScreen = () => {
    switch (route) {
      case 'landing':  return <LandingPage onNavigate={handleNavigate} brandName={tweaks.brandName} />;
      case 'auth':     return <AuthPage mode={authMode} onLogin={handleLogin} onNavigate={handleNavigate} />;
      case 'cabinet':  return <CabinetPage user={user} balance={balance} setBalance={setBalance} refreshBalance={refreshBalance} onNavigate={handleNavigate} />;
      case 'order-pf': return <OrderFormPage balance={balance} onNavigate={handleNavigate} onOrderPlaced={handleOrderPlaced} />;
      case 'orders':   return <OrdersPage onNavigate={handleNavigate} />;
      case 'profile':  return <ProfilePage user={user} onNavigate={handleNavigate} />;
      default:         return <LandingPage onNavigate={handleNavigate} brandName={tweaks.brandName} />;
    }
  };

  return (
    <div>
      <AppHeader {...headerProps} />
      {renderScreen()}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
```

- [ ] **Step 2: Commit**

```bash
git add web/static/app.jsx
git commit -m "feat: app.jsx — session restore from localStorage, routing, balance sync"
```

---

## Task 10: Delete old multi-page HTML files

**Files:**
- Delete: `web/static/login.html`, `web/static/login_telegram.html`, `web/static/register.html`, `web/static/cabinet.html`, `web/static/orders.html`, `web/static/pf-order.html`

These pages used the old design and old auth mechanism. They conflict with the SPA.

- [ ] **Step 1: Remove old HTML files**

```bash
git rm web/static/login.html \
       web/static/login_telegram.html \
       web/static/register.html \
       web/static/cabinet.html \
       web/static/orders.html \
       web/static/pf-order.html
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: remove old multi-page HTML (replaced by SPA)"
```

---

## Task 11: E2E verification — pages, order creation, TG notification

**Goal:** Start the server, open all pages in browser, create a real order, verify balance deducted and TG admin notification received.

**Prerequisites:** Bot is running with a real TG token. Web server accessible (default port 8000). Test user account exists.

- [ ] **Step 1: Start the app**

```bash
cd /Users/belikov/Documents/pets/bots/telegram/original_avito_pf_bot
python -m __main__
```

Server should start at http://localhost:8000. Check: `curl -s http://localhost:8000/api/health` → `{"status":"ok"}`

- [ ] **Step 2: Open landing page in browser**

Navigate to http://localhost:8000 in Chrome (use Claude in Chrome tool or open manually).

Verify:
- Hero section visible with "Войти через Telegram" and "Войти через Email" buttons
- Services grid shows 6 cards (2 active: ПФ, Отзывы; 4 with "Скоро" badges)
- FAQ accordion opens/closes
- Stats section shows 3 cards
- Footer shows Telegram links
- Theme toggle (●/○ button) switches dark/light

- [ ] **Step 3: Test email login**

Click "Войти через Email" → Auth page renders with card layout.

Use an existing test user (check `.env` or DB for credentials) or register via:
- Click "Зарегистрироваться"
- Fill: name="Тест", email="test@test.com", password="testtest123"
- Click "Создать аккаунт →"

Verify: redirected to Cabinet page. Header shows user avatar and balance badge.

- [ ] **Step 4: Verify Cabinet page**

After login, verify:
- Welcome strip shows user's first name
- Balance card shows real balance from `/api/me`
- Services catalog shows 6 cards
- Recent orders table loads from API (may be empty)
- Chat button visible in bottom-right corner
- Click Chat → chat panel opens, messages load from `/api/support/messages`

- [ ] **Step 5: Verify Orders page**

Click "Заказы" in header nav → Orders page renders.

Verify:
- Orders load from API
- Status filter tabs work (Все / В работе / Завершённые / Отменённые)
- Table visible on desktop, accordion cards on mobile

- [ ] **Step 6: Create a PF order**

Click "+ Заказать ПФ" in header → OrderForm page.

Set parameters:
- Paste URL: `https://www.avito.ru/moskva/uslugi/test_123456`
- Views/day: 15 (slider)
- Days: 7 (slider)
- Contacts: off

Verify price preview shows: `15 × 7 × 1 × 6 = 630 ₽` (or whatever `price_per_unit` the API returns).

Check balance is sufficient. Click "Разместить заказ".

Expected: success screen "✅ Заказ принят! Списано 630 ₽" → redirects to Cabinet after ~2s.

- [ ] **Step 7: Verify balance deducted**

After redirect to Cabinet, verify:
- Balance badge in header shows old balance minus 630 ₽
- Recent orders table shows the new order with status "В работе"

- [ ] **Step 8: Verify TG admin notification**

Check the admin Telegram chat. Expected message format:
```
🌐 Новый заказ #N (веб)
💰 Сумма: 630 ₽
👤 Пользователь: ...
📧 Email: test@test.com
📋 Тариф: Авито ПФ
📊 Статус: Posted
📞 Контакт: Нет
📅 Дата: 2026-05-11
🔗 Ссылок: 1
https://www.avito.ru/moskva/uslugi/test_123456
```

- [ ] **Step 9: Verify Profile page**

Click user dropdown → "Профиль". Verify:
- User avatar card shows first_name and @username
- "Способы входа" section shows linked providers (email should show ✓ Привязан)
- Referral link field is pre-filled

- [ ] **Step 10: Final commit**

```bash
git add -p  # review any remaining changes
git commit -m "feat: ProBoost SPA — full design implementation with real API"
```

---

## Self-Review

### Spec Coverage Check

| Requirement | Task |
|---|---|
| Внедри дизайн полностью | Tasks 1-9 |
| Проверь все страницы (landing, auth, cabinet, orders, order form, profile) | Task 11, Steps 2-5,9 |
| Создай заявку через новый веб | Task 11, Step 6 |
| Деньги списались с баланса | Task 11, Step 7 |
| Уведомление о заказе пришло админам в ТГ | Task 11, Step 8 |
| Работай от ветки dev | Worktree is branched from dev ✓ |

### Placeholder Scan

No TBD, TODO, or vague steps. All steps have:
- Exact bash commands or complete JSX code
- Expected output descriptions
- Exact file paths

### Type Consistency Check

- `onLogin(token: string)` — `AuthPage` calls `onLogin(data.access_token)` ✓, `App.handleLogin(token)` stores in localStorage ✓
- `onOrderPlaced(price: number)` — `OrderFormPage` calls `onOrderPlaced(totalPrice)` ✓, `App.handleOrderPlaced(price)` subtracts from balance ✓
- `refreshBalance()` — `App` defines it, `CabinetPage` receives it as prop ✓
- `StatusBadge` — defined in `Cabinet.jsx`, exposed via `window`, used in `Orders.jsx` ✓ (Cabinet loads before Orders per index.html script order)
- `api.get / api.post` — defined in `api.js`, loaded before all Babel scripts ✓
- `fix_count` in API = `views` in UI — consistent in `OrderForm.jsx` POST body ✓
