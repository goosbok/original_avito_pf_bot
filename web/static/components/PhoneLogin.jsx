// PhoneLogin — SMS-OTP login flow. Two-step: phone → code.
// Calls onSuccess(jwt) on successful verify.
function PhoneLogin({ onSuccess }) {
  const [step, setStep] = React.useState('phone');
  const [phone, setPhone] = React.useState('');
  const [code, setCode] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');
  const [success, setSuccess] = React.useState('');
  const [resendIn, setResendIn] = React.useState(0);

  // Countdown ticker — clean up on unmount.
  React.useEffect(() => {
    if (resendIn <= 0) return undefined;
    const t = setTimeout(() => setResendIn(s => Math.max(0, s - 1)), 1000);
    return () => clearTimeout(t);
  }, [resendIn]);

  const isValidPhone = (raw) => {
    const cleaned = (raw || '').replace(/[^\d+]/g, '');
    if (/^\+\d{10,15}$/.test(cleaned)) return true;
    if (/^\d{10,11}$/.test(cleaned)) return true;
    return false;
  };

  const requestCode = async () => {
    if (!phone) return setError('Введите номер телефона');
    if (!isValidPhone(phone)) return setError('Введите номер, например +79001234567');
    setLoading(true); setError(''); setSuccess('');
    try {
      await api.post('/api/auth/phone/request-code', { phone });
      setStep('code');
      setSuccess('Код отправлен по SMS');
      setResendIn(60);
    } catch (e) {
      if (e.status === 429) {
        setError('Слишком много запросов, подождите');
        // If retry_after is provided, use it as countdown so UI matches.
        if (e.retry_after) setResendIn(Number(e.retry_after));
      } else if (e.status === 400) {
        setError(e.message || 'Неверный формат телефона');
      } else if (e.status === 502) {
        setError('Не удалось отправить SMS, попробуйте позже');
      } else {
        setError(e.message || 'Ошибка отправки кода');
      }
    } finally {
      setLoading(false);
    }
  };

  const verify = async () => {
    if (!code || code.length < 4) return setError('Введите код из SMS');
    setLoading(true); setError('');
    try {
      const data = await api.post('/api/auth/phone/verify', { phone, code });
      if (data && data.access_token) {
        onSuccess(data.access_token);
      } else {
        setError('Неверный ответ сервера');
      }
    } catch (e) {
      if (e.status === 400) setError(e.message || 'Неверный или истёкший код');
      else setError(e.message || 'Ошибка проверки кода');
    } finally {
      setLoading(false);
    }
  };

  if (step === 'phone') {
    return (
      <div className="auth-form">
        {error && <div className="alert alert--error">{error}</div>}
        <div className="form-field">
          <label className="form-label">Номер телефона</label>
          <input
            className="input"
            type="tel"
            inputMode="tel"
            placeholder="+7 900 123-45-67"
            value={phone}
            onChange={e => setPhone(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !loading && requestCode()}
            autoFocus
          />
          <div className="form-hint">Отправим SMS с 6-значным кодом</div>
        </div>
        <button className="btn btn--primary btn--lg btn--full" onClick={requestCode} disabled={loading}>
          {loading ? 'Отправка...' : 'Получить код'}
        </button>
      </div>
    );
  }

  // step === 'code'
  return (
    <div className="auth-form">
      {error && <div className="alert alert--error">{error}</div>}
      {success && <div className="alert alert--success">{success}</div>}
      <div className="form-field">
        <label className="form-label">6-значный код из SMS</label>
        <input
          className="input"
          placeholder="123456"
          value={code}
          maxLength={6}
          inputMode="numeric"
          onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
          onKeyDown={e => e.key === 'Enter' && !loading && verify()}
          style={{ textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.2em', fontWeight: 700 }}
          autoFocus
        />
        <div className="form-hint">Код отправлен на {phone}. Действителен 5 минут.</div>
      </div>
      <button className="btn btn--primary btn--lg btn--full" onClick={verify} disabled={loading}>
        {loading ? 'Проверка...' : 'Войти'}
      </button>
      <div style={{ textAlign: 'center', fontSize: '0.875rem' }}>
        {resendIn > 0 ? (
          <span style={{ color: 'var(--text-3)' }}>Повторно отправить через {resendIn} сек.</span>
        ) : (
          <>
            <span style={{ color: 'var(--text-3)' }}>Не пришёл код?</span>{' '}
            <span
              onClick={() => { if (!loading) requestCode(); }}
              style={{ color: 'var(--primary)', fontWeight: 600, cursor: loading ? 'default' : 'pointer' }}
            >
              Отправить заново
            </span>
          </>
        )}
      </div>
      <button
        className="btn btn--ghost btn--sm btn--full"
        onClick={() => { setStep('phone'); setCode(''); setError(''); setSuccess(''); }}
        disabled={loading}
      >
        ← Изменить номер
      </button>
    </div>
  );
}

Object.assign(window, { PhoneLogin });
