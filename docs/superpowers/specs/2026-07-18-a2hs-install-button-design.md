# Add-to-Home-Screen Install Button (Cabinet)

**Date:** 2026-07-18
**Status:** Approved

## Problem

Users open the cabinet through the browser every time. The PWA plumbing (manifest, icons, `display: standalone`) already exists in `web/static/`, but nothing in the UI invites the user to install. We want visible entry points in the личный кабинет that trigger installation ("добавить значок на главный экран").

## Goal

Two entry points (approved as variant B + C from mockups):

1. **Banner** in the cabinet dashboard — reach: seen by everyone who opens the cabinet, dismissible forever.
2. **Header icon** in `AppHeader` next to the notifications bell — quiet permanent entry point.

Both do the same on click: native install prompt on Chromium (Android/desktop), step-by-step instructions sheet on iOS Safari. Neither is shown when the app is already installed, as far as the platform allows detection.

## Scope

Frontend only, no backend changes:

- `web/static/a2hs.js` — **new**, early event capture + state helper
- `web/static/components/InstallPrompt.jsx` — **new**, React components
- `web/static/index.html` — two script tags
- `web/static/components/Cabinet.jsx` — mount banner
- `web/static/components/AppHeader.jsx` — mount header icon
- `web/static/app.jsx` — mount iOS guide sheet at root
- `web/static/platform.css` — styles (both themes, both breakpoints)

`manifest.json` needs no changes: the FastAPI app serves the SPA from `/` (`web/main.py` `spa_fallback`), so `start_url: "/"` opens the cabinet.

---

## Visibility matrix

| Environment | Detection signal | Banner | Header icon | Click action |
|---|---|---|---|---|
| Running as installed app | `display-mode: standalone` or `navigator.standalone` | hidden | hidden | — |
| Chromium, installable | `beforeinstallprompt` captured | shown unless dismissed | shown | `deferredPrompt.prompt()` |
| Chromium, installed | no `beforeinstallprompt` / `appinstalled` fired | hidden | hidden | — |
| iOS Safari | iPhone/iPad UA (installability unknowable) | shown unless dismissed | shown | open instructions sheet |
| Other (Firefox, desktop Safari, …) | no prompt event, not iOS | hidden | hidden | — |

Known iOS limitation (accepted): Safari cannot tell whether the icon is already on the home screen while browsing. A user who added the icon manually and never dismissed the banner sees it once; the "Готово, добавил" button in the sheet and the ✕ both hide it forever. The header icon stays visible on iOS — it is small and harmless.

Known iOS limitation #2 (accepted): the home-screen web app has storage separate from Safari, so the user logs in again on first launch of the installed app.

---

## Architecture

### 1. `web/static/a2hs.js` — early capture, plain JS

`beforeinstallprompt` can fire before Babel compiles the React components, so capture must happen in a plain script loaded before the React block in `index.html` (next to `api.js`).

Exposes `window.a2hs`:

```js
window.a2hs = {
  getState(),     // 'installed' | 'installable' | 'ios' | 'unavailable'
  prompt(),       // calls deferredPrompt.prompt(); resolves with outcome
  subscribe(cb),  // cb() on any state change; returns unsubscribe
  isDismissed(),  // localStorage 'a2hs_dismissed' === '1' (in-memory fallback)
  dismiss(),      // set flag + notify subscribers
};
```

State resolution order:

1. `installed` — `matchMedia('(display-mode: standalone)').matches || navigator.standalone === true`, or `appinstalled` event fired this session.
2. `installable` — `beforeinstallprompt` captured (`e.preventDefault()`, keep reference).
3. `ios` — `/iphone|ipad|ipod/i.test(navigator.userAgent)` or iPadOS masquerading as Mac (`platform === 'MacIntel' && maxTouchPoints > 1`).
4. `unavailable` — everything else.

Note: on Chromium `beforeinstallprompt` arrives asynchronously (often a second or two after load), so state starts as `unavailable` and flips to `installable` — this is why components subscribe instead of reading once.

