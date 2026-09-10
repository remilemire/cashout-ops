from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One transaction per request: commit on success, roll back on error.

    Request services leave commits to this dependency. Background jobs own
    separate transactions; repositories flush where results are needed early.

    Declare the session as `DbSession` below rather than wrapping this in
    `Depends` yourself — the wrapper's `scope` decides whether a commit-time
    failure can still reach the client (see `DbSession`).
    """
    async with request.app.state.db_sessionmaker() as db:
        try:
            yield db
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


# The request's database session. `scope="function"` makes FastAPI close the
# dependency after the handler returns but before the response bytes are
# sent; the commit therefore runs while an IntegrityError can still be
# translated into the error response the client actually receives. Without
# it teardown runs after the response is on the wire, so a commit-time
# constraint violation (e.g. from an UPDATE that never flushed during the
# request) would be a silent lost write behind a success response.
#
# Never wrap `get_db` in a bare `Depends(get_db)`: the two forms have
# different dependency-cache keys, so a request resolving both would
# silently open two sessions and two transactions — and the bare form's
# post-response commit reintroduces the lost-write hazard. No bare user
# remains; tests/unit/test_dependency_scopes.py enforces that every route
# resolves get_db function-scoped.
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]


__all__ = ["DbSession", "get_db"]
