# backend/app/infrastructure/redis/dependencies.py

from __future__ import annotations

from fastapi import Request

from . import Redis


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


__all__ = ["get_redis"]