`prompt()` guards: a captured event can be `.prompt()`ed only once. After use the reference is cleared; if the user declined, Chromium may re-fire `beforeinstallprompt` later and the state flips back to `installable`. If the reference is absent, `prompt()` is a no-op.

`localStorage` unavailable (private mode) → `dismiss()` keeps the flag in memory: banner hides for the session, reappears next visit. Acceptable.

### 2. `web/static/components/InstallPrompt.jsx`

- `useA2HS()` — hook: `{ state, dismissed }`, subscribes to `window.a2hs` on mount.
- `InstallBanner` — card for the cabinet. Visible when `(state === 'installable' || state === 'ios') && !dismissed`. App icon, title «Добавьте авито.пф на экран», subtitle «Быстрый доступ к заказам и балансу», primary button «Установить», ✕ in the corner (→ `a2hs.dismiss()`).
- `InstallHeaderButton` — icon button for the header. Visible when `state === 'installable' || state === 'ios'` (ignores dismissed). `title="Добавить на главный экран"`.
- `InstallGuideSheet` — iOS instructions. Mounted once at app root; opened by CustomEvent `a2hs-open-guide` (same pattern as `support-chat-send`). Bottom sheet on mobile, centered dialog on desktop. Three steps (Поделиться → «На экран “Домой”» → Добавить), ghost button «Готово, добавил» (→ `dismiss()` + close), closes on overlay click.

Click routing (shared handler): `state === 'installable'` → `a2hs.prompt()`; `state === 'ios'` → `window.dispatchEvent(new CustomEvent('a2hs-open-guide'))`.

### 3. Mount points

- `Cabinet.jsx` — `<InstallBanner />` right after `.cabinet-top-row`, before the services catalog. Full-width card.
- `AppHeader.jsx` — `<InstallHeaderButton />` immediately left of `<NotificationsBell />`; rendered only when `isApp && user && !adminMode`, in both desktop and mobile action groups.
- `app.jsx` — `<InstallGuideSheet />` mounted at root alongside `SupportChat`.
- `index.html` — `<script src="/a2hs.js">` after `api.js`; `InstallPrompt.jsx` script tag before `AppHeader.jsx` (dependency order).

### 4. Styles (`platform.css`)

New block near other component styles: `.a2hs-banner`, `.a2hs-header-btn`, `.a2hs-sheet` (+ overlay). Theme via existing CSS vars only (`--surface`, `--border`, `--primary`, `--text-*`) — must look right in light and dark. Breakpoints: banner is a normal card on both; sheet is bottom-anchored under 640px, centered dialog above. Per project rule, verify on mobile AND desktop.

---

## Data flow

```
page load
   │
a2hs.js: detect standalone / iOS, listen for beforeinstallprompt, appinstalled
   │
React mounts → useA2HS() subscribes → components render per visibility matrix
   │
click (banner or header icon)
   ├─ installable → a2hs.prompt() ──► native dialog ──► appinstalled → all UI hides
   └─ ios → CustomEvent 'a2hs-open-guide' ──► sheet with 3 steps
                                                  ├─ «Готово, добавил» → dismiss() → banner hidden forever
                                                  └─ close/overlay → nothing persisted
banner ✕ → dismiss() → banner hidden forever (header icon unaffected)
```

---

## Testing

No JS test infrastructure exists (components are Babel-in-browser, Python tests only). Verification is manual, against a checklist:

1. Chrome desktop: banner + header icon appear once `beforeinstallprompt` fires; «Установить» opens the native dialog; accepting hides both immediately (`appinstalled`); relaunch in the installed window shows neither (standalone).
2. Chrome DevTools device emulation + real Android if available: same flow.
3. iOS Safari (device or simulator): banner + icon visible; click opens the sheet; «Готово, добавил» hides the banner permanently (survives reload); header icon remains.
4. ✕ on the banner: hidden, survives reload.
5. Firefox desktop: neither banner nor icon rendered.
6. Both themes (light/dark), both breakpoints (mobile/desktop) for banner and sheet.
7. Full Python suite in Docker — must stay green (no backend changes expected).
