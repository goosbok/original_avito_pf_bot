"""Admin feature flags (auto-dispatch в бизу и т.п.)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from services import feature_flags
from utils.sqlite3 import get_setting_from_base
from web.admin_deps import require_admin
from web.schemas import AdminAutoDispatchState, AdminAutoDispatchUpdate

router = APIRouter(prefix="/api/admin/settings", tags=["admin"])


def _state() -> AdminAutoDispatchState:
    row = get_setting_from_base("pf_auto_dispatch_enabled")
    return AdminAutoDispatchState(
        enabled=feature_flags.auto_dispatch_enabled(),
        source="db" if row and row["value"] else "env",
    )


@router.get("/auto-dispatch", response_model=AdminAutoDispatchState)
async def get_auto_dispatch(_: int = Depends(require_admin)) -> AdminAutoDispatchState:
    return _state()


@router.post("/auto-dispatch", response_model=AdminAutoDispatchState)
async def set_auto_dispatch(
    body: AdminAutoDispatchUpdate,
    _: int = Depends(require_admin),
) -> AdminAutoDispatchState:
    feature_flags.set_auto_dispatch_enabled(body.enabled)
    return _state()
