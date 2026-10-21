"""Telegram sink for the Notifier (TOOL-006, D6).

The token arrives via env ``PUMPGROK_TELEGRAM_TOKEN`` only: never TOML,
never logged, never in an exception message. ``chat_id`` must already be in
``notify.allowlist`` before this sink is reached.
"""

from __future__ import annotations

import os

import httpx

__all__ = ["TELEGRAM_ENV_VAR", "TelegramSender", "read_telegram_token"]

TELEGRAM_ENV_VAR = "PUMPGROK_TELEGRAM_TOKEN"


def read_telegram_token() -> str:
    """Token from the environment; empty when unset (sink then refuses)."""
    return os.environ.get(TELEGRAM_ENV_VAR, "").strip()


class TelegramSender:
    """Send Telegram ``sendMessage`` calls with an injected httpx client."""

    def __init__(self, client: httpx.AsyncClient, token: str = "") -> None:
        self._client = client
        self._token = token or read_telegram_token()

    async def send(self, chat_id: str, text: str) -> None:
        """POST sendMessage; failures are sanitized so the token never leaks."""
        if not self._token:
            raise RuntimeError("telegram token is unset; refusing Telegram send")
        try:
            response = await self._client.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"telegram send failed: {type(exc).__name__}") from None
