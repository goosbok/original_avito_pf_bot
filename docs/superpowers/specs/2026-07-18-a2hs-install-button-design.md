# Add-to-Home-Screen Install Button (Cabinet)

**Date:** 2026-07-18
**Status:** Approved

## Problem

Users open the cabinet through the browser every time. The PWA plumbing (manifest, icons, `display: standalone`) already exists in `web/static/`, but nothing in the UI invites the user to install. We want visible entry points in the личный кабинет that trigger installation ("добавить значок на главный экран").

## Goal

Two entry points (approved as variant B + C from mockups):

1. **Banner** in the cabinet dashboard — reach: seen by everyone who opens the cabinet, dismissible forever.
2. **Header icon** in `AppHeader` next to the notifications bell — a compact always-available entry point that shares the banner's dismissal (dismissing one hides both).

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
- `.gitignore` — ignore the local `docker-compose.override.yml` (dev-only statics bind mount; must never reach prod)

`manifest.json` needs no changes: the FastAPI app serves the SPA from `/` (`web/main.py` `spa_fallback`), so `start_url: "/"` opens the cabinet.

---

## Visibility matrix

| Environment | Detection signal | Banner | Header icon | Click action |
|---|---|---|---|---|
| Running as installed app | `display-mode: standalone` or `navigator.standalone` | hidden | hidden | — |
| Chromium, installable | `beforeinstallprompt` captured | shown unless dismissed | shown unless dismissed | `prompt()` → native dialog |
| Chromium, dialog declined | prompt consumed, no `appinstalled` | still shown | still shown | no-op until event re-fires |
| Chromium, installed | no `beforeinstallprompt` / `appinstalled` fired | hidden | hidden | — |
| iOS Safari (also Chrome/Firefox on iOS) | iPhone/iPad UA **with** `Safari` token | shown unless dismissed | shown unless dismissed | open instructions sheet |
| iOS in-app WebView (Telegram, VK, …) | iPhone/iPad UA **without** `Safari` token | hidden | hidden | — |
| Other (Firefox desktop, desktop Safari, …) | no prompt event, not iOS | hidden | hidden | — |

The in-app WebView row matters: the Telegram bot is this product's main funnel, and Telegram's iOS WKWebView matches `/iphone/i` but has no share-sheet path to the home screen — showing Safari instructions there would be a dead end. The `Safari`-token heuristic errs on the safe side: worst case is no button, never broken instructions.

Dismissal semantics: the banner ✕ and the sheet's "Готово, добавил" both call `dismiss()`, which hides **both** the banner and the header icon (they share the `isDismissed()` gate). Closing the sheet without committing (Escape, overlay tap, "Закрыть") does not dismiss — the entry points stay. `appinstalled` clears the dismissed flag, so after an uninstall the UI can return.

Known iOS limitation (accepted): Safari cannot tell whether the icon is already on the home screen while browsing, and it never fires `appinstalled`. A user who added the icon manually and never dismissed the prompt sees it once; "Готово, добавил" and the ✕ hide it forever. If that user later removes the home-screen icon, the prompt does not re-surface on iOS (no install signal to clear the flag) — accepted.

Ultra-narrow exception: on viewports ≤359px the header icon is hidden entirely (`@media (max-width: 359px)`) — measured at 320px the header row (logo + icon + bell + theme toggle + burger) overflows and clips the burger. The cabinet banner remains the entry point at these widths.

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

State resolution order (a debug override runs first: `localStorage.a2hs_force = '<state>'` forces any state — required to test the iOS sheet in DevTools, where Chrome fires `beforeinstallprompt` regardless of the emulated UA):

1. `installed` — `matchMedia('(display-mode: standalone)').matches || navigator.standalone === true`, or `appinstalled` event fired this session.
2. `installable` — `beforeinstallprompt` captured, **or already consumed by `prompt()` this session** — after a declined native dialog the UI must not vanish from under the user.
3. `ios` — iPhone/iPad UA (incl. iPadOS masquerading as Mac: `platform === 'MacIntel' && maxTouchPoints > 1`) **and** UA contains the `Safari` token (excludes in-app WebViews).
4. `unavailable` — everything else.

Note: on Chromium `beforeinstallprompt` arrives asynchronously (often a second or two after load), so state starts as `unavailable` and flips to `installable` — this is why components subscribe instead of reading once.

We do **not** call `e.preventDefault()` on `beforeinstallprompt`. It is only needed to suppress Chrome's own ambient install UI (mini-infobar), and our replacement entry points are login-gated — guests would lose the native affordance and get nothing back. A logged-in Android user may see both the mini-infobar and our banner; accepted. The event reference works without `preventDefault`.

`prompt()` semantics: the captured event is single-use — consume the reference, call `.prompt()`, resolve with `userChoice`. Sync throws, a rejected `prompt()` promise, and a missing/rejected `userChoice` are all swallowed to `null`, so callers never see an unhandled rejection or exception. On accept, `appinstalled` flips the state to `installed`, clears the dismissed flag, and all UI hides. On decline the state stays `installable` and a further click is a no-op until Chromium re-fires the event (typically next navigation) — honest platform limitation.

`localStorage` unavailable (private mode) → `dismiss()` keeps the flag in memory: banner hides for the session, reappears next visit. Acceptable.

### 2. `web/static/components/InstallPrompt.jsx`

