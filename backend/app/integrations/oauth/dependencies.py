# backend/app/integrations/oauth/dependencies.py

from __future__ import annotations

from fastapi import Request

from .client import OAuthClient


def get_oauth_client(request: Request) -> OAuthClient:
    return request.app.state.oauth_client


__all__ = ["get_oauth_client"]
