# backend/app/dependencies/background.py

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable


class PostCommitTasks:
    """Async jobs queued during a request and run after its transaction commits.

    Unlike Starlette's BackgroundTasks — which execute before the `get_db`
    teardown and therefore cannot see the request's writes — these jobs run
    once the request transaction has committed. On request failure the jobs
    are skipped.
    """

    def __init__(self) -> None:
        self._jobs: list[Callable[[], Awaitable[None]]] = []

    def add(self, job: Callable[[], Awaitable[None]]) -> None:
        self._jobs.append(job)

    async def run(self) -> None:
        for job in self._jobs:
            await job()


async def get_post_commit_tasks() -> AsyncIterator[PostCommitTasks]:
    """Yield a per-request PostCommitTasks and run its jobs on teardown.

    Ordering contract: dependencies tear down in reverse (LIFO) order, so this
    MUST be entered before any dependency that opens the DB session — list it
    first in the router's `dependencies=[...]` — for `run()` to execute after
    `get_db` has committed. A downstream exception surfaces at `yield`, which
    skips the jobs.
    """
    tasks = PostCommitTasks()
    yield tasks
    await tasks.run()
