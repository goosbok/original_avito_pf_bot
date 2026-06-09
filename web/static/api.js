// Global HTTP client — injected before React components load.
// Uses JWT from localStorage. Exposes window.api for all components.
window.api = {
  _token() { return localStorage.getItem('access_token'); },

  // FastAPI returns 422 with detail as an array of {loc, msg, type, ...} objects.
  // Normalize to a human-readable Russian string that names the offending field
  // — bare "Field required" tells the user nothing about WHICH field.
  _FIELD_RU: {
    email: 'Email', password: 'Пароль', password_confirm: 'Подтверждение пароля',
    new_password: 'Новый пароль', new_password_confirm: 'Подтверждение нового пароля',
    current_password: 'Текущий пароль', first_name: 'Имя', code: 'Код',
    phone: 'Телефон', token: 'Токен', urls: 'Ссылки', links: 'Ссылки',
    days: 'Срок', fix_count: 'Просмотров в день', identifier: 'Идентификатор',
  },
  _MSG_RU: {
    'Field required': 'обязательное поле',
    'Input should be a valid string': 'некорректное значение',
    'String should have at least': 'слишком короткое значение',
    'String should match pattern': 'некорректный формат',
    'value is not a valid email address': 'некорректный email',
  },
  _ruMsg(msg) {
    if (!msg) return '';
    for (const [en, ru] of Object.entries(this._MSG_RU)) {
      if (msg.startsWith(en)) return ru;
    }
    return String(msg);
  },
  _formatDetail(detail) {
    if (!detail) return 'Не удалось выполнить запрос';
    if (typeof detail === 'string') return detail;
    const first = Array.isArray(detail) && detail.length > 0 ? detail[0] :
                  (typeof detail === 'object' ? detail : null);
    if (!first || !first.msg) return 'Не удалось выполнить запрос';
    const msg = this._ruMsg(first.msg);
    // loc looks like ['body', 'password_confirm'] or ['query', 'foo']. Pick last meaningful part.
    if (Array.isArray(first.loc) && first.loc.length > 0) {
      const fieldKey = first.loc[first.loc.length - 1];
      const fieldLabel = this._FIELD_RU[fieldKey] || (typeof fieldKey === 'string' ? fieldKey : null);
      if (fieldLabel) return `${fieldLabel}: ${msg}`;
    }
    return msg;
  },

  async get(path) {
    const token = this._token();
    const res = await fetch(path, {
      headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    });
    if (res.status === 401) return { __unauthorized: true };
    if (!res.ok) {
      const retryAfter = res.headers.get('Retry-After');
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const e = new Error(this._formatDetail(err.detail));
      e.status = res.status;
      e.detail = err.detail;
      if (retryAfter) e.retry_after = parseInt(retryAfter, 10) || retryAfter;
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
      const retryAfter = res.headers.get('Retry-After');
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const e = new Error(this._formatDetail(err.detail));
      e.status = res.status;
      e.detail = err.detail;
      if (retryAfter) e.retry_after = parseInt(retryAfter, 10) || retryAfter;
      throw e;
    }
    if (res.status === 204) return null;
    return res.json();
  }
};
