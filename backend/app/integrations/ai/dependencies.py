from __future__ import annotations

from fastapi import Request

from .client import AIClient


def get_ai_client(request: Request) -> AIClient:
    return request.app.state.ai_client


__all__ = ["get_ai_client"]
