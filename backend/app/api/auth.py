# backend/app/api/auth.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, require_csrf
from app.core.cookies import (
    clear_csrf_cookie,
    clear_session_cookie,
    get_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
)
from app.lib.crypto import generate_secret_token
from app.schemas.auth import AuthLogin
from app.schemas.users import UserOut
from app.services import auth, sessions

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
async def login(
    response: Response, payload: AuthLogin, db: Annotated[AsyncSession, Depends(get_db)]
) -> UserOut:
    result = await auth.login(db, payload=payload)

    set_session_cookie(response, result.session_token)
    set_csrf_cookie(response, generate_secret_token())

    return UserOut.model_validate(result.user)


@router.post("/logout", dependencies=[Depends(get_current_user), Depends(require_csrf)])
async def logout(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> JSONResponse:
    response = JSONResponse(status_code=200, content={"ok": True})

    session_token = get_session_cookie(request)
    if session_token is None:
        return response

    await sessions.delete_by_token(db, token=session_token)

    clear_session_cookie(response)
    clear_csrf_cookie(response)

    return response
