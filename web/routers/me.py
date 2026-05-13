from fastapi import APIRouter, Depends, HTTPException

from services import identity
from services.exceptions import UserNotFound
from web.admin_deps import is_admin
from web.deps import require_user
from web.schemas import ProfileResponse, ProviderInfo

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=ProfileResponse)
async def get_me(user_id: int = Depends(require_user)) -> ProfileResponse:
    try:
        u = identity.get_user(user_id)
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProfileResponse(
        user_id=u.id,
        user_name=u.user_name,
        first_name=u.first_name,
        balance=u.balance,
        is_admin=is_admin(u.id),
    )


@router.get("/providers", response_model=list[ProviderInfo])
async def get_providers(user_id: int = Depends(require_user)) -> list[ProviderInfo]:
    return [ProviderInfo(**p) for p in identity.list_providers(user_id)]
