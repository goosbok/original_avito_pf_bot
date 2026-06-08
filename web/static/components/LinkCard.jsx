// LinkCard — preview card for a pasted Avito URL.
// Replaces the plain text list (AddedLinksList) used previously in OrderForm.
//
// Props:
//   url     — the Avito URL (canonical, already trimmed by parseAvitoUrls)
//   meta    — { status: 'loading'|'ok'|'not_found'|'fetch_failed', image_url?, title? }
//   onRemove — callback when user clicks "×"
//
// States rendered:
//   loading           → skeleton thumb + shimmer title placeholder
//   ok                → <img> from image_url, title shown
//   not_found / fetch_failed → green "A" placeholder, fallback title = url path
function LinkCard({ url, meta, onRemove }) {
  const status = (meta && meta.status) || 'loading';
  const hasImage = status === 'ok' && meta && meta.image_url;
  const titleText = (meta && meta.title) || _urlShortPath(url);

  return (
    <div
      onClick={() => window.open(url, '_blank', 'noopener,noreferrer')}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '8px 10px',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm, 8px)',
        marginBottom: 8,
        background: 'var(--surface)',
        cursor: 'pointer',
        minWidth: 0,
      }}
    >
      <div style={{
        width: 56, height: 56, borderRadius: 8, flexShrink: 0,
        overflow: 'hidden', position: 'relative',
        background: 'linear-gradient(135deg, #00aa00 0%, #007f00 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {status === 'loading' && (
          <div style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.25) 50%, transparent 100%)',
            animation: 'linkcard-shimmer 1.2s linear infinite',
          }} />
        )}
        {hasImage ? (
          <img
            src={meta.image_url}
            alt=""
            loading="lazy"
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <span style={{
            color: 'white', fontWeight: 800, fontSize: '1.5rem',
            fontFamily: 'Georgia, "Times New Roman", serif',
            visibility: status === 'loading' ? 'hidden' : 'visible',
          }}>A</span>
        )}
      </div>
      <div style={{ flex: '1 1 0', minWidth: 0 }}>
        <div style={{
          fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-1)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          opacity: status === 'loading' ? 0.4 : 1,
        }}>
          {status === 'loading' ? ' ' : titleText}
        </div>
        <div title={url} style={{
          fontSize: '0.7rem', color: 'var(--text-3)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          fontFamily: 'monospace', marginTop: 2,
        }}>
          {_urlShortPath(url)}
        </div>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onRemove(url); }}
        aria-label="Удалить ссылку"
        style={{
          flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--status-cancel-text, #999)',
          fontWeight: 700, fontSize: '1.2rem', padding: '0 6px', lineHeight: 1,
        }}
      >−</button>
    </div>
  );
}

function _urlShortPath(url) {
  try {
    const u = new URL(url);
    return u.pathname.length > 50 ? u.pathname.slice(0, 50) + '…' : u.pathname;
  } catch (_) {
    return url;
  }
}

// Inject shimmer keyframes once.
(function _injectShimmerStyles() {
  if (document.getElementById('linkcard-shimmer-style')) return;
  const s = document.createElement('style');
  s.id = 'linkcard-shimmer-style';
  s.textContent = '@keyframes linkcard-shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }';
  document.head.appendChild(s);
})();

Object.assign(window, { LinkCard });
