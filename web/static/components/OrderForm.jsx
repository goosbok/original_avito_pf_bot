// PF Order Form — two-column layout with real API
const { useState: useOrderState, useEffect: useOrderEffect } = React;

function parseAvitoUrls(text) {
  if (!text) return [];
  const normalized = text.replace(/(?<=\S)[\r\n]+(?=\S)/g, '');
  const raw = normalized.match(/https?:\/\/(?:www\.)?avito\.ru\/\S+/g) || [];
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

function OrderFormPage({ balance, onNavigate, onOrderPlaced }) {
  const [inputText, setInputText] = useOrderState('');
  const [links, setLinks] = useOrderState([]);
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

  const urlCount = links.length;
  const totalPrice = urlCount > 0 ? views * days * urlCount * pricePerUnit : 0;

  const handleInputChange = e => {
    const val = e.target.value;
    const parsed = parseAvitoUrls(val);
    const toAdd = parsed.filter(u => !links.includes(u));
    if (toAdd.length) setLinks(prev => [...prev, ...toAdd]);
    setInputText(val);
  };

  const removeLink = url => setLinks(prev => prev.filter(u => u !== url));

  const handleSubmit = async () => {
    if (urlCount === 0) return setError('Вставьте хотя бы одну ссылку на объявление');
    if (totalPrice > balance) return setError(`Недостаточно средств. Нужно ${totalPrice.toLocaleString('ru-RU')} ₽, на балансе ${balance.toLocaleString('ru-RU')} ₽`);
    setError(''); setLoading(true);
    try {
      await api.post('/api/orders/pf', {
        links,
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

  const noUrlsWarning = inputText.length > 5 && parseAvitoUrls(inputText).length === 0 && urlCount === 0;

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

                  {urlCount > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-2)', marginBottom: 6 }}>
                        Добавленные объявления
                      </div>
                      {links.map((url, i) => (
                        <div key={url} style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, padding: '7px 0', borderBottom: i < links.length - 1 ? '1px solid var(--border)' : 'none' }}>
                          <a
                            href={url} target="_blank" rel="noopener noreferrer"
                            title={url}
                            style={{ flex: '1 1 0', minWidth: 0, fontSize: '0.775rem', fontFamily: 'monospace', color: 'var(--primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textDecoration: 'none' }}
                          >
                            {url.length > 60 ? url.slice(0, 60) + '…' : url}
                          </a>
                          <button
                            onClick={() => removeLink(url)}
                            style={{ flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--status-cancel-text)', fontWeight: 700, fontSize: '1.1rem', padding: '0 4px', lineHeight: 1 }}
                          >
                            −
                          </button>
                        </div>
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
