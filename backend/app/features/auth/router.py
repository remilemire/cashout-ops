# backend/app/features/auth/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_csrf
from app.features.sessions.cookies import (
    clear_csrf_cookie,
    clear_session_cookie,
    get_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
)
from app.features.users.schemas import UserOut
from app.lib.crypto import generate_secret_token

from . import service as auth_service
from .schemas import AuthLogin, AuthRegister
from .types import UserWithSessionToken

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
async def register(
    response: Response,
    payload: AuthRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    result = await auth_service.register(db, payload=payload)
    return _authenticated_response(response, result)


@router.post("/login", response_model=UserOut)
async def login(
    response: Response,
    payload: AuthLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    result = await auth_service.login(db, payload=payload)
    return _authenticated_response(response, result)


@router.post("/logout", dependencies=[Depends(require_csrf), Depends(get_current_user)])
async def logout(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> JSONResponse:
    response = JSONResponse(status_code=200, content={"ok": True})

    session_token = get_session_cookie(request)
    if session_token is None:
        return response

    await auth_service.logout(db, session_token=session_token)

    clear_session_cookie(response)
    clear_csrf_cookie(response)

    return response


def _authenticated_response(
    response: Response, result: UserWithSessionToken
) -> UserOut:
    set_session_cookie(response, result.session_token)
    set_csrf_cookie(response, generate_secret_token())
    return UserOut.model_validate(result.user)
