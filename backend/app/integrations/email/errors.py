# backend/app/integrations/email/errors.py

from __future__ import annotations


class EmailDeliveryError(Exception):
    """The provider failed to deliver an email.

    Clients raise this instead of provider SDK exceptions so callers (and the
    outbox's `last_error`) see an application error naming the cause, never a
    provider's internal exception type.
    """


__all__ = ["EmailDeliveryError"]
