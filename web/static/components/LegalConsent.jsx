// Controlled component: two required consent checkboxes (privacy + offer).
// Parent owns state; component is pure.
function LegalConsent({
  privacyChecked,
  offerChecked,
  onPrivacyChange,
  onOfferChange,
  disabled = false,
  style = {},
}) {
  const rowStyle = {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    fontSize: '0.8125rem',
    color: 'var(--text-2)',
    lineHeight: 1.5,
    cursor: disabled ? 'not-allowed' : 'pointer',
    userSelect: 'none',
  };
  const boxStyle = {
    marginTop: 2,
    flexShrink: 0,
    cursor: disabled ? 'not-allowed' : 'pointer',
    accentColor: 'var(--primary)',
  };
  const linkStyle = { color: 'var(--primary)', fontWeight: 600 };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, ...style }}>
      <label style={rowStyle}>
        <input
          type="checkbox"
          checked={privacyChecked}
          onChange={e => onPrivacyChange(e.target.checked)}
          disabled={disabled}
          style={boxStyle}
        />
        <span>
          Я согласен(на) с{' '}
          <a href="/privacy" target="_blank" rel="noopener noreferrer" style={linkStyle}>
            Политикой конфиденциальности
          </a>
        </span>
      </label>
      <label style={rowStyle}>
        <input
          type="checkbox"
          checked={offerChecked}
          onChange={e => onOfferChange(e.target.checked)}
          disabled={disabled}
          style={boxStyle}
        />
        <span>
          Я ознакомлен(а) и согласен(на) с условиями{' '}
          <a href="/offer" target="_blank" rel="noopener noreferrer" style={linkStyle}>
            Публичной оферты
          </a>
        </span>
      </label>
    </div>
  );
}

Object.assign(window, { LegalConsent });
