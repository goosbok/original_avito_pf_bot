// InstallPrompt — add-to-home-screen entry points: cabinet banner,
// header icon button, iOS instructions sheet.
// State machine lives in /a2hs.js (plain JS, loaded before React).
const { useState: useA2hsState, useEffect: useA2hsEffect } = React;

function useA2HS() {
  const [, force] = useA2hsState(0);
  useA2hsEffect(() => {
    if (!window.a2hs) return undefined;
    const unsub = window.a2hs.subscribe(() => force(x => x + 1));
    // Re-check once: beforeinstallprompt may have fired in the gap between
    // the first render and this effect — that notify() had no subscribers.
    force(x => x + 1);
    return unsub;
  }, []);
  // No hard dependency on the plain script: if /a2hs.js failed to load
  // (partial deploy, blocking extension), render no install UI instead of
  // throwing and blanking the whole SPA.
  if (!window.a2hs) return { state: 'unavailable', dismissed: true };
  return { state: window.a2hs.getState(), dismissed: window.a2hs.isDismissed() };
}

function a2hsActivate(state) {
  if (state === 'installable') window.a2hs.prompt(); // never rejects (caught inside a2hs.js)
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
            {' '}в панели браузера
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
