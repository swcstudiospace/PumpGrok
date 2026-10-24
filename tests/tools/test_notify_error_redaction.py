"""Notify failures: no URL in delivered errors; a local write failure never blocks sinks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import httpx

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.notify.notifier import STDOUT_FILE_SINK, HttpxNotifier
from pumpgrok.tools.notify.telegram import TelegramSender
from pumpgrok.tools.notify.webhook import WebhookSender

START = 1469918176.385
SECRET_PATH = "SECRET-PATH-TOKEN"
WEBHOOK_URL = f"https://hooks.example/services/{SECRET_PATH}"


class _InstantRetryClock(FixtureClock):
    """Virtual time whose sleep advances the clock at once, so retries never wait."""

    async def sleep(self, seconds: float) -> None:
        self.advance_to(self.now() + seconds)


def _notifier(alert_file: Path, handler) -> HttpxNotifier:
    clock = _InstantRetryClock(start=START)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpxNotifier(
        telegram=TelegramSender(client, token="test-token"),
        webhook=WebhookSender(client, clock),
        allowlist=[WEBHOOK_URL],
        clock=clock,
        alert_file=alert_file,
    )


def _row(out: dict, sink: str) -> dict:
    return next(row for row in out["delivered"] if row["sink"] == sink)


async def test_webhook_500_error_row_omits_url(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream failure")

    notifier = _notifier(tmp_path / "alerts.log", handler)
    out = await notifier.send(severity="critical", kind="halt", text="stop")

    row = _row(out, WEBHOOK_URL)
    assert row["ok"] is False
    assert row["error"] == "HTTP 500"
    assert SECRET_PATH not in row["error"]
    assert WEBHOOK_URL not in row["error"]


async def test_webhook_transport_error_row_names_class_not_url(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    notifier = _notifier(tmp_path / "alerts.log", handler)
    out = await notifier.send(severity="critical", kind="halt", text="stop")

    row = _row(out, WEBHOOK_URL)
    assert row["ok"] is False
    assert row["error"] == "WebhookSendError"
    assert SECRET_PATH not in row["error"]


async def test_unwritable_alert_file_still_delivers_to_network_sink(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("occupied", encoding="utf-8")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    notifier = _notifier(blocker / "alerts.log", handler)
    out = await notifier.send(severity="critical", kind="halt", text="stop")

    assert seen == [WEBHOOK_URL]
    assert _row(out, WEBHOOK_URL) == {"sink": WEBHOOK_URL, "ok": True, "error": None}
    file_row = _row(out, STDOUT_FILE_SINK)
    assert file_row["ok"] is False
    assert file_row["error"].startswith("alert file write failed: ")


async def test_failed_file_write_is_retried_on_next_send(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("occupied", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    notifier = _notifier(blocker / "alerts.log", handler)
    first = await notifier.send(severity="critical", kind="halt", text="stop")
    assert _row(first, STDOUT_FILE_SINK)["ok"] is False

    blocker.unlink()
    second = await notifier.send(severity="critical", kind="halt", text="stop")
    assert _row(second, STDOUT_FILE_SINK) == {"sink": STDOUT_FILE_SINK, "ok": True, "error": None}
    assert (tmp_path / "not-a-directory" / "alerts.log").exists()
