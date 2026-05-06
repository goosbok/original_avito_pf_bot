"""Точка входа FastAPI-приложения.

Запускается как фоновая asyncio-таска внутри aiogram-loop через __main__.py.
Routers подключаются ниже по мере добавления (в Task 14, 15).
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Avito PF Bot Web", version="0.1.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


from web.routers import refill as refill_router  # noqa: E402
from web.routers.applications import router as applications_router  # noqa: E402
from web.routers.auth_email import router as auth_email_router  # noqa: E402
from web.routers.auth_link import router as auth_link_router  # noqa: E402
from web.routers.auth_telegram import router as auth_telegram_router  # noqa: E402
from web.routers.me import router as me_router  # noqa: E402

app.include_router(refill_router.router)
app.include_router(applications_router)
app.include_router(auth_email_router)
app.include_router(auth_link_router)
app.include_router(auth_telegram_router)
app.include_router(me_router)

from pathlib import Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
