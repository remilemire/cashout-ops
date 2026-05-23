# backend/app/services/users.py

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import UnauthenticatedError
from app.models import User
from app.schemas.users import UserCreate, UserUpdate
from app.utils.passwords import hash_password, verify_password


async def get_from_credentials(db: AsyncSession, *, email: str, password: str) -> User:
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthenticatedError("Invalid email or password.")
    return user


def create(db: AsyncSession, *, payload: UserCreate) -> User:
    data = payload.to_update()

    password = data.pop("password")
    data["password_hash"] = hash_password(password)

    user = User(**data)
    db.add(user)

    return user


async def update(db: AsyncSession, *, user_id: int, payload: UserUpdate) -> User:
    user = await User.get_active(db, user_id)
    for field, value in payload.to_update().items():
        setattr(user, field, value)
    return user


async def delete(db: AsyncSession, *, user_id: int) -> None:
    user = await User.get_active(db, user_id)
    await db.delete(user)
