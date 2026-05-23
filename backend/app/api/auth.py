# backend/app/api/auth.py


from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.users import UserCreate, UserLogin, UserOut
from app.services import sessions, users
from app.utils.transactions import commit_or_raise, flush_or_raise

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/signup", response_model=UserOut)
async def signup(
    response: Response,
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    data = payload.to_update()
    user = users.create(db, payload=payload)
    await flush_or_raise(db)

    await db.refresh(user)
    sessions.create(response, db, user_id=user.id, remember=data.get("remember", False))
    await commit_or_raise(db)

    return UserOut.model_validate(user).to_response()


@router.get("/login", response_model=UserOut)
async def login(
    response: Response, payload: UserLogin, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, Any]:
    data = payload.to_update()
    user = await users.get_from_credentials(
        db, email=data["email"], password=data["password"]
    )
    sessions.create(response, db, user_id=user.id, remember=data.get("remember", False))
    await commit_or_raise(db)
    return UserOut.model_validate(user).to_response()


@router.post("/logout")
async def logout(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> JSONResponse:
    response = JSONResponse(status_code=200, content={"ok": True})
    await sessions.clear(request, response, db)
    await commit_or_raise(db)
    return response
