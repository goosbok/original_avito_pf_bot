"""Точка входа FastAPI-приложения.

Запускается как фоновая asyncio-таска внутри aiogram-loop через __main__.py.
Routers подключаются ниже по мере добавления (в Task 14, 15).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.avito_phrase_cache_refresh import run_refresh_loop
from services.order_links_deadline import run_deadline_loop
from services.order_links_dispatcher import run_dispatcher_loop
from services.payment_expiry import run_expiry_loop
from utils.sqlite3 import create_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Старт/стоп фоновых задач приложения."""
    # Создаём таблицы и применяем миграции при старте API.
    # На проде api стартует вместе с ботом через __main__.py, но standalone
    # uvicorn (docker compose) тоже должен уметь инициализировать БД.
    await asyncio.get_event_loop().run_in_executor(None, create_db)
    expiry_task = asyncio.create_task(run_expiry_loop())
    deadline_task = asyncio.create_task(run_deadline_loop())
    dispatcher_task = asyncio.create_task(run_dispatcher_loop())
    refresh_task = asyncio.create_task(run_refresh_loop())
    try:
        yield
    finally:
        expiry_task.cancel()
        try:
            await expiry_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        deadline_task.cancel()
        dispatcher_task.cancel()
        refresh_task.cancel()
        for task in (deadline_task, dispatcher_task, refresh_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


app = FastAPI(title="Avito PF Bot Web", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


from web.routers import refill as refill_router  # noqa: E402
from web.routers.applications import router as applications_router  # noqa: E402
from web.routers.auth_email import router as auth_email_router, router_auth as auth_router  # noqa: E402
from web.routers.auth_link import router as auth_link_router  # noqa: E402
from web.routers.auth_phone import router as auth_phone_router  # noqa: E402
from web.routers.auth_telegram import router as auth_telegram_router  # noqa: E402
from web.routers.me import router as me_router  # noqa: E402

app.include_router(refill_router.router)
app.include_router(applications_router)
app.include_router(auth_email_router)
app.include_router(auth_router)
app.include_router(auth_link_router)
app.include_router(auth_phone_router)
app.include_router(auth_telegram_router)
app.include_router(me_router)

from web.routers.orders import router as orders_router  # noqa: E402

app.include_router(orders_router)

from web.routers.notifications import router as notifications_router  # noqa: E402

app.include_router(notifications_router)

from web.routers.support import router as support_router  # noqa: E402

app.include_router(support_router)

from web.routers.config import router as config_router  # noqa: E402

app.include_router(config_router)

from web.routers.admin_users import router as admin_users_router  # noqa: E402

app.include_router(admin_users_router)

from web.routers.admin_orders import router as admin_orders_router  # noqa: E402

app.include_router(admin_orders_router)

from web.routers.admin_support import router as admin_support_router  # noqa: E402

app.include_router(admin_support_router)

from web.routers.admin_stats import router as admin_stats_router  # noqa: E402

app.include_router(admin_stats_router)

from web.routers.legal import router as legal_router  # noqa: E402

app.include_router(legal_router)

from pathlib import Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
