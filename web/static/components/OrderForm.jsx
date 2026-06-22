// PF Order Form — 3-step wizard (params → auth choice → payment picker)
// Used both for authenticated users (skip step 2) and guests.
const { useState: useOrderState, useEffect: useOrderEffect } = React;

function parseAvitoUrls(text) {
  if (!text) return [];
  // Переводы строк → пробелы. Так \S+ regex останавливается на границе строки,
  // и две отдельные ссылки в столбик не склеятся в один матч.
  // (Раньше нормализация СТИРАЛА \n между \S → два URL склеивались в один,
  //  split('?')[0] оставлял только первый.)
  const normalized = text.replace(/[\r\n]+/g, ' ');
  const raw = normalized.match(/https?:\/\/(?:(?:www|m)\.)?avito\.ru\/\S+/g) || [];
  const seen = new Set();
  return raw
    .map(u => u.replace(/["')\].,;]+$/, '').split('?')[0])
    .filter(u => { if (seen.has(u)) return false; seen.add(u); return true; });
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

// Маленькая info-подсказка: иконка «i» + поповер по клику (работает и на тач-экранах).
function InfoHint({ text }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!open) return;
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);
  return (
    <span ref={ref} style={{ position: 'relative', display: 'inline-flex' }}>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen(v => !v); }}
        aria-label="Подробнее"
        style={{
          width: 18, height: 18, borderRadius: '50%',
          border: `1.5px solid ${open ? 'var(--primary)' : 'var(--text-3)'}`,
          background: 'transparent', color: open ? 'var(--primary)' : 'var(--text-3)',
          cursor: 'pointer', fontSize: '0.72rem', fontWeight: 700, lineHeight: 1,
          fontFamily: 'Georgia, "Times New Roman", serif', fontStyle: 'italic',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0, padding: 0,
        }}
      >i</button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute', top: 'calc(100% + 8px)', left: 0, zIndex: 100,
            width: 280, maxWidth: '75vw',
            background: 'var(--surface)', color: 'var(--text-2)',
            border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
            boxShadow: 'var(--shadow-lg)', padding: '10px 12px',
            fontSize: '0.75rem', lineHeight: 1.55, fontWeight: 400,
            textAlign: 'left', whiteSpace: 'normal', cursor: 'default',
          }}
        >
          {text}
        </div>
      )}
    </span>
  );
}

