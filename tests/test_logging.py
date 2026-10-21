"""Redacted single-line JSON logging (OBS-001, FOUNDATION_STACK 5.1-5.3)."""

from __future__ import annotations

import io
import json
import logging
import re
from collections.abc import Iterator

import pytest

from pumpgrok.logging import setup_logging

# Synthetic values in the shapes the filter masks. Each line is annotated for the G-3 scanner.
PLANTED_XAI = "xai-a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"  # pragma: allowlist secret
PLANTED_JWT = (
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"  # pragma: allowlist secret
)
PLANTED_TELEGRAM = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"  # pragma: allowlist secret
PLANTED_CONN = "postgresql://grokuser:hunter2pw@db.internal/desk"  # pragma: allowlist secret
PLANTED_MNEMONIC = (
    "legal winner thank year wave sausage worth useful legal winner"  # pragma: allowlist secret
)


@pytest.fixture
def root_handlers() -> Iterator[None]:
    """Restore the root logger after each test; setup_logging installs one handler on it."""
    root = logging.getLogger()
    saved = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in saved:
            root.removeHandler(handler)
    root.setLevel(level)


def _lines(buffer: io.StringIO) -> list[str]:
    return [line for line in buffer.getvalue().splitlines() if line]


def test_log_redaction(root_handlers: None) -> None:
    buffer = io.StringIO()
    setup_logging(mode="paper", profile="paper", environ={}, stream=buffer)
    logger = logging.getLogger("pumpgrok.test.redaction")
    logger.info(
        f"keys {PLANTED_XAI} and {PLANTED_CONN} seen",
        extra={
            "event": "probe",
            "rpc": f"see {PLANTED_JWT}",
            "bot_token": "benign-looking-value",
            "mnemonic": PLANTED_MNEMONIC,
            "nested": {"note": f"tg {PLANTED_TELEGRAM}", "seed": 7},
            "items": [PLANTED_XAI, "plain"],
        },
    )
    (line,) = _lines(buffer)
    for planted in (PLANTED_XAI, PLANTED_JWT, PLANTED_TELEGRAM, PLANTED_CONN, PLANTED_MNEMONIC):
        assert planted not in line
    record = json.loads(line)
    assert record["msg"].startswith("keys xai-*")
    assert record["data"]["bot_token"] == "[redacted]"
    assert record["data"]["mnemonic"] == "[redacted]"
    assert record["data"]["nested"]["seed"] == "[redacted]"
    assert record["data"]["nested"]["note"].startswith("tg 1234*")
    assert record["data"]["items"][0].startswith("xai-*")
    assert record["data"]["items"][1] == "plain"
    assert record["data"]["rpc"].startswith("see eyJh*")


def test_every_record_carries_the_stack_fields(root_handlers: None) -> None:
    buffer = io.StringIO()
    setup_logging(mode="paper", profile="paper", environ={}, stream=buffer)
    logging.getLogger("pumpgrok.test.fields").info(
        "order placed", extra={"event": "order_placed", "mint": "MintX", "units": 3}
    )
    (line,) = _lines(buffer)
    record = json.loads(line)
    assert set(record) == {
        "ts",
        "level",
        "logger",
        "msg",
        "event",
        "correlation_id",
        "seat",
        "ticket_id",
        "mint",
        "mode",
        "profile",
        "data",
    }
    assert list(record) == sorted(record)
    assert record["level"] == "INFO"
    assert record["logger"] == "pumpgrok.test.fields"
    assert record["event"] == "order_placed"
    assert record["mint"] == "MintX"
    assert record["mode"] == "paper"
    assert record["profile"] == "paper"
    assert record["data"] == {"units": 3}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", record["ts"])
    assert ", " not in line and ": " not in line  # compact separators


def test_text_mode_requires_dev_profile(root_handlers: None) -> None:
    text_buffer = io.StringIO()
    setup_logging(
        mode="paper",
        profile="dev",
        environ={"PUMPGROK_LOG_JSON": "false"},
        stream=text_buffer,
    )
    logging.getLogger("pumpgrok.test.text").info("hello dev")
    text_line = _lines(text_buffer)[0]
    with pytest.raises(json.JSONDecodeError):
        json.loads(text_line)
    assert "hello dev" in text_line

    ignored_buffer = io.StringIO()
    setup_logging(
        mode="paper",
        profile="paper",
        environ={"PUMPGROK_LOG_JSON": "false"},
        stream=ignored_buffer,
    )
    logging.getLogger("pumpgrok.test.text").info("hello paper")
    assert json.loads(_lines(ignored_buffer)[0])["msg"] == "hello paper"


def test_dev_text_traceback_is_redacted(root_handlers: None) -> None:
    buffer = io.StringIO()
    setup_logging(
        mode="paper",
        profile="dev",
        environ={"PUMPGROK_LOG_JSON": "false"},
        stream=buffer,
    )
    try:
        raise RuntimeError(f"rpc failed at {PLANTED_CONN}")
    except RuntimeError:
        logging.getLogger("pumpgrok.test.devexc").exception("call failed")
    text = buffer.getvalue()
    assert "Traceback" in text
    assert PLANTED_CONN not in text
    assert "hunter2pw" not in text


def test_exception_text_is_redacted(root_handlers: None) -> None:
    buffer = io.StringIO()
    setup_logging(mode="paper", profile="paper", environ={}, stream=buffer)
    try:
        raise RuntimeError(f"rpc failed at {PLANTED_CONN}")
    except RuntimeError:
        logging.getLogger("pumpgrok.test.exc").exception("call failed")
    (line,) = _lines(buffer)
    assert PLANTED_CONN not in line
    record = json.loads(line)
    assert record["exc"]["type"] == "RuntimeError"
    assert "hunter2pw" not in record["exc"]["msg"]
