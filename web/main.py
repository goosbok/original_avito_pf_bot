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
