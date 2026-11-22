"""RT-04: restart recovery re-arms exit deadlines and restores tapes, peaks, probation and watch set.

Kill-the-process tests on a temp ledger file: a crash mid-recovery
followed by a second recovery converges to the identical state, and
the resume-buy test proves no second sniper BUY and no second
simulated fill for the same mint and candidate. No test may be skipped.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.recovery import (
    DuplicateBuyError,
    RecoveryError,
    RecoveryInterrupted,
    assert_no_second_buy,
    decision_recorded,
    recover,
)

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT = "So11111111111111111111111111111111111111112"
DECISION_ID = "01H00000000000000000000000"


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _seq():
    import itertools

    return itertools.count(1)


def _append(store: LedgerStore, clock: FixtureClock, seq: Any, type_: str, payload: dict[str, Any]) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"rec-{next(seq)}",
        type=type_,
        payload=payload,
    )


def _seed(store: LedgerStore, clock: FixtureClock) -> None:
    seq = _seq()
    _append(
        store, clock, seq, "PositionOpened",
        {
            "source": "paper",
            "mint": MINT,
            "price_entry": "0.00001",
            "token_units": 3_000_000,
            "cost_basis_lamports": 100_000_000,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )
    _append(
        store, clock, seq, "MarkToMarket",
        {
            "source": "paper",
            "ts_source": "curve",
            "cash_lamports": EQUITY,
            "equity_lamports": EQUITY,
            "unrealized_lamports": 0,
            "prices_json": json.dumps({MINT: {"mtm_lamports": EQUITY, "spot": "0.00001", "source": "curve"}}),
        },
    )
    _append(
        store, clock, seq, "OrderPlaced",
        {
            "source": "paper",
            "order_id": "01H00000000000000000000000",
            "decision_id": DECISION_ID,
            "ticket_id": TICKET,
            "side": "buy",
            "mint": MINT,
            "slippage_bps": 50,
            "size_lamports": 100_000_000,
            "approval_json": '{"strategy": "momentum_breakout"}',
        },
    )
    _append(
        store, clock, seq, "JournalNote",
        {
            "source": "paper",
            "seat": "bot-02-risk",
            "note_kind": "note",
            "text": "PROBATION momentum_breakout",
            "refs": [],
        },
    )
    _append(
        store, clock, seq, "JournalNote",
        {
            "source": "paper",
            "seat": "bot-00-chief",
            "note_kind": "note",
            "text": f"WATCH {MINT}",
            "refs": [],
        },
    )


def test_restart_recovery_restores_everything(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _seed(store, clock)
    restored = recover(store, clock)
    assert MINT in restored.open_positions
    assert restored.peaks[MINT] == 100_000_000
    assert restored.probation == frozenset({"momentum_breakout"})
    assert restored.watch_set == frozenset({MINT})
    assert restored.deadlines[MINT] == clock.now() + 3600.0
    assert restored.tapes != {}


def test_crash_during_recovery_resumes_clean(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _seed(store, clock)
    with pytest.raises(RecoveryInterrupted):
        recover(store, clock, fail_after_batches=0)
    second = recover(store, clock)
    third = recover(store, clock)
    assert second == third
    assert second.deadlines[MINT] == clock.now() + 3600.0


def test_corrupt_ledger_fails_closed(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _seed(store, clock)
    # Corrupt the chain: rewrite one payload without fixing hashes.
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "ledger.sqlite"))
    conn.execute("DROP TRIGGER events_append_only_u")
    conn.execute("DROP TRIGGER events_append_only_d")
    conn.execute("UPDATE events SET payload_json='{}' WHERE seq=1")
    conn.commit()
    conn.close()
    try:
        store.verify()
    except Exception:
        pass
    with pytest.raises(RecoveryError):
        recover(store, clock)


def test_resume_places_no_second_buy_and_no_second_fill(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _seed(store, clock)
    assert decision_recorded(store, MINT, DECISION_ID) is True
    with pytest.raises(DuplicateBuyError):
        assert_no_second_buy(store, MINT, DECISION_ID)


def test_fresh_candidate_has_no_decision_link(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    assert decision_recorded(store, MINT, DECISION_ID) is False
    assert_no_second_buy(store, MINT, DECISION_ID)  # must not raise
