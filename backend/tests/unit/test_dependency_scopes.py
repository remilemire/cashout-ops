# backend/tests/unit/test_dependency_scopes.py

"""Structural guarantees on dependency scopes.

`DbSession` exists so the per-request commit runs before the response is
sent (see app/infrastructure/db/dependencies.py). A bare `Depends(get_db)`
would commit after the response — reopening the silent lost-write hazard —
and mixing the two forms in one request would open two sessions, because
the dependency-cache key includes the scope. These tests walk the dependant
trees FastAPI builds at route-declaration time, so every route mounted
under /api is covered without constructing an app.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Sequence

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from app.api import api_router
from app.features.auth.email_challenges.dependencies import challenge_time_floor
from app.features.auth.email_challenges.router import router as email_challenges_router
from app.infrastructure.db.dependencies import get_db


def _api_routes(routes: Sequence[BaseRoute]) -> Iterator[APIRoute]:
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        else:
            # FastAPI 0.138's include_router mounts an _IncludedRouter wrapper
            # instead of copying routes; `original_router` is its (private,
            # version-pinned) link to the included router's own routes.
            original = getattr(route, "original_router", None)
            if original is not None:
                yield from _api_routes(original.routes)


def _walk(dependant: Dependant) -> Iterator[Dependant]:
    yield dependant
    for sub in dependant.dependencies:
        yield from _walk(sub)


def test_get_db_is_always_function_scoped() -> None:
    routes = list(_api_routes(api_router.routes))
    # If the include-wrapper unwrapping breaks on a FastAPI upgrade, the walk
    # would go silently empty; the count guard turns that into a failure.
    assert len(routes) >= 20

    for route in routes:
        for dependant in _walk(route.dependant):
            if dependant.call is get_db:
                assert dependant.scope == "function", (
                    f"{route.path} resolves get_db without scope='function'; "
                    "declare the session as DbSession"
                )


def test_email_challenge_routes_enter_the_time_floor_first() -> None:
    """The floor must wrap everything, the session commit included.

    Router-level dependencies are solved before endpoint parameters and torn
    down LIFO, so the floor being first — and function-scoped, like the
    session — is what puts the commit inside the padded window and the pad
    before the first response byte. The timing test cannot observe this from
    the client side; this pins the structure that guarantees it.
    """
    routes = list(_api_routes(email_challenges_router.routes))
    assert len(routes) == 2

    for route in routes:
        first = route.dependant.dependencies[0]
        assert first.call is challenge_time_floor, route.path
        assert first.scope == "function", route.path
