# backend/app/dependencies/redis.py

from __future__ import annotations

from fastapi import Request

from app.infrastructure.redis import Redis


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


__all__ = ["get_redis"]
