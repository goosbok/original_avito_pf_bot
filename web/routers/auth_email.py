"""Email registration and login endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services import auth_email
from services.exceptions import EmailAlreadyRegistered, InvalidCredentials
from web.auth import create_jwt
from web.schemas import EmailLoginRequest, EmailRegisterRequest, TokenResponse

router = APIRouter(prefix="/api/auth/email", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: EmailRegisterRequest) -> TokenResponse:
    """Register a new user with email and password."""
    try:
        user_id = auth_email.register(body.email, body.password, first_name=body.first_name)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))


@router.post("/login", response_model=TokenResponse)
async def login(body: EmailLoginRequest) -> TokenResponse:
    """Login with email and password."""
    try:
        user_id = auth_email.login(body.email, body.password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return TokenResponse(access_token=create_jwt(user_id))
