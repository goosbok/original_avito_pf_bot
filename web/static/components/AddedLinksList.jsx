// AddedLinksList — render the "Добавленные объявления" list shared by
// OrderForm and GuestOrderForm. Renders nothing when the list is empty.
function AddedLinksList({ links, onRemove }) {
  if (!links || links.length === 0) return null;
  return (
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
            onClick={() => onRemove(url)}
            style={{ flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--status-cancel-text)', fontWeight: 700, fontSize: '1.1rem', padding: '0 4px', lineHeight: 1 }}
          >
            −
          </button>
        </div>
      ))}
    </div>
  );
}

Object.assign(window, { AddedLinksList });
