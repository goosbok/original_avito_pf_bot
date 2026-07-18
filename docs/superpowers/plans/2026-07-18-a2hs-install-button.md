# Add-to-Home-Screen Install Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two entry points in the cabinet (dismissible banner + header icon) that trigger PWA installation — native prompt on Chromium, instructions sheet on iOS — and hide themselves when the app is already installed.

**Architecture:** A plain-JS module (`a2hs.js`) loaded before React captures `beforeinstallprompt`/`appinstalled` and exposes a tiny state API on `window.a2hs`. React components (`InstallPrompt.jsx`) subscribe to it and render the banner (Cabinet), the header icon (AppHeader), and the iOS guide sheet (app root, opened via CustomEvent like `support-chat-send`). Spec: `docs/superpowers/specs/2026-07-18-a2hs-install-button-design.md`.

**Tech Stack:** React 18 UMD + Babel standalone (no build step, no JS tests — verification is manual in browser), plain CSS with theme variables in `platform.css`, FastAPI serves statics.

**Important codebase conventions:**
- Each `.jsx` file is a separate `text/babel` script sharing the global scope. Top-level `const`/`let` collide across files — alias React hooks uniquely per file (e.g. `const { useState: useA2hsState } = React;`), exactly like `Cabinet.jsx` does with `useCabinetState`.
- Components are plain global `function` declarations, no imports/exports.
- JSX SVG attributes are camelCase (`strokeWidth`, not `stroke-width`).
- Commits: Conventional Commits, English, no Co-Authored-By / watermarks.

---

## File Map

| File | Change |
|---|---|
| `web/static/a2hs.js` | New — event capture + `window.a2hs` state API |
| `web/static/components/InstallPrompt.jsx` | New — `useA2HS`, `InstallBanner`, `InstallHeaderButton`, `InstallGuideSheet` |
| `web/static/index.html` | Two script tags (a2hs.js, InstallPrompt.jsx) |
| `web/static/components/Cabinet.jsx` | Mount `<InstallBanner />` after top-row (~line 254) |
| `web/static/components/AppHeader.jsx` | Mount `<InstallHeaderButton />` before `<NotificationsBell />` (~line 131) |
| `web/static/app.jsx` | Mount `<InstallGuideSheet />` at root (~line 312) |
| `web/static/platform.css` | New `.a2hs-*` styles block (append at end) |

---

## Task 1: `a2hs.js` state module + script tag

**Files:**
- Create: `web/static/a2hs.js`
- Modify: `web/static/index.html` (after the `/api.js` script tag, line ~26)

- [ ] **Step 1: Create `web/static/a2hs.js`**

```js
// a2hs.js — Add-to-Home-Screen state helper.
// Plain JS loaded BEFORE the React/Babel scripts: `beforeinstallprompt`
// can fire while components are still compiling, so capture happens here.
//
// States:
//   'installed'   — running standalone, or `appinstalled` fired this session
//   'installable' — Chromium handed us a deferred install prompt
//   'ios'         — iPhone/iPad Safari: no API, we show manual instructions
//   'unavailable' — everything else (Firefox, desktop Safari, …): show nothing
(function () {
  var deferredPrompt = null;
  var installedThisSession = false;
  var subscribers = [];
  var memDismissed = false; // fallback when localStorage is blocked

  function notify() {
    subscribers.forEach(function (cb) { try { cb(); } catch (_) {} });
  }

  function isStandalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches)
      || window.navigator.standalone === true;
  }

  function isIos() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent)
      // iPadOS ≥13 reports itself as a Mac, but Macs have no touch points
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferredPrompt = e;
    notify();
  });

  window.addEventListener('appinstalled', function () {
    deferredPrompt = null;
    installedThisSession = true;
    notify();
  });

  window.a2hs = {
    getState: function () {
      if (installedThisSession || isStandalone()) return 'installed';
      if (deferredPrompt) return 'installable';
      if (isIos()) return 'ios';
      return 'unavailable';
    },
    // A captured event can be .prompt()ed only once: consume the reference.
    // If the user declines, Chromium re-fires beforeinstallprompt later
    // (usually on next navigation) and the state flips back to 'installable'.
    prompt: function () {
      if (!deferredPrompt) return Promise.resolve(null);
      var p = deferredPrompt;
      deferredPrompt = null;
      notify();
      p.prompt();
      return p.userChoice;
    },
    subscribe: function (cb) {
      subscribers.push(cb);
      return function () {
        subscribers = subscribers.filter(function (s) { return s !== cb; });
      };
    },
    isDismissed: function () {
      try { return memDismissed || localStorage.getItem('a2hs_dismissed') === '1'; }
      catch (_) { return memDismissed; }
    },
    dismiss: function () {
      memDismissed = true;
      try { localStorage.setItem('a2hs_dismissed', '1'); } catch (_) {}
      notify();
    },
  };
})();
```

