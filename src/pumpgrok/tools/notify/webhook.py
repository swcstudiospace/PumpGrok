"""Generic webhook sink for the Notifier (TOOL-006, D6).

POSTs ``{event, text, fields, ts}`` to allowlisted URLs only; the allowlist
check happens in :class:`Notifier` before this sink is reached.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from pumpgrok.core.ids import Clock

__all__ = ["WebhookSendError", "WebhookSender"]


class WebhookSendError(RuntimeError):
    """Sanitized webhook failure carrying the HTTP status for the retry classifier.

    The message names only the status or exception type, never the request URL,
    so a secret carried in the webhook path cannot reach an exception message.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class WebhookSender:
    """POST alert payloads with an injected httpx client."""

    def __init__(self, client: httpx.AsyncClient, clock: Clock) -> None:
        self._client = client
        self._clock = clock

    async def send(self, url: str, payload: dict[str, Any]) -> None:
        """POST the payload with a UTC timestamp; raise on HTTP failure."""
        body = {
            **payload,
            "ts": datetime.fromtimestamp(self._clock.now(), UTC).isoformat(),
        }
        try:
            response = await self._client.post(url, json=body)
            response.raise_for_status()
        except httpx.TimeoutException:
            raise TimeoutError("webhook send timed out") from None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise WebhookSendError(f"webhook send failed: HTTP {status}", status) from None
        except httpx.HTTPError as exc:
            raise WebhookSendError(f"webhook send failed: {type(exc).__name__}") from None
