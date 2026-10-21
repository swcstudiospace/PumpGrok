"""Abstract Notifier (TOOL-006): stdout+file always on, network allowlisted.

``Notifier.send`` fans one alert out: stdout and the alert file always
receive it; Telegram and webhook sinks only fire for allowlisted
destinations (R39). Network sinks retry with the j8 policy; stdout/file
never retry. Idempotency is ``d(kind, ticket, severity, minute)`` via
:func:`alert_key`, derived from the injected Clock minute.
"""

from __future__ import annotations

import abc
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal

from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from pumpgrok.core.ids import Clock
from pumpgrok.core.tool import RetryPolicy
from pumpgrok.tools.notify.allowlist import partition_destinations

__all__ = [
    "ALERT_KINDS",
    "HttpxNotifier",
    "J8",
    "Notifier",
    "alert_key",
]

ALERT_KINDS: tuple[str, ...] = (
    "rug_flag",
    "halt",
    "breaker",
    "killswitch",
    "escalation",
    "report",
    "unknown_result",
    "bot_restart_exhausted",
    "heartbeat_stale",
    "persistence_down",
    "clock_skew",
    "ledger_inconsistent",
)

AlertSeverity = Literal["info", "warning", "critical"]

J8 = RetryPolicy(attempts=3, base_s=1.0, max_s=8.0)


def _is_retriable_sink_error(exc: BaseException) -> bool:
    """Retry only timeouts and 5xx/429 (D5); 4xx and refusals never retry."""
    if isinstance(exc, TimeoutError):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status >= 500 or status == 429
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return isinstance(status, int) and (status >= 500 or status == 429)


def alert_key(kind: str, ticket_id: str | None, severity: str, clock: Clock) -> str:
    """Derived idempotency key: d(kind, ticket, severity, UTC minute)."""
    minute = datetime.fromtimestamp(clock.now(), UTC).strftime("%Y-%m-%dT%H:%M")
    digest = hashlib.sha256(f"{kind}\n{ticket_id or ''}\n{severity}\n{minute}".encode()).hexdigest()
    return digest[:32]


class Notifier(abc.ABC):
    """Alert fan-out with the network edge abstracted for tests and sinks."""

    def __init__(
        self,
        *,
        allowlist: tuple[str, ...] | list[str],
        clock: Clock,
        alert_file: Path,
    ) -> None:
        self._allowlist = list(allowlist)
        self._clock = clock
        self._alert_file = alert_file
        self._seen_keys: set[str] = set()

    @property
    def allowlist(self) -> list[str]:
        return list(self._allowlist)

    @abc.abstractmethod
    async def send_telegram(self, chat_id: str, text: str) -> None:
        """Deliver to one allowlisted Telegram chat; raise on failure."""

    @abc.abstractmethod
    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        """POST one allowlisted webhook URL; raise on failure."""

    async def send(
        self,
        *,
        severity: str,
        kind: str,
        text: str,
        ticket_id: str | None = None,
        fields: dict[str, Any] | None = None,
        destinations: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Fan out; a repeated key suppresses every sink (stdout/file too)."""
        key = idempotency_key or alert_key(kind, ticket_id, severity, self._clock)
        if key in self._seen_keys:
            return {"delivered": [], "suppressed": True}
        self._seen_keys.add(key)
        requested = destinations if destinations is not None else list(self._allowlist)
        allowed, refused = partition_destinations(requested, self._allowlist)
        delivered: list[dict[str, Any]] = []
        self._write_stdout_and_file(severity, kind, text, ticket_id, fields or {})
        delivered.append({"sink": "stdout+file", "ok": True, "error": None})
        for destination in allowed:
            try:
                if destination.startswith(("http://", "https://")):
                    payload = {
                        "event": kind,
                        "text": text,
                        "ticket_id": ticket_id,
                        "fields": fields or {},
                    }
                    await self._with_j8(lambda: self.send_webhook(destination, payload))
                else:
                    await self._with_j8(lambda: self.send_telegram(destination, text))
                delivered.append({"sink": destination, "ok": True, "error": None})
            except Exception as exc:  # noqa: BLE001 - sinks report, never raise
                delivered.append({"sink": destination, "ok": False, "error": str(exc)})
        for destination in refused:
            delivered.append(
                {"sink": destination, "ok": False, "error": "not_allowlisted"}
            )
        return {"delivered": delivered, "suppressed": False}

    async def _with_j8(self, make_coro: Callable[[], Any]) -> Any:
        """Retry a coroutine factory (a coroutine object cannot be re-awaited)."""
        policy = J8
        async for attempt in AsyncRetrying(
            sleep=self._clock.sleep,
            wait=wait_random_exponential(multiplier=policy.base_s, max=policy.max_s),
            stop=stop_after_attempt(policy.attempts),
            retry=retry_if_exception(_is_retriable_sink_error),
            reraise=True,
        ):
            with attempt:
                return await make_coro()
        raise AssertionError("unreachable")

    def _write_stdout_and_file(
        self,
        severity: str,
        kind: str,
        text: str,
        ticket_id: str | None,
        fields: dict[str, Any],
    ) -> None:
        line = f"[pumpgrok:{severity}] {kind} {ticket_id or '-'} {text}"
        print(line)
        self._alert_file.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "severity": severity,
            "kind": kind,
            "ticket_id": ticket_id,
            "text": text,
            "fields": fields,
        }
        with open(self._alert_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


class HttpxNotifier(Notifier):
    """Concrete Notifier composing the Telegram and webhook senders."""

    def __init__(
        self,
        *,
        telegram: Any,
        webhook: Any,
        allowlist: tuple[str, ...] | list[str],
        clock: Clock,
        alert_file: Path,
    ) -> None:
        super().__init__(allowlist=allowlist, clock=clock, alert_file=alert_file)
        self._telegram = telegram
        self._webhook = webhook

    async def send_telegram(self, chat_id: str, text: str) -> None:
        await self._telegram.send(chat_id, text)

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        await self._webhook.send(url, payload)