- [ ] **Step 2: Add the script tag to `index.html`**

After the `/api.js` block (line ~26), before `/dates.js`:

```html
  <!-- Add-to-Home-Screen state (must load before React to catch beforeinstallprompt) -->
  <script src="/a2hs.js"></script>
```

- [ ] **Step 3: Verify in browser**

Run: `docker compose up -d` (if not already running), open `http://localhost:8000`.
In DevTools console: `window.a2hs.getState()`.
Expected: `'unavailable'` (Firefox/Safari) or `'installable'` after a couple of seconds (Chrome; localhost counts as a secure context). No console errors.

- [ ] **Step 4: Commit**

```bash
git add web/static/a2hs.js web/static/index.html
git commit -m "feat(web): add a2hs state module capturing PWA install events"
```

---

## Task 2: React components + mounts

**Files:**
- Create: `web/static/components/InstallPrompt.jsx`
- Modify: `web/static/index.html` (component script tags, line ~40)
- Modify: `web/static/app.jsx` (~line 312)

- [ ] **Step 1: Create `web/static/components/InstallPrompt.jsx`**

```jsx
// InstallPrompt — add-to-home-screen entry points: cabinet banner,
// header icon button, iOS instructions sheet.
// State machine lives in /a2hs.js (plain JS, loaded before React).
const { useState: useA2hsState, useEffect: useA2hsEffect } = React;

function useA2HS() {
  const [, force] = useA2hsState(0);
  useA2hsEffect(() => window.a2hs.subscribe(() => force(x => x + 1)), []);
  return { state: window.a2hs.getState(), dismissed: window.a2hs.isDismissed() };
}

function a2hsActivate(state) {
  if (state === 'installable') window.a2hs.prompt();
  else if (state === 'ios') window.dispatchEvent(new CustomEvent('a2hs-open-guide'));
}

function InstallBanner() {
  const { state, dismissed } = useA2HS();
  if (dismissed || (state !== 'installable' && state !== 'ios')) return null;
  return (
    <div className="card a2hs-banner">
      <button className="a2hs-banner__close" onClick={() => window.a2hs.dismiss()} aria-label="Скрыть">✕</button>
      <img className="a2hs-banner__icon" src="/icon-192.png" alt="" width="40" height="40" />
      <div className="a2hs-banner__text">
        <div className="a2hs-banner__title">Добавьте авито.пф на главный экран</div>
        <div className="a2hs-banner__desc">Быстрый доступ к заказам и балансу — в одно касание</div>
      </div>
      <button className="btn btn--primary btn--sm a2hs-banner__cta" onClick={() => a2hsActivate(state)}>
        Установить
      </button>
    </div>
  );
}

function InstallHeaderButton() {
  const { state } = useA2HS();
  if (state !== 'installable' && state !== 'ios') return null;
  return (
    <button
      className="a2hs-header-btn"
      onClick={() => a2hsActivate(state)}
      title="Добавить на главный экран"
      aria-label="Добавить на главный экран"
    >
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="6" y="3" width="12" height="18" rx="2" />
        <path d="M12 8v5m0 0l-2.2-2.2M12 13l2.2-2.2" />
      </svg>
    </button>
  );
}

function InstallGuideSheet() {
  const [open, setOpen] = useA2hsState(false);
  useA2hsEffect(() => {
    const h = () => setOpen(true);
    window.addEventListener('a2hs-open-guide', h);
    return () => window.removeEventListener('a2hs-open-guide', h);
  }, []);
  if (!open) return null;
  const done = () => { window.a2hs.dismiss(); setOpen(false); };
  return (
    <div className="a2hs-overlay" onClick={() => setOpen(false)}>
      <div className="a2hs-sheet" onClick={e => e.stopPropagation()}>
        <div className="a2hs-sheet__grab" aria-hidden="true" />
        <div className="a2hs-sheet__head">
          <img src="/icon-192.png" alt="" width="34" height="34" style={{ borderRadius: 8 }} />
          <div className="a2hs-sheet__title">Добавить на главный экран</div>
        </div>
        <ol className="a2hs-sheet__steps">
          <li>
            Нажмите <b>«Поделиться»</b>{' '}
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3v12M12 3L8 7m4-4l4 4" />
              <path d="M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7" />
            </svg>
            {' '}в панели Safari
          </li>
          <li>Выберите <b>«На экран “Домой”»</b></li>
          <li>Нажмите <b>«Добавить»</b> — значок появится на главном экране</li>
        </ol>
        <div className="a2hs-sheet__actions">
          <button className="btn btn--ghost btn--sm" onClick={done}>Готово, добавил</button>
          <button className="btn btn--secondary btn--sm" onClick={() => setOpen(false)}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Register the script in `index.html`**

In the components block, after `Notifications.jsx` and before `AppHeader.jsx` (AppHeader will use `InstallHeaderButton`):

```html
  <script type="text/babel" src="/components/InstallPrompt.jsx"></script>
