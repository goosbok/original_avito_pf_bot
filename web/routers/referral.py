"""Партнерская программа: ссылки, статистика, клики + админ-настройка процента."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import referral
from services.exceptions import NothingToWithdraw, UserNotFound, WithdrawConflict
from web.admin_deps import require_admin
from web.deps import require_user

router = APIRouter(prefix="/api", tags=["referral"])


class CreateLinkBody(BaseModel):
    slug: str | None = None


class AdminPercentBody(BaseModel):
    # Поле ОБЯЗАТЕЛЬНОЕ (но nullable): PATCH с пустым телом должен вернуть 422,
    # а не молча сбросить договорной процент на глобальный.
    custom_percent: int | None = Field(..., ge=1, le=100)


@router.get("/me/referral")
async def my_referral(user_id: int = Depends(require_user)) -> dict:
    return referral.get_summary(user_id)


@router.post("/me/referral/links", status_code=201)
async def create_link(
    body: CreateLinkBody, user_id: int = Depends(require_user)
) -> dict:
    try:
        return referral.create_link(user_id, body.slug)
    except referral.SlugInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (referral.SlugTaken, referral.LinkLimitReached) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        # FK violation → аккаунт удалён (например, влит при merge), а JWT ещё жив.
        # Чистый 404 вместо необработанного 500.
        raise HTTPException(status_code=404, detail="пользователь не найден") from exc


@router.delete("/me/referral/links/{link_id}", status_code=204, response_model=None)
async def archive_link(
    link_id: int, user_id: int = Depends(require_user)
) -> None:
    if not referral.archive_link(user_id, link_id):
        raise HTTPException(status_code=404, detail="ссылка не найдена")


@router.post("/me/referral/links/{link_id}/restore")
async def restore_link(
    link_id: int, user_id: int = Depends(require_user)
) -> dict:
    if not referral.restore_link(user_id, link_id):
        raise HTTPException(status_code=404, detail="ссылка не найдена")
    return {"ok": True}


@router.get("/me/referral/bonuses")
async def my_bonuses(
    limit: int = 50, offset: int = 0, user_id: int = Depends(require_user)
) -> list[dict]:
    return referral.list_bonuses(
        user_id, limit=max(1, min(limit, 200)), offset=max(0, offset)
    )


@router.post("/me/referral/withdraw")
async def withdraw_referral_balance(user_id: int = Depends(require_user)) -> dict:
    try:
        withdrawn, new_balance = referral.withdraw_to_main_balance(user_id)
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail="пользователь не найден") from exc
    except NothingToWithdraw as exc:
        raise HTTPException(status_code=400, detail="нечего выводить") from exc
    except WithdrawConflict as exc:
        raise HTTPException(status_code=409, detail="попробуйте ещё раз") from exc
    return {"withdrawn": withdrawn, "referral_balance": 0, "balance": new_balance}


@router.post("/referral/click")
async def click(code: str = "") -> dict:
    """Публичный счетчик кликов (sendBeacon). Любой мусор — молча ok.

    Best-effort: без rate-limit/дедупа, счетчик можно накрутить скриптом.
    Это витринная метрика, НЕ основа для начислений (бонусы идут только с
    реальных пополнений через referral_bonuses).
    """
    referral.register_click(code)
    return {"ok": True}


# ------------------------------------------------------------------ admin

@router.get("/admin/users/{target_user_id}/referral")
async def admin_user_referral(
    target_user_id: int, _: int = Depends(require_admin)
) -> dict:
    return referral.get_summary(target_user_id)


@router.patch("/admin/referral/links/{link_id}")
async def admin_set_percent(
    link_id: int, body: AdminPercentBody, _: int = Depends(require_admin)
) -> dict:
    if not referral.set_custom_percent(link_id, body.custom_percent):
        raise HTTPException(status_code=404, detail="ссылка не найдена")
    return {"ok": True}
