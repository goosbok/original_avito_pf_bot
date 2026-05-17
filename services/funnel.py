"""Universal funnel analytics: event log + step registry.

Pipeline pattern: each user-facing service declares its ordered list of steps
in FUNNEL_STEPS, then domain handlers call track_step(user_id, service, step)
at well-defined progression points. Reads are aggregate-only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from services.db import connect

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
    ts = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute(
            "INSERT INTO funnel_events (user_id, service, step, ts) "
            "VALUES (?, ?, ?, ?)",
            (user_id, service, step, ts),
        )
        con.commit()
