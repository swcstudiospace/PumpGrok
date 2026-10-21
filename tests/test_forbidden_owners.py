"""forbidden_owners enforcement: sniper/exit seats refused (STRUCT-005, T-02-10)."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from pumpgrok.cli import EXIT_CONFIG, main

TICKET = "SOL-20260101-001"
MINT = "So11111111111111111111111111111111111111112"
APPROVAL = "apr-01ARZ3NDEKTSV4RRFFQ69G5FAV"

TRADE_FLAGS = [
    "--ticket",
    TICKET,
    "--mint",
    MINT,
    "--size-sol",
    "0.5",
    "--slippage-bps",
    "100",
    "--approval-id",
    APPROVAL,
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip PUMPGROK_* and secret-shaped names so each test sets exactly what it needs."""
    for name in list(os.environ):
        if name.startswith("PUMPGROK_") or "KEY" in name.upper():
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def root_handlers() -> Iterator[None]:
    """main() installs a handler bound to the test's stderr; remove it afterwards."""
    root = logging.getLogger()
    level = root.level
    yield
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    root.setLevel(level)


def _paper_verb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, side: str, seat: str) -> int:
    monkeypatch.chdir(tmp_path)
    return main(["paper", side, *TRADE_FLAGS, "--seat", seat])


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("seat", ["sniper", "exit"])
def test_forbidden_seats_refused_on_paper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    side: str,
    seat: str,
) -> None:
    code = _paper_verb(tmp_path, monkeypatch, side, seat)
    assert code == EXIT_CONFIG
    assert "refused" in capsys.readouterr().err


@pytest.mark.parametrize(
    "verb",
    [["state", "status"], ["state", "halt"], ["state", "autonomy", "manual-ticket"]],
)
@pytest.mark.parametrize("seat", ["sniper", "exit"])
def test_forbidden_seats_refused_on_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    verb: list[str],
    seat: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main([*verb, "--seat", seat]) == EXIT_CONFIG
    assert "refused" in capsys.readouterr().err


def test_allowed_seat_rejected_without_valid_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Phase 3 (R63, plan 03-04): the desk seat reaches the verb, but no
    # approval_id can be valid yet (RiskEngine plus the PaperAdapter place
    # transaction land in Phase 4), so the trade is refused with exit 1
    # instead of the old absent-verb exit 5. No OrderPlaced row is written.
    code = _paper_verb(tmp_path, monkeypatch, "buy", "desk")
    assert code == EXIT_CONFIG
    assert "no valid approval_id" in capsys.readouterr().err


def test_bad_ticket_is_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "paper",
            "buy",
            "--ticket",
            "nope",
            "--mint",
            MINT,
            "--size-sol",
            "0.5",
            "--slippage-bps",
            "100",
            "--approval-id",
            APPROVAL,
            "--seat",
            "desk",
        ]
    )
    assert code == EXIT_CONFIG
    assert "bad --ticket" in capsys.readouterr().err
