// a2hs.js — Add-to-Home-Screen state helper.
// Plain JS loaded BEFORE the React/Babel scripts: `beforeinstallprompt`
// can fire while components are still compiling, so capture happens here.
//
// States:
//   'installed'   — running standalone, or `appinstalled` fired this session
//   'installable' — Chromium install prompt available (or already shown and
//                   declined this session — UI must not vanish under the user)
//   'ios'         — iPhone/iPad browser with a share-sheet path to the home
//                   screen (Safari, Chrome/Firefox on iOS)
//   'unavailable' — everything else, incl. iOS in-app WebViews (Telegram,
//                   VK, …) where the share-sheet instructions can't be followed
//
// Debug override (needed to test the iOS sheet in DevTools — Chrome fires
// beforeinstallprompt even with an emulated iPhone UA, so 'ios' is otherwise
// unreachable there): localStorage.setItem('a2hs_force', 'ios')
(function () {
  'use strict';
  var deferredPrompt = null;
  var promptConsumed = false; // native dialog shown; keep UI until installed
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

  function isIosSafari() {
    var ua = navigator.userAgent;
    var ios = /iphone|ipad|ipod/i.test(ua)
      // iPadOS ≥13 reports itself as a Mac, but Macs have no touch points
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    // In-app WebViews lack the Safari UA token; real browsers keep it.
    return ios && /safari/i.test(ua);
  }

  // No e.preventDefault(): it would suppress Chrome's own install
  // mini-infobar, and our entry points are login-gated — guests would get
  // nothing in return. The event reference works without it.
  window.addEventListener('beforeinstallprompt', function (e) {
    deferredPrompt = e;
    notify();
  });

  window.addEventListener('appinstalled', function () {
    deferredPrompt = null;
    installedThisSession = true;
    // Clear any prior dismissal: once installed the flag is meaningless, and
    // leaving it set would keep both entry points hidden forever if the user
    // later uninstalls the app.
    memDismissed = false;
    try { localStorage.removeItem('a2hs_dismissed'); } catch (_) {}
    notify();
  });

  window.a2hs = {
    getState: function () {
      var forced = null;
      try { forced = localStorage.getItem('a2hs_force'); } catch (_) {}
      if (forced && /^(installed|installable|ios|unavailable)$/.test(forced)) return forced;
      if (installedThisSession || isStandalone()) return 'installed';
      if (deferredPrompt || promptConsumed) return 'installable';
      if (isIosSafari()) return 'ios';
      return 'unavailable';
    },
    // The captured event is single-use. On decline the state deliberately
    // stays 'installable' (via promptConsumed) so both entry points remain
    // visible; a further click is a no-op until Chromium re-fires the event
    // (typically next navigation). Never rejects — errors resolve as null.
    // Sync throws and a rejected prompt() promise are swallowed too: the
    // event is spent either way, promptConsumed keeps the UI visible.
    prompt: function () {
      if (!deferredPrompt) return Promise.resolve(null);
      var p = deferredPrompt;
      deferredPrompt = null;
      promptConsumed = true;
      var shown;
      try {
        shown = p.prompt();
      } catch (_) {
        notify();
        return Promise.resolve(null);
      }
      if (shown && shown.catch) shown.catch(function () {});
      // Some Chromium variants expose prompt() without a userChoice promise —
      // guard the access so this contract truly never throws.
      var choice = p.userChoice;
      if (!choice || typeof choice.then !== 'function') {
        notify();
        return Promise.resolve(null);
      }
      return choice
        .catch(function () { return null; })
        .then(function (c) { notify(); return c || null; });
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
