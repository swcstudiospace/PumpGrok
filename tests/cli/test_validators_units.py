"""CLI argument validators and small helpers (R22/R28/R29 boundaries)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from pumpgrok.cli.errors import UsageError
from pumpgrok.cli.validators import (
    _approval_id,
    _human_by,
    _jsonable,
    _ledger_id_or_none,
    _mint,
    _mint_approval_id,
    _report_date,
    _size_sol,
    _slippage_bps,
    _ticket,
    _utc_now,
    size_sol_to_lamports,
)


def test_ticket_accepts_sol_date_form() -> None:
    assert _ticket("SOL-20260101-001") == "SOL-20260101-001"
    for bad in ("SOL-2026-01-01-001", "sol-20260101-001", "SOL-20260101", ""):
        with pytest.raises(UsageError):
            _ticket(bad)


def test_mint_accepts_base58_lengths() -> None:
    assert _mint("1" * 32) == "1" * 32
    for bad in ("1" * 31, "1" * 45, "0" * 40, "O" * 40):
        with pytest.raises(UsageError):
            _mint(bad)


def test_size_sol_parses_positive_decimals() -> None:
    assert _size_sol("0.25") == Decimal("0.25")
    assert size_sol_to_lamports(Decimal("0.25")) == 250_000_000
    for bad in ("0", "-1", "nan", "inf", "abc", ""):
        with pytest.raises(UsageError):
            _size_sol(bad)


def test_slippage_bps_bounds() -> None:
    assert _slippage_bps("0") == 0
    assert _slippage_bps("10000") == 10000
    for bad in ("-1", "10001", "1.5", "x"):
        with pytest.raises(UsageError):
            _slippage_bps(bad)


def test_approval_id_and_minter() -> None:
    minted = _mint_approval_id()
    assert minted.startswith("apr-")
    assert _approval_id(minted) == minted
    for bad in ("apr-x", "APR-01JXXXXXXXXXXXXXXXXXXXXXXX", minted.upper()):
        with pytest.raises(UsageError):
            _approval_id(bad)


def test_human_by_requires_a_human_name() -> None:
    assert _human_by("human:operator", "test") == "human:operator"
    for bad in (None, "operator", "bot-00-chief", "human:bot-00-chief", "human:"):
        with pytest.raises(UsageError):
            _human_by(bad, "test")


def test_utc_now_is_aware() -> None:
    assert _utc_now().tzinfo is not None


def test_jsonable_coerces_floats_recursively() -> None:
    assert _jsonable(1.5) == "1.5"
    assert _jsonable({"a": [1.5, ("x", 2.5)]}) == {"a": ["1.5", ["x", "2.5"]]}
    assert _jsonable("s") == "s"
    assert _jsonable(7) == 7


def test_report_date_defaults_to_today_and_refuses_non_dates() -> None:
    today = _utc_now().strftime("%Y-%m-%d")
    assert _report_date(None, "--since") == today
    assert _report_date("2026-01-31", "--since") == "2026-01-31"
    with pytest.raises(UsageError):
        _report_date("31-01-2026", "--since")


def test_ledger_id_or_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    assert _ledger_id_or_none() == "none"
    ledger = tmp_path / "var" / "ledger.sqlite"
    ledger.parent.mkdir(parents=True)
    db = sqlite3.connect(str(ledger))
    db.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    db.commit()
    db.close()
    assert _ledger_id_or_none() == "none"
    db = sqlite3.connect(str(ledger))
    db.execute("INSERT INTO meta (key, value) VALUES ('ledger_id', 'led-abc')")
    db.commit()
    db.close()
    assert _ledger_id_or_none() == "led-abc"
    ledger.write_bytes(b"not a database")
    assert _ledger_id_or_none() == "none"
