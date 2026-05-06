from fastapi import APIRouter, Depends, HTTPException

from services import applications
from services.exceptions import ApplicationNotFound
from web.deps import require_user
from web.schemas import (
    ApplicationCreateRequest,
    ApplicationCreateResponse,
    ApplicationInfo,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.post("", response_model=ApplicationCreateResponse, status_code=201)
async def create_app(
    body: ApplicationCreateRequest,
    user_id: int = Depends(require_user),
) -> ApplicationCreateResponse:
    try:
        result = applications.create(user_id, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApplicationCreateResponse(
        id=result.application.id,
        name=result.application.name,
        api_key=result.api_key,  # plaintext, ONE TIME
        api_key_prefix=result.application.api_key_prefix,
        created_at=result.application.created_at,
    )


@router.get("", response_model=list[ApplicationInfo])
async def list_apps(user_id: int = Depends(require_user)) -> list[ApplicationInfo]:
    return [
        ApplicationInfo(
            id=a.id,
            name=a.name,
            api_key_prefix=a.api_key_prefix,
            created_at=a.created_at,
            revoked_at=a.revoked_at,
        )
        for a in applications.list_for_user(user_id)
    ]


@router.delete("/{app_id}", status_code=204)
async def revoke_app(app_id: int, user_id: int = Depends(require_user)) -> None:
    try:
        applications.revoke(app_id, user_id)
    except ApplicationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
