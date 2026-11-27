"""RT-04 (library half): restart restores tapes, peaks and probation."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.strategies.recovery import RecoveryStore
from pumpgrok.strategies.tape import Tape, Tick


def test_restart_restores_state_byte_identically(tmp_path: Path) -> None:
    tape = Tape.from_ticks(
        [
            Tick(ts=1.0, mint="MintA", price_lamports=1000, buyers=7, created_ts=0.0),
            Tick(ts=2.0, mint="MintA", price_lamports=1500, buyers=9, created_ts=0.0),
        ]
    )
    RecoveryStore(tmp_path / "recovery.json").save(
        "momentum_breakout",
        tape=tape,
        peaks={"MintA": 1500},
        probation={"MintA": True},
    )

    # Simulate a restart: a fresh store over the same file.
    restored = RecoveryStore(tmp_path / "recovery.json").load("momentum_breakout")
    assert restored.strategy_id == "momentum_breakout"
    assert restored.ticks == tape.ticks
    assert restored.peaks == {"MintA": 1500}
    assert restored.probation == {"MintA": True}


def test_unknown_strategy_restores_empty(tmp_path: Path) -> None:
    restored = RecoveryStore(tmp_path / "recovery.json").load("mean_reversion")
    assert restored.ticks == ()
    assert restored.peaks == {}
    assert restored.probation == {}
