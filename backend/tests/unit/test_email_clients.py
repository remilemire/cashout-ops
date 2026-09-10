"""Provider email clients normalize send failures to the application error."""

from __future__ import annotations

from typing import NoReturn

import pytest
import resend

from app.integrations.email import EmailDeliveryError, ResendEmailClient


async def test_resend_send_failure_raises_the_application_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ResendEmailClient(api_key="test-key", sender="Test <test@test.com>")

    def _boom(params: resend.Emails.SendParams) -> NoReturn:
        raise RuntimeError("invalid api key")

    monkeypatch.setattr(resend.Emails, "send", _boom)

    with pytest.raises(EmailDeliveryError, match="invalid api key") as excinfo:
        await client.send(to="user@test.com", subject="subject", html="<p>hi</p>")

    # The provider exception is chained for logs, not exposed as the raise.
    assert isinstance(excinfo.value.__cause__, RuntimeError)
