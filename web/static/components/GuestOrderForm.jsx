// Guest PF Order Form — same as OrderFormPage but no balance, + phone field, direct YooKassa payment
const { useState: useGOFState, useEffect: useGOFEffect } = React;

// parseAvitoUrls is defined locally (not exported from OrderForm.jsx)
function parseGuestAvitoUrls(text) {
  if (!text) return [];
  const normalized = text.replace(/(?<=\S)[\r\n]+(?=\S)/g, '');
  const raw = normalized.match(/https?:\/\/(?:www\.)?avito\.ru\/\S+/g) || [];
  const seen = new Set();
  return raw
    .map(u => u.replace(/["')\].,;]+$/, '').split('?')[0])
    .filter(u => { if (seen.has(u)) return false; seen.add(u); return true; });
}

function GuestOrderForm({ onNavigate }) {
  const [inputText, setInputText] = useGOFState('');
  const [links, setLinks] = useGOFState([]);
  const [views, setViews] = useGOFState(30);
  const [days, setDays] = useGOFState(7);
  const [contacts, setContacts] = useGOFState(false);
  const [startDate, setStartDate] = useGOFState(() => {
    const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().split('T')[0];
  });
  const [phone, setPhone] = useGOFState('');
  const [pricePerUnit, setPricePerUnit] = useGOFState(6);
  const [paymentAvailable, setPaymentAvailable] = useGOFState(true);
  const [loading, setLoading] = useGOFState(false);
  const [error, setError] = useGOFState('');
  const [agreedPrivacy, setAgreedPrivacy] = useGOFState(false);
  const [agreedOffer, setAgreedOffer] = useGOFState(false);
  const consentOk = agreedPrivacy && agreedOffer;

  useGOFEffect(() => {
    api.get('/api/orders/pf/price').then(d => {
      if (!d.__unauthorized) setPricePerUnit(d.price_per_unit || 6);
    }).catch(() => {});
    api.get('/api/guest-orders/payment-available').then(d => {
      if (!d.__unauthorized) setPaymentAvailable(d.available !== false);
    }).catch(() => {});
  }, []);

  const urlCount = links.length;
  const totalPrice = urlCount > 0 ? views * days * urlCount * pricePerUnit : 0;

  const handleInputChange = e => {
    const val = e.target.value;
    const parsed = parseGuestAvitoUrls(val);
    const toAdd = parsed.filter(u => !links.includes(u));
    if (toAdd.length) setLinks(prev => [...prev, ...toAdd]);
    setInputText(val);
  };

  const removeLink = url => setLinks(prev => prev.filter(u => u !== url));

  const handleSubmit = async () => {
    if (!consentOk) return setError('Необходимо принять политику конфиденциальности и оферту');
    if (urlCount === 0) return setError('Вставьте хотя бы одну ссылку на объявление');
    if (!phone.trim()) return setError('Укажите номер телефона');
    if (!paymentAvailable) return setError('Онлайн-оплата временно недоступна');
    setError(''); setLoading(true);
    try {
      const data = await api.post('/api/guest-orders/pf', {
        links,
        days,
        fix_count: views,
        contacts,
        phone: phone.trim(),
        agreed_privacy: agreedPrivacy,
        agreed_offer: agreedOffer,
      });
      window.location.href = data.payment_url;
    } catch (e) {
      setError(e.message || 'Ошибка создания заказа. Попробуйте позже или напишите в поддержку.');
    } finally { setLoading(false); }
  };

  const noUrlsWarning = inputText.length > 5 && parseGuestAvitoUrls(inputText).length === 0 && urlCount === 0;

  return (
    <div className="page-wrap">
      <div className="order-page">
        <div className="container" style={{ maxWidth: 900 }}>

          <button className="order-back" onClick={() => onNavigate('landing')}>← На главную</button>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>Авито ПФ</h1>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-3)' }}>
              Поведенческие факторы · {pricePerUnit} ₽ за просмотр
            </span>
            <span style={{ marginLeft: 'auto', background: 'var(--primary-dim)', color: 'var(--primary)', fontSize: '0.75rem', fontWeight: 700, padding: '3px 10px', borderRadius: 4 }}>
              Без регистрации
            </span>
          </div>

          {!paymentAvailable && (
            <div className="alert alert--error" style={{ marginBottom: 16 }}>
              Онлайн-оплата временно недоступна. Для заказа <a href="https://t.me/avito_pf_otzizi" target="_blank" rel="noopener" style={{ color: 'inherit', fontWeight: 700 }}>напишите в поддержку</a>.
            </div>
          )}
          {error && <div className="alert alert--error" style={{ marginBottom: 16 }}>{error}</div>}

          <div className="order-two-col" style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, alignItems: 'start' }}>

            {/* LEFT */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="card" style={{ padding: '14px 18px', borderLeft: '3px solid var(--primary)' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 700, marginBottom: 5, color: 'var(--text-1)' }}>Рекомендация</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-2)', lineHeight: 1.65 }}>
                  Начните с <strong>15–30 просм./день без контактов</strong> в течение недели.
                  После оживления органики постепенно добавляйте 5–8 контактов.
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
                    placeholder="Вставьте ссылки или любой текст со ссылками Авито"
                    value={inputText}
                    onChange={handleInputChange}
                    style={{ resize: 'none' }}
                  />
                  {noUrlsWarning && (
                    <div style={{ fontSize: '0.8rem', color: 'var(--status-cancel-text)', marginTop: 6 }}>⚠ Авито-ссылки не найдены</div>
                  )}
                  {urlCount > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>Добавленные объявления</div>
                      {links.map((url, i) => (
                        <div key={url} style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, padding: '7px 0', borderBottom: i < links.length - 1 ? '1px solid var(--border)' : 'none' }}>
                          <a href={url} target="_blank" rel="noopener noreferrer" title={url}
                            style={{ flex: '1 1 0', minWidth: 0, fontSize: '0.775rem', fontFamily: 'monospace', color: 'var(--primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textDecoration: 'none' }}>
                            {url.length > 60 ? url.slice(0, 60) + '…' : url}
                          </a>
                          <button onClick={() => removeLink(url)}
                            style={{ flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--status-cancel-text)', fontWeight: 700, fontSize: '1.1rem', padding: '0 4px', lineHeight: 1 }}>
                            −
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  {urlCount === 0 && (
                    <div className="form-hint" style={{ marginTop: 6 }}>Каждое уникальное объявление — отдельная строка в счёте</div>
                  )}
                </div>
              </div>

              {/* Phone field */}
              <div className="card" style={{ padding: '18px 20px' }}>
                <div className="form-field">
                  <label className="form-label">Номер телефона</label>
                  <input
                    type="tel"
                    className="input"
                    placeholder="+7 (999) 000-00-00"
                    value={phone}
                    onChange={e => setPhone(e.target.value)}
                  />
                  <div className="form-hint" style={{ marginTop: 6 }}>
                    Нужен для связи при проблемах с заказом. Назовите его в поддержке — найдём заказ без регистрации.
                  </div>
                </div>
              </div>
            </div>

            {/* RIGHT */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="card" style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>
                <SliderField label="Просмотров в день" min={5} max={500} step={5} value={views} onChange={setViews} hint="Рекомендуем 15–50 для начала" />
                <div style={{ height: 1, background: 'var(--border)' }} />
                <SliderField label="Количество дней" min={1} max={30} step={1} value={days} onChange={setDays} suffix=" дн." hint="Лучше крутить непрерывно от 7 дней" />
                <div style={{ height: 1, background: 'var(--border)' }} />
                <div className="form-field">
                  <label className="form-label">Дата начала</label>
                  <input type="date" className="input" value={startDate} min={new Date().toISOString().split('T')[0]} onChange={e => setStartDate(e.target.value)} />
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
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Стоимость</span>
                  <span style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)', letterSpacing: '-0.03em' }}>{totalPrice.toLocaleString('ru-RU')} ₽</span>
                </div>
                <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {[
                    { label: 'Просмотров в день', val: views },
                    { label: 'Количество дней', val: days },
                    { label: 'Объявлений', val: Math.max(urlCount, 1) },
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

              <LegalConsent
                privacyChecked={agreedPrivacy}
                offerChecked={agreedOffer}
                onPrivacyChange={setAgreedPrivacy}
                onOfferChange={setAgreedOffer}
                disabled={loading}
                style={{ marginTop: 4 }}
              />
              <button
                className="btn btn--primary btn--lg btn--full desktop-only"
                onClick={handleSubmit}
                disabled={loading || urlCount === 0 || !paymentAvailable || !consentOk}
                style={{ fontSize: '0.9375rem' }}
              >
                {loading ? 'Создаём заказ...' : 'Перейти к оплате →'}
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
          <button className="btn btn--primary btn--lg btn--full" onClick={handleSubmit}
            disabled={loading || urlCount === 0 || !paymentAvailable || !consentOk}>
            {loading ? 'Создаём...' : 'Перейти к оплате →'}
          </button>
          {!consentOk && urlCount > 0 && paymentAvailable && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginTop: 6, textAlign: 'center' }}>
              Для оплаты примите оба условия выше
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { GuestOrderForm });