function OrderFormPage({ user, balance, prefilledFrom, onNavigate, onOrderPlaced }) {
  // Step 1 fields
  const [inputText, setInputText] = useOrderState('');
  const [links, setLinks] = useOrderState(() => Array.isArray(prefilledFrom?.links) ? prefilledFrom.links : []);
  // Preview meta for each URL — survives removeLink so re-paste is instant.
  // Shape: { [url]: { status: 'loading'|'ok'|'not_found'|'fetch_failed', image_url?, title? } }
  const [linkMeta, setLinkMeta] = useOrderState({});
  // fixCount = views per day
  const [fixCount, setFixCount] = useOrderState(() => Number(prefilledFrom?.fix_count) || 30);
  // For prefilled flow days is deliberately blank per plan
  const [days, setDays] = useOrderState(() => {
    if (prefilledFrom) return prefilledFrom.days != null ? Number(prefilledFrom.days) : '';
    return 7;
  });
  const [contacts, setContacts] = useOrderState(() => !!prefilledFrom?.contacts);
  // start_date: ISO "YYYY-MM-DD". По умолчанию = сегодня (Москва).
  const _todayISO = () => {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  };
  const [startDate, setStartDate] = useOrderState(() => prefilledFrom?.start_date || _todayISO());

  // Wizard state
  const [step, setStep] = useOrderState(1);
  const [loading, setLoading] = useOrderState(false);
  // ref-guard от двойного сабмита: setLoading(true) применяется на следующем
  // рендере, а быстрый dbl-click успевает выстрелить второй submitToBackend.
  const submittingRef = React.useRef(false);
  const [error, setError] = useOrderState('');
  const [pricePerUnit, setPricePerUnit] = useOrderState(6);

  // Step 2 state (guest auth choice)
  const [showPhoneInput, setShowPhoneInput] = useOrderState(false);
  const [guestPhone, setGuestPhone] = useOrderState('');

  // Step 3 state
  const [createdOrder, setCreatedOrder] = useOrderState(null); // { order_id, price, available_methods }

  // For prefilled (repeat-order) flow: kick off preview fetch on mount so the
  // restored cards don't stay on shimmer forever. Paste flow handles itself via
  // handleInputChange; this is the only entry point that bypasses paste.
  useOrderEffect(() => {
    const prefilled = Array.isArray(prefilledFrom?.links) ? prefilledFrom.links : [];
    if (!prefilled.length) return;
    setLinkMeta(prev => {
      const next = { ...prev };
      for (const u of prefilled) {
        if (!next[u]) next[u] = { status: 'loading' };
      }
      return next;
    });
    _fetchPreviewsAndMerge(prefilled);
  }, []);

  useOrderEffect(() => {
    api.get('/api/orders/pf/price').then(data => {
      if (!data.__unauthorized) setPricePerUnit(data.price_per_unit || 6);
    }).catch(() => {});
  }, []);

  const urlCount = links.length;
  const daysNum = parseInt(days, 10) || 0;
  const totalPrice = urlCount > 0 ? fixCount * daysNum * urlCount * pricePerUnit : 0;

  const handleInputChange = e => {
    const val = e.target.value;
    const parsed = parseAvitoUrls(val);
    const toAdd = parsed.filter(u => !links.includes(u));
    if (toAdd.length) {
      setLinks(prev => [...prev, ...toAdd]);
      // Mark new URLs as loading (skip URLs we already have meta for — re-add case).
      const newlyLoading = toAdd.filter(u => !linkMeta[u]);
      if (newlyLoading.length) {
        setLinkMeta(prev => {
          const next = { ...prev };
          for (const u of newlyLoading) next[u] = { status: 'loading' };
          return next;
        });
        _fetchPreviewsAndMerge(newlyLoading);
      }
    }
    setInputText(val);
  };

  const _fetchPreviewsAndMerge = async (urls) => {
    try {
      const data = await api.post('/api/orders/links/preview', { urls });
      if (!data || !Array.isArray(data.previews)) return;
      setLinkMeta(prev => {
        const next = { ...prev };
        for (const p of data.previews) {
          next[p.url] = {
            status: p.status,
            image_url: p.image_url || null,
            title: p.title || null,
          };
        }
        return next;
      });
    } catch (err) {
      // Network/server error — flip the still-loading entries to fetch_failed so
      // the card renders the placeholder instead of a perpetual skeleton.
      // Best-effort feature, not blocking — the form still submits.
      console.warn('[link-preview] fetch failed', err);
      setLinkMeta(prev => {
        const next = { ...prev };
        for (const u of urls) {
          if (next[u] && next[u].status === 'loading') {
            next[u] = { status: 'fetch_failed' };
          }
        }
        return next;
      });
    }
  };

  const removeLink = url => setLinks(prev => prev.filter(u => u !== url));

  const submitToBackend = async (phoneArg) => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setLoading(true); setError('');
    try {
      const data = await api.post('/api/orders/pf', {
        links,
        days: parseInt(days, 10),
        fix_count: fixCount,
        contacts,
        agreed_privacy: true,  // приняты автоматически — текст внизу формы
        agreed_offer: true,
        phone: phoneArg || null,
        start_date: startDate || null,
      });
      setCreatedOrder(data);
      setStep(3);
    } catch (e) {
      setError(e.message || 'Не удалось создать заказ');
    } finally {
      setLoading(false);
      submittingRef.current = false;
    }
  };

  const handleNextFromStep1 = () => {
    if (urlCount === 0) return setError('Добавьте хотя бы одну ссылку на объявление');
    if (!daysNum || daysNum < 1) return setError('Укажите количество дней (от 1)');
    setError('');
    if (user) {
      submitToBackend(null);
    } else {
      setStep(2);
    }
  };

  const handleGoToAuth = () => {
    try {
      sessionStorage.setItem('order_prefill', JSON.stringify({
        links,
        days: daysNum || null,
        fix_count: fixCount,
        contacts,
      }));
    } catch (_) {}
    onNavigate('auth');
  };

  const handleGuestSubmit = () => {
    if (!guestPhone || guestPhone.replace(/\D/g, '').length < 10) {
      return setError('Введите корректный номер телефона');
    }
    setError('');
    submitToBackend(guestPhone);
  };

  const handlePay = async (method) => {
    if (!createdOrder) return;
    if (submittingRef.current) return;
    submittingRef.current = true;
    setLoading(true); setError('');
    try {
      const data = await api.post(`/api/orders/pf/${createdOrder.order_id}/pay`, { method });
      if (method === 'balance') {
        onOrderPlaced && onOrderPlaced(createdOrder.price);
        onNavigate('order-detail', { order_id: createdOrder.order_id });
      } else if (method === 'yookassa') {
        if (data && data.confirmation_url) {
          window.location.href = data.confirmation_url;
        } else {
          setError('Не удалось получить ссылку оплаты');
        }
      }
    } catch (e) {
      if (e.status === 400) setError(e.message || 'Недостаточно средств');
      else setError(e.message || 'Ошибка оплаты');
    } finally {
      setLoading(false);
      submittingRef.current = false;
    }
  };

  // ----- Step 3: payment picker -----
  if (step === 3 && createdOrder) {
    const methods = createdOrder.available_methods || [];
    return (
      <div className="page-wrap">
        <div className="container" style={{ maxWidth: 560, padding: '28px 20px 80px' }}>
          <h1 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: 6 }}>Заказ создан</h1>
          <p style={{ color: 'var(--text-2)', marginBottom: 18 }}>
            Заказ <strong>#{createdOrder.order_id}</strong> · сумма к оплате{' '}
            <strong style={{ color: 'var(--primary)' }}>{createdOrder.price.toLocaleString('ru-RU')} ₽</strong>
          </p>
          {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}
          <div className="card" style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-2)', marginBottom: 4 }}>
              Выберите способ оплаты
            </div>
            {methods.includes('balance') && (
              <button
                className="btn btn--primary btn--lg btn--full"
                onClick={() => handlePay('balance')}
                disabled={loading}
              >
                {loading ? 'Оплачиваем...' : 'Оплатить с баланса'}
              </button>
            )}
            {methods.includes('yookassa') && (
              <button
                className="btn btn--secondary btn--lg btn--full"
                onClick={() => handlePay('yookassa')}
                disabled={loading}
              >
                {loading ? 'Перенаправляем...' : 'Оплатить картой (ЮKassa)'}
              </button>
            )}
            {methods.length === 0 && (
              <div className="alert alert--error">Нет доступных способов оплаты</div>
            )}
          </div>
          <div style={{ marginTop: 14, textAlign: 'center' }}>
            <button
              className="btn btn--ghost btn--sm"
              onClick={() => onNavigate('order-detail', { order_id: createdOrder.order_id })}
            >
              Перейти к заказу
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ----- Step 2: guest auth choice -----
  if (step === 2) {
    return (
      <div className="page-wrap">
        <div className="container" style={{ maxWidth: 560, padding: '28px 20px 80px' }}>
          <button className="order-back" onClick={() => { setError(''); setStep(1); }}>← Назад к параметрам</button>
          <h1 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: 6 }}>Как оформить заказ?</h1>
          <p style={{ color: 'var(--text-2)', marginBottom: 18 }}>
            Сумма: <strong style={{ color: 'var(--primary)' }}>{totalPrice.toLocaleString('ru-RU')} ₽</strong>
          </p>
          {error && <div className="alert alert--error" style={{ marginBottom: 12 }}>{error}</div>}
          <div className="card" style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {!showPhoneInput ? (
              <>
                <button
                  className="btn btn--primary btn--lg btn--full"
                  onClick={() => { setError(''); setShowPhoneInput(true); }}
                  disabled={loading}
                >
                  Быстрый заказ по телефону
                </button>
                <div style={{ textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-3)' }}>или</div>
                <button
                  className="btn btn--secondary btn--lg btn--full"
                  onClick={handleGoToAuth}
                  disabled={loading}
                >
                  У меня есть аккаунт — войти
                </button>
              </>
            ) : (
              <>
                <div className="form-field">
                  <label className="form-label">Номер телефона</label>
                  <input
                    className="input"
                    type="tel"
                    inputMode="tel"
                    placeholder="+7 900 123-45-67"
                    value={guestPhone}
                    onChange={e => setGuestPhone(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleGuestSubmit()}
                    autoFocus
                  />
                  <div className="form-hint">На этот номер привяжем заказ — потом сможете войти по SMS</div>
                </div>
                <button
                  className="btn btn--primary btn--lg btn--full"
                  onClick={handleGuestSubmit}
                  disabled={loading}
                >
                  {loading ? 'Создаём заказ...' : 'Создать заказ'}
                </button>
                <button
                  className="btn btn--ghost btn--sm btn--full"
                  onClick={() => { setShowPhoneInput(false); setError(''); }}
                  disabled={loading}
                >
                  ← Назад к выбору
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ----- Step 1: parameters -----
  const noUrlsWarning = inputText.length > 5 && parseAvitoUrls(inputText).length === 0 && urlCount === 0;

  return (
    <div className="page-wrap">
      <div className="order-page">
        <div className="container" style={{ maxWidth: 900 }}>
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
                    rows={4}
                    placeholder={"Вставьте ссылки или любой текст со ссылками Авито"}
                    value={inputText}
                    onChange={handleInputChange}
                    style={{ resize: 'none' }}
                  />

                  {noUrlsWarning && (
                    <div style={{ fontSize: '0.8rem', color: 'var(--status-cancel-text)', marginTop: 6 }}>
                      ⚠ Авито-ссылки не найдены
                    </div>
                  )}

                  {links.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
                        Добавленные объявления
                      </div>
                      {links.map(url => (
                        <LinkCard key={url} url={url} meta={linkMeta[url]} onRemove={removeLink} />
                      ))}
                    </div>
                  )}

                  {urlCount === 0 && (
                    <div className="form-hint" style={{ marginTop: 6 }}>
                      Каждое уникальное объявление — отдельная строка в счёте
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* RIGHT */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="card" style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>
                <SliderField
                  label="Просмотров в день"
                  min={1} max={200} step={1}
                  value={fixCount} onChange={setFixCount}
                  hint="Рекомендуем 15–50 для начала"
                />
                <div style={{ height: 1, background: 'var(--border)' }} />
                <SliderField
                  label="Количество дней"
                  min={1} max={90} step={1} suffix=" дн."
                  value={daysNum || 1} onChange={setDays}
                  hint="Лучше крутить непрерывно от 7 дней"
                />
                <div style={{ height: 1, background: 'var(--border)' }} />
                <div className="form-field">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                    <label className="form-label" style={{ margin: 0 }}>Дата старта</label>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>можно с сегодня</span>
                  </div>
                  <input
                    type="date"
                    className="input"
                    value={startDate}
                    min={_todayISO()}
                    onChange={e => setStartDate(e.target.value)}
                  />
                  <div className="form-hint">Когда начать показы — исполнитель стартует в этот день</div>
                </div>
                <div style={{ height: 1, background: 'var(--border)' }} />
                <div className="toggle-row" onClick={() => setContacts(v => !v)} style={{ userSelect: 'none', cursor: 'pointer' }}>
                  <div className={`toggle${contacts ? ' on' : ''}`} />
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div className="toggle-label" style={{ fontSize: '0.875rem' }}>Запросы контактов</div>
                      <InfoHint text="Контакты приходят в любом процентном соотношении к просмотрам — вплоть до полного отсутствия. Большое число контактов рискованно: для Авито это выглядит как накрутка и может навредить объявлению, поэтому их количество мы не гарантируем. Просмотры же идут 1:1 с заказом — их объём мы гарантируем, иначе вернём деньги." />
                    </div>
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
                    { label: 'Просмотров в день', val: fixCount },
                    { label: 'Количество дней', val: daysNum || '—' },
                    { label: 'Объявлений', val: urlCount },
                    { label: 'Цена за просмотр', val: `${pricePerUnit} ₽` },
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
              </div>

              <button
                className="btn btn--primary btn--lg btn--full desktop-only"
                onClick={handleNextFromStep1}
                disabled={loading || urlCount === 0}
                style={{ fontSize: '0.9375rem' }}
              >
                {loading ? 'Создаём заказ...' : (user ? 'Создать заказ' : 'Далее')}
              </button>

              {/* Согласия — мелким текстом под кнопкой */}
              <div style={{ fontSize: '0.7rem', color: 'var(--text-3)', lineHeight: 1.5, textAlign: 'center' }}>
                Продолжая, вы соглашаетесь с{' '}
                <a href="/privacy" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-3)', textDecoration: 'underline' }}>
                  Политикой конфиденциальности
                </a>
                {' '}и{' '}
                <a href="/offer" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-3)', textDecoration: 'underline' }}>
                  Публичной офертой
                </a>
              </div>
            </div>
          </div>
        </div>

        {/* Mobile sticky footer */}
        <div className="order-sticky-footer">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-2)' }}>Итого:</span>
            <span style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--primary)' }}>{totalPrice.toLocaleString('ru-RU')} ₽</span>
          </div>
          <button className="btn btn--primary btn--lg btn--full" onClick={handleNextFromStep1} disabled={loading || urlCount === 0}>
            {loading ? 'Создаём...' : (user ? 'Создать заказ' : 'Далее')}
          </button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { OrderFormPage, SliderField });
