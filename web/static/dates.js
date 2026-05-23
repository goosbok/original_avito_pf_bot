// dates.js — клиентский аналог utils/dates.format_display.
// Бэк хранит даты в ISO+UTC, фронт показывает в Moscow time в виде dd.mm.yyyy HH:MM.
//
// API (window-globals):
//   formatDisplay(iso) — "dd.mm.yyyy HH:MM"
//   formatDate(iso)    — "dd.mm.yyyy"
//   formatTime(iso)    — "HH:MM"
//
// Поддерживаемые входы:
//   • ISO+TZ: "2026-05-23T11:30:00+00:00"
//   • SQLite naive UTC: "2026-05-23 11:30:00"
//   • Legacy Moscow naive: "23.05.2026 14:30:00" (на случай если миграция что-то пропустила)
//   • Уже отформатированное "HH:MM" — formatTime возвращает как есть (для optimistic-сообщений)
// Пустой/битый ввод → "".
(function () {
  'use strict';

  var MSK_FORMATTER = new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'Europe/Moscow',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
  });

  function _parts(date) {
    var parts = MSK_FORMATTER.formatToParts(date);
    var out = {};
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      if (p.type !== 'literal') out[p.type] = p.value;
    }
    // Some engines emit "24" for midnight under hour12:false — нормализуем.
    if (out.hour === '24') out.hour = '00';
    return out;
  }

  function _parseLegacy(s) {
    // "23.05.2026 14:30:00" → Moscow-naive → Date в UTC.
    var m = /^(\d{2})\.(\d{2})\.(\d{4})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/.exec(s);
    if (!m) return null;
    var dd = m[1], mm = m[2], yyyy = m[3], hh = m[4], mi = m[5], ss = m[6] || '00';
    return new Date(yyyy + '-' + mm + '-' + dd + 'T' + hh + ':' + mi + ':' + ss + '+03:00');
  }

  function _parseToDate(value) {
    if (value == null) return null;
    if (typeof value !== 'string') {
      // Если уже Date или число — попробуем напрямую.
      var d0 = new Date(value);
      return isNaN(d0.getTime()) ? null : d0;
    }
    var s = value.trim();
    if (!s) return null;

    // 1) Legacy dd.mm.yyyy
    var legacy = _parseLegacy(s);
    if (legacy && !isNaN(legacy.getTime())) return legacy;

    // 2) ISO. Нормализуем "YYYY-MM-DD HH:MM:SS" → "YYYY-MM-DDTHH:MM:SS".
    var iso = s;
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(iso)) {
      iso = iso.replace(' ', 'T');
    }
    // Если нет TZ-маркера (Z или ±HH:MM) после времени — считаем UTC (SQLite CURRENT_TIMESTAMP).
    var hasTz = /([+-]\d{2}:?\d{2}|Z)$/i.test(iso);
    if (!hasTz && /T\d{2}:\d{2}/.test(iso)) {
      iso += 'Z';
    }
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }

  function formatDisplay(value) {
    var d = _parseToDate(value);
    if (!d) return '';
    var p = _parts(d);
    return p.day + '.' + p.month + '.' + p.year + ' ' + p.hour + ':' + p.minute;
  }

  function formatDate(value) {
    var d = _parseToDate(value);
    if (!d) return '';
    var p = _parts(d);
    return p.day + '.' + p.month + '.' + p.year;
  }

  function formatTime(value) {
    // Если уже "HH:MM" — возвращаем как есть (optimistic-сообщения).
    if (typeof value === 'string' && /^\d{2}:\d{2}$/.test(value.trim())) {
      return value.trim();
    }
    var d = _parseToDate(value);
    if (!d) return '';
    var p = _parts(d);
    return p.hour + ':' + p.minute;
  }

  window.formatDisplay = formatDisplay;
  window.formatDate = formatDate;
  window.formatTime = formatTime;
})();
