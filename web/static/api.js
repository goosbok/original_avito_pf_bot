// Global HTTP client — injected before React components load.
// Uses JWT from localStorage. Exposes window.api for all components.
window.api = {
  _token() { return localStorage.getItem('access_token'); },

  async get(path) {
    const token = this._token();
    const res = await fetch(path, {
      headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    });
    if (res.status === 401) return { __unauthorized: true };
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const e = new Error(err.detail || 'Request failed');
      e.status = res.status;
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
      const e = new Error(err.detail || 'Request failed');
      e.status = res.status;
      throw e;
    }
    if (res.status === 204) return null;
    return res.json();
  }
};
