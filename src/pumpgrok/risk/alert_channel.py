"""Alert channel: the inbound kill source polled on every risk cycle (RISK-004, R22).

The channel returns raw text lines from allowlisted senders. ``KillSwitch.absorb_alerts`` runs
each line through ``parse_kill_line``, then calls ``commit``. A desk without a configured channel
polls nothing.

Offset durability: the next update offset is persisted under the desk data dir
(``alert_offset``) by ``commit``, after the lines of a poll are handled. A restarted process
resumes from that offset, so a consumed KILL is never read again, even after a human clears the
switch. A crash before ``commit`` redelivers the lines, which is the safe direction. An unreadable
offset file resumes from 0 with a warning: re-reading recent kills is conservative, and it is
logged.

Failure policy: ``poll`` never raises. A failed or slow getUpdates returns no lines, is logged
with the exception type only (never the URL, so never the bot token), and leaves the offset where
it was so the next check retries.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import httpx

from pumpgrok.logging.redaction import RedactionFilter

__all__ = [
    "AlertChannel",
    "EmptyAlertChannel",
    "TelegramAlertChannel",
    "build_alert_channel",
]

log = logging.getLogger(__name__)

#: Per-request ceiling. The risk cycle waits at most this long on Telegram, then continues.
TELEGRAM_TIMEOUT_S = 2.0

#: File under the desk data dir holding the committed next update offset.
OFFSET_FILE_NAME = "alert_offset"

#: Telegram chat ids are integers (groups are negative). Webhook URLs never match.
_CHAT_ID_OK = frozenset("0123456789-")

#: httpx and httpcore log full request URLs at INFO, and a Telegram URL carries the bot token.
_HTTP_CLIENT_LOGGERS: tuple[str, ...] = ("httpx", "httpcore")


class AlertChannel(Protocol):
    """One poll returns the raw text of the messages received since the last commit."""

    def poll(self) -> list[str]:
        """Message texts from allowlisted senders, oldest first. Never raises."""
        ...

    def commit(self) -> None:
        """Persist the consumed offset once the lines of this poll are handled. Never raises."""
        ...


class EmptyAlertChannel:
    """The unconfigured channel: polls nothing, changes nothing."""

    def poll(self) -> list[str]:
        return []

    def commit(self) -> None:
        return None


def _redact_http_client_logs() -> None:
    """Mask bot tokens in httpx/httpcore records before any handler sees them (idempotent)."""
    for name in _HTTP_CLIENT_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactionFilter) for f in logger.filters):
            logger.addFilter(RedactionFilter())


def _load_offset(path: Path) -> int:
    """The committed offset, or 0 when none is stored (first run) or it is unreadable."""
    if not path.exists():
        return 0
    try:
        value = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        log.warning("alert channel offset file is unreadable; resuming from update 0")
        return 0
    return max(value, 0)


class TelegramAlertChannel:
    """Telegram getUpdates source. Only allowlisted chat ids yield text."""

    def __init__(
        self,
        *,
        token: str,
        allowed_chat_ids: frozenset[str],
        client: httpx.Client,
        state_dir: Path,
    ) -> None:
        self._token = token
        self._allowed = allowed_chat_ids
        self._client = client
        self._offset_path = state_dir / OFFSET_FILE_NAME
        self._committed = _load_offset(self._offset_path)
        # ``_offset`` is what getUpdates asks for: it advances only once a commit persisted it.
        # ``_next`` is where the lines just returned would end; it is never used for requests.
        self._offset = self._committed
        self._next = self._committed
        _redact_http_client_logs()

    def poll(self) -> list[str]:
        try:
            response = self._client.get(
                f"https://api.telegram.org/bot{self._token}/getUpdates",
                params={"offset": self._offset, "timeout": 0, "allowed_updates": '["message"]'},
            )
            response.raise_for_status()
            body = response.json()
            updates = body.get("result") if isinstance(body, dict) else None
            if not isinstance(updates, list):
                raise ValueError("getUpdates result is not a list")
        except httpx.HTTPStatusError as exc:
            log.warning("telegram getUpdates failed: HTTP %s", exc.response.status_code)
            return []
        except Exception as exc:  # any transport, decode or shape failure: retry next check
            log.warning("telegram getUpdates failed: %s", type(exc).__name__)
            return []
        return self._accept(updates)

    def commit(self) -> None:
        """Persist the next offset atomically, then advance the request offset to it.

        Called only after every line of the poll is handled. A write failure leaves the request
        offset where it was, so Telegram redelivers the same updates on the next poll.
        """
        if self._next <= self._committed:
            return
        tmp = self._offset_path.with_suffix(".tmp")
        try:
            self._offset_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(str(self._next), encoding="utf-8")
            os.replace(tmp, self._offset_path)
        except OSError as exc:
            log.warning("alert channel could not persist its offset: %s", type(exc).__name__)
            return
        self._committed = self._next
        self._offset = self._next

    def _accept(self, updates: list[Any]) -> list[str]:
        lines: list[str] = []
        for update in updates:
            if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
                continue
            # Every update, allowlisted or not, is confirmed once commit() persists the offset.
            self._next = max(self._next, update["update_id"] + 1)
            message = update.get("message")
            if not isinstance(message, dict):
                continue
            chat = message.get("chat")
            chat_id = str(chat.get("id", "")) if isinstance(chat, dict) else ""
            text = message.get("text")
            if not isinstance(text, str):
                continue
            if chat_id not in self._allowed:
                log.warning("alert channel ignored a message from non-allowlisted chat %s", chat_id)
                continue
            lines.append(text)
        return lines


def build_alert_channel(
    *,
    token: str,
    allowlist: Sequence[str],
    state_dir: Path,
    client: httpx.Client | None = None,
) -> AlertChannel:
    """Telegram channel only when a bot token and at least one chat id are configured.

    ``state_dir`` is the desk data dir; the committed offset lives there.
    """
    chat_ids = frozenset(
        entry for entry in allowlist if entry and set(entry) <= _CHAT_ID_OK and entry.strip("-")
    )
    if not token or not chat_ids:
        return EmptyAlertChannel()
    return TelegramAlertChannel(
        token=token,
        allowed_chat_ids=chat_ids,
        client=client if client is not None else httpx.Client(timeout=TELEGRAM_TIMEOUT_S),
        state_dir=state_dir,
    )
