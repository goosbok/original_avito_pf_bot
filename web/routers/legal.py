"""Static legal pages: privacy policy and public offer."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["legal"])

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "legal"
_CACHE_HEADERS = {"Cache-Control": "public, max-age=300"}


@router.get("/privacy", response_class=FileResponse)
async def privacy() -> FileResponse:
    return FileResponse(
        _STATIC_DIR / "privacy.html",
        media_type="text/html",
        headers=_CACHE_HEADERS,
    )


@router.get("/offer", response_class=FileResponse)
async def offer() -> FileResponse:
    return FileResponse(
        _STATIC_DIR / "offer.html",
        media_type="text/html",
        headers=_CACHE_HEADERS,
    )
