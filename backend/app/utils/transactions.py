# backend/app/utils/transactions.py

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError, ServerError


async def commit_or_raise(db: AsyncSession) -> None:
    await _transact_or_raise(db.commit, db.rollback)


async def flush_or_raise(db: AsyncSession) -> None:
    await _transact_or_raise(db.flush, db.rollback)


async def _transact_or_raise(
    transact: Callable[[], Awaitable[None]], rollback: Callable[[], Awaitable[None]]
) -> None:
    try:
        transact()

    except IntegrityError as error:
        rollback()

        diag = getattr(error.orig, "diag", {})
        state = getattr(diag, "sqlstate", None)
        match state:
            case "23505":
                raise ConflictError("unique violation") from error

            case "23503":
                raise ConflictError("foreign key violation") from error

            case "23502":
                raise ConflictError("not null violation") from error

            case "23000":
                raise ConflictError("check constraint violation") from error

            case _:
                raise ConflictError("integrity violation") from error

    except Exception as error:
        rollback()
        raise ServerError() from error