- `useA2HS()` — hook: `{ state, dismissed }`, subscribes to `window.a2hs` on mount and forces one re-render right after subscribing (an event may fire in the render-to-subscribe gap and would otherwise be lost). If `window.a2hs` is absent (script 404 during a partial deploy, blocked by an extension), returns `'unavailable'` instead of throwing — a missing install button must not blank the SPA.
- `InstallBanner` — card for the cabinet. Visible when `(state === 'installable' || state === 'ios') && !dismissed`. App icon, title «Добавьте авито.пф на главный экран», subtitle «Быстрый доступ к заказам и балансу — в одно касание», primary button «Установить», ✕ in the corner (→ `a2hs.dismiss()`). The banner reserves right padding so the ✕ never overlaps the CTA.
- `InstallHeaderButton` — icon button for the header. Visible when `(state === 'installable' || state === 'ios') && !dismissed` — the same gate as the banner, so ✕ / «Готово, добавил» hide it too. `title="Добавить на главный экран"`.
- `InstallGuideSheet` — iOS instructions. Mounted once at app root; opened by CustomEvent `a2hs-open-guide` (same pattern as `support-chat-send`). Bottom sheet on mobile, centered dialog on desktop (no open/close animation — appears instantly). Three steps: «Поделиться» **в панели браузера** (wording covers both Safari and Chrome/Firefox on iOS) → «На экран “Домой”» → «Добавить». Ghost button «Готово, добавил» (→ `dismiss()` + close), closes on overlay click.

Click routing (shared handler): `state === 'installable'` → `a2hs.prompt()`; `state === 'ios'` → `window.dispatchEvent(new CustomEvent('a2hs-open-guide'))`.

### 3. Mount points

- `Cabinet.jsx` — `<InstallBanner />` as the first child of `.container`, above the greeting/balance top-row. Full-width card.
- `AppHeader.jsx` — `<InstallHeaderButton />` immediately left of `<NotificationsBell />`; rendered only when `isApp && user && !adminMode`. There is a single `.header__actions` group (~line 115) serving both breakpoints — one mount point.
- `app.jsx` — `<InstallGuideSheet />` mounted at root alongside `SupportChat`.
- `index.html` — `<script src="/a2hs.js">` after `api.js`; `InstallPrompt.jsx` script tag before `AppHeader.jsx` (dependency order).

### 4. Styles (`platform.css`)

New block near other component styles: `.a2hs-banner`, `.a2hs-header-btn`, `.a2hs-sheet` (+ overlay). Theme via existing CSS vars only (`--surface`, `--border`, `--primary`, `--text-*`) — must look right in light and dark. Breakpoints: banner is a normal card on both; sheet is bottom-anchored on mobile, centered dialog from `min-width: 769px` — the stylesheet's single existing 768/769px cut. One deliberate exception: `max-width: 359px` hides the header icon (see the ultra-narrow note in the visibility section). Per project rule, verify on mobile AND desktop — including the header icon in the cramped mobile header.

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
   ├─ installable → a2hs.prompt() ──► native dialog
   │      ├─ accept → appinstalled → state 'installed' → all UI hides
   │      └─ decline → state stays 'installable', UI stays
   │                   (further clicks no-op until Chromium re-fires the event)
   └─ ios → CustomEvent 'a2hs-open-guide' ──► sheet with 3 steps
                                                  ├─ «Готово, добавил» → dismiss() → banner hidden forever
                                                  └─ close/overlay → nothing persisted
banner ✕ / «Готово, добавил» → dismiss() → banner AND header icon hidden
                                            (appinstalled later clears the flag)
```

---

## Testing

No JS test infrastructure exists (components are Babel-in-browser, Python tests only). Verification is manual, against a checklist:

0. Statics workflow: the api image `COPY`s the code and mounts only `./storage`, so browser checks need either a rebuild (`docker compose up -d --build`) after each edit, or the local git-ignored `docker-compose.override.yml` mounting `./web/static` (Task 1 of the plan sets it up) — then plain F5 suffices.
1. Chrome desktop: banner + header icon appear once `beforeinstallprompt` fires; «Установить» opens the native dialog; **declining keeps both visible** (further clicks are no-ops until the event re-fires); accepting hides both immediately (`appinstalled`); relaunch in the installed window shows neither (standalone). Uninstall via chrome://apps afterwards.
2. iOS sheet in DevTools: `localStorage.setItem('a2hs_force', 'ios')` + reload — plain iPhone-UA emulation is NOT enough, Chrome fires `beforeinstallprompt` regardless and `installable` wins. Banner + icon visible; click opens the sheet (instantly, no animation; page behind is scroll-locked); «Готово, добавил» hides BOTH banner and header icon permanently (survives reload); Escape/«Закрыть»/overlay just close the sheet without dismissing. Clean up: `localStorage.removeItem('a2hs_force')`.
3. Real iPhone Safari before deploy: same flow end-to-end (emulation cannot exercise the real share sheet).
4. ✕ on the banner: hidden, survives reload; the ✕ must not overlap the «Установить» button (aim-click test near the CTA's top-right corner).
5. Negative cases: Firefox desktop — nothing rendered; forced in-app WebView (`a2hs_force = 'unavailable'`, or a real Telegram iOS client) — nothing rendered.
6. Both themes (light/dark), both breakpoints (mobile/desktop) for banner, sheet AND header icon — including the cramped 320–375px mobile header on an admin account (admin toggle + install icon + bell + theme toggle in one row).
7. Full Python suite in Docker: `docker compose exec api python -m pytest` from the worktree root. Never hardcode a container name — compose derives it from the project directory, so the main checkout's `original_avito_pf_bot-api-1` is a different (stale) container.
