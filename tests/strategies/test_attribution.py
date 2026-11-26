<<<<<<< HEAD
"""STR-03: per-strategy P&L folds exactly to the desk total."""

from __future__ import annotations

import pytest

from pumpgrok.strategies.attribution import fold_attribution


def test_fold_equals_desk_total() -> None:
    fold = fold_attribution(
        {"momentum_breakout": 1000, "legacy_screening": -400, "mean_reversion": 250},
        850,
    )
    assert fold.folded_lamports == 850
    assert fold.desk_total_lamports == 850
    assert fold.per_strategy["momentum_breakout"] == 1000


def test_mismatch_raises_instead_of_drifting() -> None:
    with pytest.raises(ValueError):
        fold_attribution({"momentum_breakout": 1000}, 999)


def test_non_int_pnl_refused() -> None:
    with pytest.raises(ValueError):
        fold_attribution({"momentum_breakout": True}, 1)  # type: ignore[dict-item]
=======
"""STR-03: per-strategy P&L folds to the desk total exactly, in integer lamports.

The fold walks the ledger rows through the reducer. Each row's equity change is attributed to
one bucket: the strategy its ticket is attributed to, or the desk when none is. The buckets
therefore sum to the desk total with no remainder. The tape tests cover the bounded price
history that recovery restores (15-04).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.ledger.reducer import initial_state
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.strategies import legacy
from pumpgrok.strategies.attribution import attribute, desk_genesis, desk_net_lamports
from pumpgrok.strategies.base import TapePoint
from pumpgrok.strategies.tape import Tape, TapeError

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101


def _rows_of(path: Path) -> tuple[LedgerStore, list[dict]]:
    store = LedgerStore(str(path))
    return store, store.read(limit=None)


def test_empty_fold_is_zero_for_every_bucket() -> None:
    genesis = initial_state(source="replay", initial_equity_lamports=1_000, day_utc="")
    result = attribute(genesis, [], {}, strategy_ids=("momentum_breakout", "mean_reversion"))
    assert result.desk_total_lamports == 0
    assert result.per_strategy == {
        "momentum_breakout": 0,
        "mean_reversion": 0,
        "desk": 0,
    }


def test_unattributed_legacy_run_folds_entirely_to_the_desk(tmp_path: Path) -> None:
    run = legacy.run_legacy_replay(
        SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "l.sqlite"
    )
    store, rows = _rows_of(run.ledger_path)
    try:
        genesis = desk_genesis(store)
        result = attribute(genesis, rows, {})
        assert result.desk_total_lamports == desk_net_lamports(store)
        assert result.per_strategy == {"desk": result.desk_total_lamports}
    finally:
        store.close()


def test_attributed_buckets_sum_to_the_desk_total_exactly(tmp_path: Path) -> None:
    run = legacy.run_legacy_replay(
        SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "a.sqlite"
    )
    store, rows = _rows_of(run.ledger_path)
    try:
        genesis = desk_genesis(store)
        tickets = {
            str(row["payload"].get("ticket_id", ""))
            for row in rows
            if row["type"] == "PositionOpened"
        }
        tickets.discard("")
        assert tickets, "the smoke run must open a position under a ticket"
        refs = dict.fromkeys(tickets, "momentum_breakout")
        result = attribute(genesis, rows, refs, strategy_ids=("momentum_breakout",))
        assert result.per_strategy["momentum_breakout"] != 0
        assert sum(result.per_strategy.values()) == result.desk_total_lamports
        assert result.desk_total_lamports == desk_net_lamports(store)
        assert all(type(value) is int for value in result.per_strategy.values())
    finally:
        store.close()


def test_tape_is_bounded_and_keeps_the_newest_points() -> None:
    tape = Tape(capacity=3)
    for step in range(5):
        tape.record("MintA", TapePoint(ts=float(step), price_lamports=step * 10))
    assert [p.price_lamports for p in tape.points("MintA")] == [20, 30, 40]
    assert tape.points("MintB") == ()


def test_tape_refuses_time_going_backwards_and_non_int_prices() -> None:
    tape = Tape()
    tape.record("MintA", TapePoint(ts=5.0, price_lamports=1))
    with pytest.raises(TapeError):
        tape.record("MintA", TapePoint(ts=4.0, price_lamports=2))
    with pytest.raises(TapeError):
        tape.record("MintA", TapePoint(ts=6.0, price_lamports=1.5))  # type: ignore[arg-type]


def test_tape_serialises_for_recovery_and_round_trips() -> None:
    tape = Tape(capacity=4)
    tape.record("MintA", TapePoint(ts=1.25, price_lamports=7))
    tape.record("MintA", TapePoint(ts=2.5, price_lamports=9))
    tape.record("MintB", TapePoint(ts=2.5, price_lamports=3))
    text = tape.to_json()
    restored = Tape.from_json(text)
    assert restored.to_json() == text
    assert restored.points("MintA") == tape.points("MintA")
    assert restored.capacity == 4
    assert "NaN" not in text and "Infinity" not in text
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
