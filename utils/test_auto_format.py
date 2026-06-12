"""Pure text formatters для admin «🧪 Test auto-dispatch» сообщений.

Чистые функции — никаких I/O, БД, HTTP. Принимают LinkPreview /
DispatchResult из services.order_links_dispatcher, возвращают готовые
Telegram-сообщения.
"""
from __future__ import annotations

from datetime import datetime
from html import escape as _html_escape

from services.order_links_dispatcher import DispatchResult, LinkPreview

_REASON_RU = {
    "cache_hit": "есть в кэше",
    "cache_miss": "нет в кэше",
    "no_ad_id": "ad_id не выделился",
}


def _fmt_deadline(iso: str | None) -> str:
    """ISO timestamp → 'YYYY-MM-DD' (только день)."""
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso)
        return d.date().isoformat()
    except ValueError:
        return iso[:10]


def _short_url(url: str, limit: int = 80) -> str:
    """Урезаем длинный URL чтобы preview помещался в Telegram limit."""
    if len(url) <= limit:
        return url
    return url[:limit] + "…"


def format_preview(*, order_id: int, previews: list[LinkPreview]) -> str:
    """Сформировать preview-сообщение для admin Test auto."""
    n_auto = sum(1 for p in previews if p.decision == "auto")
    n_total = len(previews)
    word = "ссылок" if n_total in (0, 5, 6, 7, 8, 9, 10, 11, 12) else (
        "ссылка" if n_total == 1 else "ссылки"
    )

    lines = [
        f"🧪 Test auto-dispatch для #{order_id}",
        "",
        f"Будет обработано: {n_total} {word}",
        "",
    ]

    for i, p in enumerate(previews, 1):
        decision_icon = "✅ AUTO" if p.decision == "auto" else "❌ MANUAL"
        reason_ru = _REASON_RU.get(p.reason, p.reason)
        lines.append(f"{i}. <code>{_html_escape(_short_url(p.url))}</code>")
        lines.append(f"   ├ ad_id: {_html_escape(p.ad_id) if p.ad_id else '—'}")
        lines.append(f"   ├ classifier: {decision_icon} ({reason_ru})")
        if p.decision == "auto":
            phrase = _short_url(p.phrase or "", limit=150)
            lines.append(f"   ├ phrase: '{_html_escape(phrase)}'")
            lines.append(f"   └ deadline: {_fmt_deadline(p.deadline_at)}")
        else:
            lines.append(f"   └ останется pending+manual")
        lines.append("")

    if n_auto == 0:
        lines.append("⚠️ Все ссылки → MANUAL, отправлять нечего.")
    else:
        word_a = "ссылка" if n_auto == 1 else (
            "ссылки" if 2 <= n_auto <= 4 else "ссылок"
        )
        lines.append(f"⚠️ Будет реально отправлено {n_auto} {word_a} в biza.")

    return "\n".join(lines)


def format_result(
    *,
    order_id: int,
    previews: list[LinkPreview],
    results: list[DispatchResult],
) -> str:
    """Сформировать result-сообщение после force_dispatch."""
    by_link = {r.link_id: r for r in results}
    n_success = sum(1 for r in results if r.success)
    n_attempted = len(results)

    status_icon = "✅" if n_success == n_attempted and n_attempted > 0 else "⚠️"
    lines = [
        f"{status_icon} Test auto-dispatch для #{order_id} завершён",
        "",
        f"Отправлено: {n_success} / {n_attempted}",
        "",
    ]

    for i, p in enumerate(previews, 1):
        lines.append(f"{i}. <code>{_html_escape(_short_url(p.url))}</code>")
        if p.decision == "manual":
            lines.append(f"   ⏸ MANUAL (не отправлялось)")
        else:
            r = by_link.get(p.link_id)
            if r is None:
                lines.append(f"   ⚠️ (нет результата — баг)")
            elif r.success:
                lines.append(
                    f"   ✅ AUTO, external_id={_html_escape(str(r.external_id))}, "
                    f"in_work до {_fmt_deadline(p.deadline_at)}"
                )
            else:
                lines.append(f"   ❌ Ошибка: {_html_escape(r.error or '')}")
                lines.append(
                    "   (ссылка осталась pending+auto; если "
                    "PF_AUTO_DISPATCH_ENABLED включён, dispatcher повторит)"
                )
        lines.append("")

    return "\n".join(lines).rstrip()


def format_empty_cache_message(*, order_id: int, link_count: int) -> str:
    """Friendly fallback когда кэш пуст."""
    word = "ссылки" if 2 <= link_count <= 4 else (
        "ссылка" if link_count == 1 else "ссылок"
    )
    return (
        f"📭 Кэш фраз пустой.\n\n"
        f"Все {link_count} {word} заказа #{order_id} ушли бы в MANUAL "
        f"потому что в локальной БД нет ни одной известной фразы для их "
        f"ad_id.\n\n"
        f"Запусти backfill один раз, потом попробуй снова:\n\n"
        f"  <code>docker compose exec api python -m "
        f"scripts.backfill_avito_phrase_cache --days 90</code>\n\n"
        f"После backfill дневной refresh-loop поддерживает кэш свежим."
    )
