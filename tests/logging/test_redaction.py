"""INV-R-23: secrets are redacted across every log sink.

Owning test for SAFETY_INVARIANTS.md section 3.4 row INV-R-23. Fake
Solana keys (base58 and JSON byte array), seed phrases, Helius/QuickNode
URLs with keys, Telegram tokens, x.ai keys and Authorization headers fed
through every log sink (stderr JSON, the Notifier text path with its
alert file, a LiveWriteAttempted-shaped payload, exception text) come
out masked with first-4-plus-stars; key-based redaction masks secret
named data keys. The G-3 committed-secret regexes find zero matches over
the captured output. (The tree has no rotating log-file handler; the
durable file sink is the notifier alert file, covered here.)

Harness: seeded fixtures only; no wall clock, no network.
"""

from __future__ import annotations

import importlib.util
import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.logging import setup_logging
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.notify.notifier import Notifier

# Synthetic values in the shapes the filter masks. Each line is annotated
# for the G-3 scanner, mirroring tests/test_logging.py.
PLANTED_B58 = "5" + "H" * 85  # pragma: allowlist secret
PLANTED_KEYPAIR = "[" + ",".join(["1"] * 64) + "]"  # pragma: allowlist secret
PLANTED_PHRASE = (  # pragma: allowlist secret
    "abandon abandon abandon abandon abandon abandon "  # pragma: allowlist secret
    "abandon abandon abandon abandon abandon about"  # pragma: allowlist secret
)
PLANTED_HELIUS = (  # pragma: allowlist secret
    "https://mainnet.helius-rpc.com/?api-key="  # pragma: allowlist secret
    "AbCdEfGhIjKlMnOpQrStUvWx1234"  # pragma: allowlist secret
)
PLANTED_QUICKNODE = (  # pragma: allowlist secret
    "https://abc123def456.solana-mainnet.quiknode.pro/"  # pragma: allowlist secret
    "ABCDEFGHIJ1234567890/"  # pragma: allowlist secret
)
PLANTED_TELEGRAM = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"  # pragma: allowlist secret
PLANTED_XAI = "xai-a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"  # pragma: allowlist secret
PLANTED_AUTH = "Bearer xai-a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"  # pragma: allowlist secret

REPO_ROOT = Path(__file__).resolve().parents[2]


def _secrets_gate() -> Any:
    path = REPO_ROOT / "ci" / "gates" / "check_secrets.py"
    spec = importlib.util.spec_from_file_location("check_secrets_redaction", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def root_handlers() -> Iterator[None]:
    root = logging.getLogger()
    saved = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in saved:
            root.removeHandler(handler)
    root.setLevel(level)


class _StubNotifier(Notifier):
    """Real fan-out path with stubbed network edges; records deliveries."""

    def __init__(self, clock: FixtureClock, alert_file: Path) -> None:
        super().__init__(allowlist=["chat-1"], clock=clock, alert_file=alert_file)
        self.telegram_texts: list[str] = []

    async def send_telegram(self, chat_id: str, text: str) -> None:
        self.telegram_texts.append(f"{chat_id}:{text}")

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        raise AssertionError("no webhook in this test")


def _planted() -> list[str]:
    return [
        PLANTED_B58,
        PLANTED_KEYPAIR,
        PLANTED_PHRASE,
        PLANTED_HELIUS,
        PLANTED_QUICKNODE,
        PLANTED_TELEGRAM,
        PLANTED_XAI,
        PLANTED_AUTH,
    ]


async def test_log_redaction(
    root_handlers: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """INV-R-23: every sink masks secrets; G-3 finds zero matches."""
    buffer = io.StringIO()
    setup_logging(mode="paper", profile="paper", environ={}, stream=buffer)
    log = logging.getLogger("pumpgrok.test.redaction23")
    live_payload = {
        "source": "paper",
        "adapter": "live",
        "method": "place",
        "caller_seat": "bot-04-sniper",
        "gate_result_json": json.dumps({"key": PLANTED_B58, "url": PLANTED_HELIUS}),
        "stack_hash": "abc123",
    }
    log.info(
        "gate refused with key %s and token %s header %s",
        PLANTED_XAI,
        PLANTED_TELEGRAM,
        PLANTED_AUTH,
        extra={
            "event": "live_write_attempted",
            "auth": PLANTED_AUTH,
            "mnemonic": PLANTED_PHRASE,
            "keypair": PLANTED_KEYPAIR,
            "endpoint": PLANTED_QUICKNODE,
            "payload": live_payload,
        },
    )
    try:
        raise RuntimeError(f"rpc failed at {PLANTED_HELIUS}")
    except RuntimeError:
        log.exception("trade failed")
    lines = [line for line in buffer.getvalue().splitlines() if line]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["msg"].startswith("gate refused with key xai-")
    assert "123456789:" not in first["msg"]
    assert "Bearer xai-" in first["msg"]
    assert first["data"]["auth"] == "[redacted]"
    assert first["data"]["mnemonic"] == "[redacted]"
    assert first["data"]["keypair"] == "[redacted]"
    assert first["data"]["endpoint"].startswith("https://abc1")
    assert PLANTED_B58 not in json.dumps(first["data"]["payload"])
    assert PLANTED_HELIUS not in json.dumps(first["data"]["payload"])
    gate = _secrets_gate()
    findings = [
        finding
        for number, line in enumerate(lines, 1)
        for finding in gate.scan_line("redacted.jsonl", number, line)
    ]
    assert findings == []

    notifier = _StubNotifier(FixtureClock(start=0.0), tmp_path / "alerts.jsonl")
    await notifier.send(
        severity="critical",
        kind="kill",
        text=f"KILL switch: key {PLANTED_B58} auth {PLANTED_AUTH}",
        ticket_id="SOL-20260101-001",
        fields={"mnemonic": PLANTED_PHRASE, "note": f"see {PLANTED_XAI}"},
        destinations=["chat-1"],
    )
    alerted = (tmp_path / "alerts.jsonl").read_text(encoding="utf-8")
    delivered = "\n".join(notifier.telegram_texts)
    assert notifier.telegram_texts != []
    for secret in (PLANTED_B58, PLANTED_AUTH, PLANTED_PHRASE, PLANTED_XAI):
        assert secret not in alerted
        assert secret not in delivered
    assert "5H" in alerted
    assert "[redacted]" in alerted
    assert "xai-" in delivered
    sink_findings = [
        finding
        for number, line in enumerate(alerted.splitlines(), 1)
        for finding in gate.scan_line("alerts.jsonl", number, line)
    ]
    assert sink_findings == []
    out = capsys.readouterr().out
    for secret in (PLANTED_B58, PLANTED_AUTH):
        assert secret not in out
