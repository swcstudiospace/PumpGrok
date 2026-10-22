"""Regression: Telegram retries, token-free errors, per-destination delivery (PR6 r4).

Finding 7: a 429 or 5xx Telegram failure is retried; a 400 or 401 is not.
Finding 4: the bot token never appears in an error, and the redaction pattern
    masks it in a Telegram request URL.
Finding 6: each destination has its own bound below the registry budget, slow
    destinations do not delay fast ones, and a failed sink is retried, not
    treated as delivered.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from pumpgrok.logging.redaction import redact_text
from pumpgrok.replay.clock import WallClock
from pumpgrok.tools.notify.alert import ALERT_SPEC
from pumpgrok.tools.notify.notifier import DESTINATION_TIMEOUT_S, HttpxNotifier, Notifier
from pumpgrok.tools.notify.telegram import TelegramSender, TelegramSendError
from pumpgrok.tools.notify.webhook import WebhookSender

TOKEN = "123456789:AAFakeSyntheticTelegramTokenValue_0"
CHAT = "12345"
SLOW_URL = "https://slow.example.test/hook"
FAST_URL = "https://fast.example.test/hook"
KEY = "k" * 32


def _http_notifier(tmp_path: Path, handler: Any) -> HttpxNotifier:
    clock = WallClock()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpxNotifier(
        telegram=TelegramSender(client, token=TOKEN),
        webhook=WebhookSender(client, clock),
        allowlist=[CHAT],
        clock=clock,
        alert_file=tmp_path / "alerts.log",
    )


class _ScriptedNotifier(Notifier):
    """Notifier whose sinks are plain callables, so timing and failures are scripted."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        telegram: Any = None,
        webhook: Any = None,
        destination_timeout_s: float = DESTINATION_TIMEOUT_S,
    ) -> None:
        super().__init__(
            allowlist=[CHAT, SLOW_URL, FAST_URL],
            clock=WallClock(),
            alert_file=tmp_path / "alerts.log",
            destination_timeout_s=destination_timeout_s,
        )
        self._telegram = telegram
        self._webhook = webhook

    async def send_telegram(self, chat_id: str, text: str) -> None:
        if self._telegram is not None:
            await self._telegram(chat_id, text)

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        if self._webhook is not None:
            await self._webhook(url, payload)


# -- finding 7: status-aware Telegram retries ---------------------------------


async def test_telegram_429_is_retried_then_delivered(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"ok": False})
        return httpx.Response(200, json={"ok": True})

    out = await _http_notifier(tmp_path, handler).send(
        severity="critical", kind="halt", text="stop", destinations=[CHAT]
    )
    assert len(calls) == 2
    assert out["delivered"][-1] == {"sink": CHAT, "ok": True, "error": None}


async def test_telegram_400_is_not_retried(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"ok": False})

    out = await _http_notifier(tmp_path, handler).send(
        severity="critical", kind="halt", text="stop", destinations=[CHAT]
    )
    assert len(calls) == 1
    row = out["delivered"][-1]
    assert row["sink"] == CHAT and row["ok"] is False
    assert "HTTP 400" in row["error"]
    assert TOKEN not in str(out)


async def test_telegram_401_is_not_retried(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"ok": False})

    await _http_notifier(tmp_path, handler).send(
        severity="critical", kind="halt", text="stop", destinations=[CHAT]
    )
    assert len(calls) == 1


async def test_telegram_error_keeps_status_and_no_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(TelegramSendError) as info:
        await TelegramSender(client, token=TOKEN).send(CHAT, "hi")
    assert info.value.status_code == 503
    assert TOKEN not in str(info.value)
    assert TOKEN not in repr(info.value)


async def test_telegram_timeout_is_a_retriable_timeout_without_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(TimeoutError) as info:
        await TelegramSender(client, token=TOKEN).send(CHAT, "hi")
    assert TOKEN not in str(info.value)


# -- finding 4: redaction of the token in request URLs -------------------------


def test_redaction_masks_telegram_token_in_request_path() -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    masked = redact_text(url)
    assert TOKEN not in masked
    assert masked.startswith("https://api.telegram.org/bot1234")


def test_redaction_still_masks_plain_telegram_token() -> None:
    assert TOKEN not in redact_text(f"token={TOKEN}")


# -- finding 6: per-destination bounds and per-sink idempotency ----------------


def test_destination_bound_sits_below_registry_budget() -> None:
    assert 0 < DESTINATION_TIMEOUT_S < ALERT_SPEC.timeout_s


async def test_slow_destination_does_not_delay_fast_one(tmp_path: Path) -> None:
    async def slow(url: str, payload: dict[str, Any]) -> None:
        await asyncio.sleep(5.0)

    notifier = _ScriptedNotifier(tmp_path, webhook=slow, destination_timeout_s=0.3)
    start = time.monotonic()
    out = await notifier.send(
        severity="critical", kind="halt", text="stop", destinations=[SLOW_URL, CHAT]
    )
    elapsed = time.monotonic() - start
    rows = {d["sink"]: d for d in out["delivered"]}
    assert rows[CHAT]["ok"] is True
    assert rows[SLOW_URL]["ok"] is False
    assert "timed out" in rows[SLOW_URL]["error"]
    assert elapsed < 2.0  # bounded by the slow sink's own 0.3s, not its 5s sleep


async def test_failed_destination_is_retried_not_treated_as_delivered(tmp_path: Path) -> None:
    attempts: list[str] = []

    async def flaky(chat_id: str, text: str) -> None:
        attempts.append(chat_id)
        if len(attempts) == 1:
            raise RuntimeError("sink refused")

    notifier = _ScriptedNotifier(tmp_path, telegram=flaky)
    first = await notifier.send(
        severity="critical", kind="halt", text="stop", destinations=[CHAT], idempotency_key=KEY
    )
    assert first["delivered"][-1]["ok"] is False

    second = await notifier.send(
        severity="critical", kind="halt", text="stop", destinations=[CHAT], idempotency_key=KEY
    )
    assert second["suppressed"] is False
    assert second["delivered"] == [{"sink": CHAT, "ok": True, "error": None}]

    third = await notifier.send(
        severity="critical", kind="halt", text="stop", destinations=[CHAT], idempotency_key=KEY
    )
    assert third == {"delivered": [], "suppressed": True}
    assert len(attempts) == 2
    # stdout and the alert file were written once, on the first call only.
    assert len((tmp_path / "alerts.log").read_text(encoding="utf-8").splitlines()) == 1


async def test_delivered_sink_is_not_resent_when_another_sink_retries(tmp_path: Path) -> None:
    sent: list[str] = []

    async def fast(chat_id: str, text: str) -> None:
        sent.append(chat_id)

    async def fail_once(url: str, payload: dict[str, Any]) -> None:
        if not any(s == url for s in sent):
            sent.append(url)
            raise RuntimeError("down")
        sent.append(url)

    notifier = _ScriptedNotifier(tmp_path, telegram=fast, webhook=fail_once)
    await notifier.send(
        severity="warning",
        kind="breaker",
        text="tripped",
        destinations=[CHAT, FAST_URL],
        idempotency_key=KEY,
    )
    out = await notifier.send(
        severity="warning",
        kind="breaker",
        text="tripped",
        destinations=[CHAT, FAST_URL],
        idempotency_key=KEY,
    )
    assert [d["sink"] for d in out["delivered"]] == [FAST_URL]
    assert sent.count(CHAT) == 1  # the chat that already succeeded was not re-sent
