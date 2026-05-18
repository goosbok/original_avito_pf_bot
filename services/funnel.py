"""Universal funnel analytics: event log + step registry.

Pipeline pattern: each user-facing service declares its ordered list of steps
in FUNNEL_STEPS, then domain handlers call track_step(user_id, service, step)
at well-defined progression points. Reads are aggregate-only.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")  # headless backend — required when no display is available
import matplotlib.pyplot as plt  # noqa: E402

from services.db import connect

logger = logging.getLogger(__name__)

# Ordered list of steps for each service. Add a new entry to plug a new
# service into funnel analytics — no schema change required.
FUNNEL_STEPS: dict[str, list[str]] = {
    "pf_avito": [
        "view_tariff",
        "select_period",
        "select_count",
        "links_valid",
        "contact_chosen",
        "order_confirmed",
    ],
}

# Human-readable labels for admin UI. Keys must match FUNNEL_STEPS.
SERVICE_LABELS: dict[str, str] = {
    "pf_avito": "🚀 Накрутка ПФ Авито",
}

# Russian labels for each step, shown in the admin chart and caption.
# Keys must cover every (service, step) in FUNNEL_STEPS — enforced by test.
STEP_LABELS: dict[str, dict[str, str]] = {
    "pf_avito": {
        "view_tariff": "Открыл карточку ПФ",
        "select_period": "Выбрал срок",
        "select_count": "Выбрал кол-во ПФ",
        "links_valid": "Прислал ссылки",
        "contact_chosen": "Ответил про контакты",
        "order_confirmed": "Подтвердил заказ",
    },
}


def get_step_label(service: str, step: str) -> str:
    """Human-readable Russian label for a step. Falls back to the raw step id."""
    return STEP_LABELS.get(service, {}).get(step, step)


def _validate(service: str, step: str | None = None) -> None:
    if service not in FUNNEL_STEPS:
        raise ValueError(f"Unknown service: {service!r}")
    if step is not None and step not in FUNNEL_STEPS[service]:
        raise ValueError(f"Unknown step {step!r} for service {service!r}")


def track_step(user_id: int, service: str, step: str) -> None:
    """Record one funnel event.

    Raises ValueError if service or step is not registered in FUNNEL_STEPS.
    Duplicates (same user_id + step) are allowed by design — the table is
    an event log; uniqueness is enforced at read time via COUNT(DISTINCT).
    """
    _validate(service, step)
    try:
        ts = datetime.now(timezone.utc).isoformat()
        with connect() as con:
            con.execute(
                "INSERT INTO funnel_events (user_id, service, step, ts) "
                "VALUES (?, ?, ?, ?)",
                (user_id, service, step, ts),
            )
            con.commit()
    except Exception:
        logger.warning(
            "track_step failed",
            exc_info=True,
            extra={"service": service, "step": step, "user_id": user_id},
        )


def get_funnel_stats(
    service: str,
    *,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> list[dict]:
    """Aggregate distinct-user counts per step, in FUNNEL_STEPS order.

    Returns: [{"step": str, "users": int, "drop_off_pct": float | None}, ...]
    Steps with no events appear with users=0. drop_off_pct is None for the
    first step and whenever the previous step had 0 users.
    """
    _validate(service)
    if from_dt is not None and from_dt.tzinfo is None:
        raise ValueError("from_dt must be timezone-aware")
    if to_dt is not None and to_dt.tzinfo is None:
        raise ValueError("to_dt must be timezone-aware")
    sql = "SELECT step, COUNT(DISTINCT user_id) AS users FROM funnel_events WHERE service = ?"
    params: list = [service]
    if from_dt is not None:
        sql += " AND ts >= ?"
        params.append(from_dt.isoformat())
    if to_dt is not None:
        sql += " AND ts <= ?"
        params.append(to_dt.isoformat())
    sql += " GROUP BY step"

    with connect() as con:
        rows = con.execute(sql, params).fetchall()
    counts: dict[str, int] = {row["step"]: int(row["users"]) for row in rows}

    out: list[dict] = []
    prev: int | None = None
    for step in FUNNEL_STEPS[service]:
        users = counts.get(step, 0)
        if prev is None or prev == 0:
            drop_off_pct: float | None = None
        else:
            drop_off_pct = round((prev - users) / prev * 100, 1)
        out.append({"step": step, "users": users, "drop_off_pct": drop_off_pct})
        prev = users
    return out


def render_chart(
    service: str,
    *,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    title: str,
) -> io.BytesIO:
    """Render a horizontal bar chart of the funnel as PNG. Returns a BytesIO
    positioned at offset 0 (ready for aiogram answer_photo)."""
    stats = get_funnel_stats(service, from_dt=from_dt, to_dt=to_dt)
    steps = [r["step"] for r in stats]
    labels = [get_step_label(service, s) for s in steps]
    users = [r["users"] for r in stats]

    fig, ax = plt.subplots(figsize=(10, max(3, 0.7 * len(steps) + 1)))
    y = list(range(len(steps)))
    ax.barh(y, users, color="#4a90e2")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()  # first step on top
    ax.set_xlabel("Уникальных пользователей")
    ax.set_title(title)

    for i, row in enumerate(stats):
        label = str(row["users"])
        if row["drop_off_pct"] is not None:
            label += f"  (-{row['drop_off_pct']}%)"
        ax.text(row["users"], i, "  " + label, va="center")

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf
