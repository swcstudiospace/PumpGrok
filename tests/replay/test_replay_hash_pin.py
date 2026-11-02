"""smoke-10m replay hash pin (CONTEXT D-08).

The pinned value is the events.hash that `pumpgrok verify --fixture smoke-10m` prints. The run
happens in an empty working directory (D-09), so an operator var/ledger.sqlite cannot move it.
smoke-10m admits no trade; the trading pin in test_trading_smoke_pin.py guards risk, adapter and
exit edits.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pin_support import SMOKE_10M_EVENTS_HASH, verify_fixture


@pytest.fixture
def clean_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_smoke_10m_events_hash_matches_the_pin(clean_cwd: Path) -> None:
    run = verify_fixture("smoke-10m")
    assert run.events_hash == SMOKE_10M_EVENTS_HASH


def test_smoke_10m_chain_has_seq_two_and_forty_one_events(clean_cwd: Path) -> None:
    run = verify_fixture("smoke-10m")
    assert (run.seq, run.events_read) == (2, 41)


def test_smoke_10m_ledger_lands_under_the_clean_directory(clean_cwd: Path) -> None:
    run = verify_fixture("smoke-10m")
    assert run.ledger == clean_cwd / "var" / "replay" / "smoke-10m" / "ledger.sqlite"
    assert run.ledger.is_file()
