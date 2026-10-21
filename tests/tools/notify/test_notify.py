"""Notify + alert tests (TOOL-006): allowlist gating, stdout+file, j8, keys."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import httpx
import pytest
from pydantic import ValidationError

from pumpgrok.replay.clock import FixtureClock, WallClock
from pumpgrok.tools.notify.alert import ALERT_SPEC, AlertIn, build_alert_tool
from pumpgrok.tools.notify.allowlist import is_allowlisted, partition_destinations
from pumpgrok.tools.notify.notifier import ALERT_KINDS, HttpxNotifier, alert_key
from pumpgrok.tools.notify.telegram import TelegramSender
from pumpgrok.tools.notify.webhook import WebhookSender

START = 1469918176.385
ALLOW = ["12345", "https://hooks.example/x"]


def _notifier(tmp_path: Path, handler, allowlist=ALLOW) -> tuple[HttpxNotifier, FixtureClock, list]:
    clock = FixtureClock(start=START)
    seen: list = []
    transport = httpx.MockTransport(handler(seen))  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    notifier = HttpxNotifier(
        telegram=TelegramSender(client, token="test-token"),
        webhook=WebhookSender(client, clock),
        allowlist=allowlist,
        clock=clock,
        alert_file=tmp_path / "alerts.log",
    )
    return notifier, clock, seen


def _ok(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    return handler


def test_allowlist_gating() -> None:
    assert is_allowlisted("12345", ALLOW)
    assert not is_allowlisted("99999", ALLOW)
    assert not is_allowlisted("12345", [])
    allowed, refused = partition_destinations(["12345", "evil"], ALLOW)
    assert allowed == ["12345"]
    assert refused == ["evil"]


def test_escalation_kinds_present() -> None:
    assert len(ALERT_KINDS) == 12
    for kind in ALERT_KINDS:
        AlertIn(severity="warning", kind=kind, text="t")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        AlertIn(severity="warning", kind="tweet_this", text="t")  # type: ignore[arg-type]


def test_alert_key_shape_and_stability() -> None:
    clock = FixtureClock(start=START)
    first = alert_key("halt", "SOL-20260201-001", "critical", clock)
    assert len(first) == 32
    assert alert_key("halt", "SOL-20260201-001", "critical", clock) == first
    assert alert_key("halt", None, "critical", clock) != first
    assert alert_key("breaker", "SOL-20260201-001", "critical", clock) != first


async def test_non_allowlisted_destination_never_sent(tmp_path: Path) -> None:
    notifier, _, seen = _notifier(tmp_path, _ok)
    out = await notifier.send(
        severity="critical", kind="halt", text="stop", destinations=["evil-node"]
    )
    assert seen == []
    assert out["suppressed"] is False
    assert out["delivered"][-1] == {
        "sink": "evil-node",
        "ok": False,
        "error": "not_allowlisted",
    }
    lines = (tmp_path / "alerts.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["kind"] == "halt"


async def test_stdout_and_file_always_on_empty_allowlist(tmp_path: Path) -> None:
    notifier, _, seen = _notifier(tmp_path, _ok, allowlist=[])
    out = await notifier.send(severity="info", kind="report", text="daily")
    assert seen == []
    assert out["delivered"] == [{"sink": "stdout+file", "ok": True, "error": None}]
    assert (tmp_path / "alerts.log").is_file()


async def test_webhook_retry_then_delivery(tmp_path: Path) -> None:
    calls: list = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(500, json={"ok": False})
        return httpx.Response(200, json={"ok": True})

    clock = WallClock()
    transport = httpx.MockTransport(flaky)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    notifier = HttpxNotifier(
        telegram=TelegramSender(client, token="t"),
        webhook=WebhookSender(client, clock),
        allowlist=["https://hooks.example/x"],
        clock=clock,
        alert_file=tmp_path / "alerts.log",
    )
    out = await notifier.send(
        severity="warning",
        kind="breaker",
        text="tripped",
        destinations=["https://hooks.example/x"],
    )
    assert len(calls) == 2
    assert out["delivered"][-1]["ok"] is True


async def test_idempotent_repeat_suppressed(tmp_path: Path) -> None:
    notifier, _, _ = _notifier(tmp_path, _ok)
    tool = build_alert_tool(notifier, FixtureClock(start=START))
    first = await tool(
        AlertIn(
            severity="critical",
            kind="killswitch",
            text="set",
            idempotency_key="k" * 32,
        )
    )
    assert first.suppressed is False
    second = await tool(
        AlertIn(
            severity="critical",
            kind="killswitch",
            text="set",
            idempotency_key="k" * 32,
        )
    )
    assert second.suppressed is True
    assert second.delivered == []
    assert ALERT_SPEC.side_effect.value == "paper-write"
    assert ALERT_SPEC.timeout_s == 10.0
    assert ALERT_SPEC.rate_limit_key == "notify"
