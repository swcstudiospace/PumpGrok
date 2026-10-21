"""Generic webhook sink for the Notifier (TOOL-006, D6).

POSTs ``{event, text, fields, ts}`` to allowlisted URLs only; the allowlist
check happens in :class:`Notifier` before this sink is reached.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from pumpgrok.core.ids import Clock

__all__ = ["WebhookSender"]


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
        response = await self._client.post(url, json=body)
        response.raise_for_status()
