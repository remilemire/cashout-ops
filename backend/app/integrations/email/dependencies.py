from __future__ import annotations

from fastapi import Request

from .client import EmailClient


def get_email_client(request: Request) -> EmailClient:
    return request.app.state.email_client


__all__ = ["get_email_client"]
