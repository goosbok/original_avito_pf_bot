// LinkCard — preview card for a pasted Avito URL.
// Replaces the plain text list (AddedLinksList) used previously in OrderForm.
//
// Props:
//   url     — the Avito URL (canonical, already trimmed by parseAvitoUrls)
//   meta    — { status: 'loading'|'ok'|'not_found'|'fetch_failed', image_url?, title? }
//   onRemove — callback when user clicks "×"
//
// States rendered:
//   loading                  → neutral-gray thumb + CSS spinner, skeleton bar for title
//   ok                       → <img> from image_url, title shown
//   not_found / fetch_failed → green "A" placeholder, fallback title = url path
function LinkCard({ url, meta, onRemove }) {
  const status = (meta && meta.status) || 'loading';
  const isLoading = status === 'loading';
  const hasImage = status === 'ok' && meta && meta.image_url;
  // Show green "A" tile only when we know there's no preview to load.
  // (Without this gate the green flashes between loading and the <img>
  // actually rendering its pixels.)
  const showFallback = !isLoading && !hasImage;
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
        // Brand-green tile ONLY for the explicit fallback ("A"). For loading
        // and for ok-with-image we use neutral gray so there's no green flash
        // while the CDN <img> is still pulling pixels.
        background: showFallback
          ? 'linear-gradient(135deg, #00aa00 0%, #007f00 100%)'
          : 'var(--surface-2, #ececec)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {isLoading && (
          <div
            aria-label="Загрузка превью"
            style={{
              width: 22, height: 22, borderRadius: '50%',
              border: '2.5px solid var(--border, rgba(0,0,0,0.12))',
              borderTopColor: 'var(--primary, #00aa00)',
              animation: 'linkcard-spin 0.8s linear infinite',
            }}
          />
        )}
        {hasImage && (
          <img
            src={meta.image_url}
            alt=""
            loading="lazy"
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        )}
        {showFallback && (
          <span style={{
            color: 'white', fontWeight: 800, fontSize: '1.5rem',
            fontFamily: 'Georgia, "Times New Roman", serif',
          }}>A</span>
        )}
      </div>
      <div style={{ flex: '1 1 0', minWidth: 0 }}>
        {isLoading ? (
          // Skeleton bar — clearly signals "loading" alongside the spinner.
          <div style={{
            height: 12, width: '62%', borderRadius: 4,
            background: 'var(--surface-2, #ececec)',
            animation: 'linkcard-pulse 1.2s ease-in-out infinite',
          }} />
        ) : (
          <div style={{
            fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-1)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>{titleText}</div>
        )}
        <div title={url} style={{
          fontSize: '0.7rem', color: 'var(--text-3)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          fontFamily: 'monospace', marginTop: isLoading ? 6 : 2,
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

// Inject spinner + skeleton-pulse keyframes once.
(function _injectLinkCardStyles() {
  if (document.getElementById('linkcard-anim-style')) return;
  const s = document.createElement('style');
  s.id = 'linkcard-anim-style';
  s.textContent = [
    '@keyframes linkcard-spin { to { transform: rotate(360deg); } }',
    '@keyframes linkcard-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }',
  ].join(' ');
  document.head.appendChild(s);
})();

Object.assign(window, { LinkCard });