```

- [ ] **Step 3: Mount the sheet at app root in `app.jsx`**

At line ~312, next to the existing `SupportChat` mount:

```jsx
      {user && !adminMode && <SupportChat />}
      {user && !adminMode && <InstallGuideSheet />}
```

- [ ] **Step 4: Verify in browser**

Reload `http://localhost:8000`, log in. No console errors. In console:
`window.dispatchEvent(new CustomEvent('a2hs-open-guide'))` — the sheet appears (unstyled until Task 4 — that's expected). Overlay click closes it.

- [ ] **Step 5: Commit**

```bash
git add web/static/components/InstallPrompt.jsx web/static/index.html web/static/app.jsx
git commit -m "feat(web): add install prompt components and iOS guide sheet"
```

---

## Task 3: Mount banner in Cabinet, icon in AppHeader

**Files:**
- Modify: `web/static/components/Cabinet.jsx` (~line 254)
- Modify: `web/static/components/AppHeader.jsx` (~line 131)

- [ ] **Step 1: Add banner to `Cabinet.jsx`**

Between the closing `</div>` of `.cabinet-top-row` (line ~254) and the `{/* Catalog */}` comment:

```jsx
          <InstallBanner />

          {/* Catalog */}
```

- [ ] **Step 2: Add icon button to `AppHeader.jsx`**

Right before the NotificationsBell line (`{isApp && user && !adminMode && <NotificationsBell onNavigate={onNavigate} />}`, line ~131):

```jsx
          {/* A2HS install entry point (regular user view only) */}
          {isApp && user && !adminMode && <InstallHeaderButton />}

```

- [ ] **Step 3: Verify in browser**

Chrome, `http://localhost:8000`, logged in: once `beforeinstallprompt` fires, the banner shows in the cabinet (between balance block and «Услуги») and the icon shows left of the bell. In Firefox: neither appears. No console errors either way.

- [ ] **Step 4: Commit**

```bash
git add web/static/components/Cabinet.jsx web/static/components/AppHeader.jsx
git commit -m "feat(web): mount install banner in cabinet and icon in header"
```

---

## Task 4: Styles in `platform.css`

**Files:**
- Modify: `web/static/platform.css` (append at end of file)

- [ ] **Step 1: Append the `.a2hs-*` block**

```css
/* ============ A2HS (add to home screen) ============ */
.a2hs-banner {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 18px; margin-bottom: 24px;
  position: relative; flex-wrap: wrap;
}
.a2hs-banner__icon { border-radius: 10px; flex-shrink: 0; }
.a2hs-banner__text { flex: 1 1 200px; min-width: 0; }
.a2hs-banner__title { font-weight: 700; font-size: 0.9375rem; }
.a2hs-banner__desc { font-size: 0.8125rem; color: var(--text-2); margin-top: 2px; }
.a2hs-banner__cta { white-space: nowrap; }
.a2hs-banner__close {
  position: absolute; top: 8px; right: 10px;
  background: none; border: none; cursor: pointer;
  color: var(--text-3); font-size: 0.875rem; line-height: 1; padding: 4px;
}
.a2hs-banner__close:hover { color: var(--text-1); }

/* Mirrors .bell__btn so header icons look uniform */
.a2hs-header-btn {
  background: transparent;
  border: 1.5px solid var(--border);
  border-radius: 50%;
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  color: var(--text-1);
  box-sizing: border-box;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.a2hs-header-btn:hover {
  background: var(--surface-2);
  border-color: var(--primary);
  color: var(--primary);
}

.a2hs-overlay {
  position: fixed; inset: 0; z-index: 1200;
  background: rgba(10, 14, 20, 0.5);
  display: flex; align-items: flex-end; justify-content: center;
}
.a2hs-sheet {
  background: var(--surface);
  border-radius: 16px 16px 0 0;
  width: 100%; max-width: 480px;
  padding: 14px 20px 24px;
  box-shadow: 0 -8px 30px rgba(0, 0, 0, 0.2);
}
.a2hs-sheet__grab {
  width: 36px; height: 4px; border-radius: 99px;
  background: var(--border); margin: 0 auto 14px;
}
.a2hs-sheet__head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.a2hs-sheet__title { font-weight: 700; font-size: 1rem; }
.a2hs-sheet__steps {
  margin: 0 0 16px; padding-left: 20px;
  display: flex; flex-direction: column; gap: 8px;
  font-size: 0.875rem; color: var(--text-2);
}
.a2hs-sheet__steps b { color: var(--text-1); }
.a2hs-sheet__steps svg { vertical-align: -3px; color: var(--primary); }
.a2hs-sheet__actions { display: flex; gap: 8px; }

/* Desktop: centered dialog instead of bottom sheet */
@media (min-width: 640px) {
  .a2hs-overlay { align-items: center; padding: 20px; }
  .a2hs-sheet { border-radius: 16px; }
  .a2hs-sheet__grab { display: none; }
}
```

- [ ] **Step 2: Verify both themes and breakpoints**

Reload. Check banner + sheet in: light theme mobile (DevTools iPhone emulation), light desktop, dark mobile, dark desktop (theme toggle in header). Nothing overflows, colors come from vars, sheet is bottom-anchored on mobile and centered on desktop.

- [ ] **Step 3: Commit**

```bash
git add web/static/platform.css
git commit -m "feat(web): style a2hs banner, header button and guide sheet"
```

---

## Task 5: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Chromium install flow**

Chrome on `http://localhost:8000`, logged in:
1. Banner + header icon appear (after `beforeinstallprompt`, up to a few seconds).
2. «Установить» → native install dialog.
3. Accept → banner and icon disappear immediately (`appinstalled`).
4. Open the installed app window → neither banner nor icon (standalone). Uninstall the app afterwards (chrome://apps).

- [ ] **Step 2: iOS flow (DevTools emulation)**

DevTools → iPhone emulation → reload (UA must be iPhone; use the "iPhone" device preset with its default UA):
1. Banner + icon visible.
2. Click → guide sheet with 3 steps slides up from the bottom.
3. «Готово, добавил» → sheet closes, banner gone; survives reload (localStorage).
4. Header icon still visible (expected on iOS).
5. Clear `localStorage.removeItem('a2hs_dismissed')` → banner back after reload.

- [ ] **Step 3: Dismiss flow**

✕ on the banner → hidden, survives reload. Header icon unaffected.

- [ ] **Step 4: Negative case**

Firefox (or Safari desktop): no banner, no icon, no console errors.

- [ ] **Step 5: Python suite (regression only — no backend changes)**

Run: `docker exec original_avito_pf_bot-api-1 python -m pytest` (per project rule: tests inside Docker, not local python3).
Expected: green, same as baseline.

- [ ] **Step 6: Final commit if anything was touched during verification**

```bash
git status   # expect clean; commit fixes with fix(web): ... if any
```
