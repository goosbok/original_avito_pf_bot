// Global HTTP client — injected before React components load.
// Uses JWT from localStorage. Exposes window.api for all components.
window.api = {
  _token() { return localStorage.getItem('access_token'); },

  // FastAPI returns 422 with detail as an array of {loc, msg, type, ...} objects.
  // Normalize to the first human-readable message so callers can display a string.
  _formatDetail(detail) {
    if (!detail) return 'Request failed';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      if (first && typeof first === 'object' && first.msg) return String(first.msg);
    }
    if (typeof detail === 'object' && detail.msg) return String(detail.msg);
    return 'Request failed';
  },

  async get(path) {
    const token = this._token();
    const res = await fetch(path, {
      headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    });
    if (res.status === 401) return { __unauthorized: true };
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const e = new Error(this._formatDetail(err.detail));
      e.status = res.status;
      e.detail = err.detail;
      throw e;
    }
    return res.json();
  },

  async post(path, body) {
    const token = this._token();
    const res = await fetch(path, {
      method: 'POST',
      headers: Object.assign(
        { 'Content-Type': 'application/json' },
        token ? { 'Authorization': 'Bearer ' + token } : {}
      ),
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const e = new Error(this._formatDetail(err.detail));
      e.status = res.status;
      e.detail = err.detail;
      throw e;
    }
    if (res.status === 204) return null;
    return res.json();
  }
};
