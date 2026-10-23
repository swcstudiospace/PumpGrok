"""Replay and serve follow one recorded timeline (Greptile round 1, findings 4-8, 12).

Each test names the finding it pins. Datasets are built from the smoke fixture plus
extra ticks in a temporary directory, so the bundled fixture is never edited here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import FilterSettings
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.supervisor.scheduler import (
    build_serve_replay,
    run_once_replay,
    serve_fixture_timeline,
)

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
MINT_B = "SmokeMintBBBB2222222222222222222222222222222"
MINT_C = "SmokeMintCCCC3333333333333333333333333333333"
T_UNITS = 121_500_000_000_000
FULL_B = 9_900_000_000  # mint B reserves at its 3.0 s entry tick


def _iso(offset: float) -> str:
    """ISO stamp ``offset`` seconds after the smoke start (2026-01-01T00:00:00Z)."""
    stamp = parse_ts_utc("2026-01-01T00:00:00.000Z") + offset
    whole = int(stamp)
    millis = round((stamp - whole) * 1000)
    return f"{datetime.fromtimestamp(whole, UTC):%Y-%m-%dT%H:%M:%S}.{millis:03d}Z"


def _tick(offset: float, mint: str, s: int, *, evidence: bool = False) -> dict[str, Any]:
    event: dict[str, Any] = {
        "ts_utc": _iso(offset),
        "kind": "tick",
        "mint": mint,
        "S": s,
        "T": T_UNITS,
        "complete": False,
        "source": "rest",
    }
    if evidence:
        event.update(
            name=f"Token {mint[:6]}",
            image_uri=f"fixture://{mint[:6]}.png",
            created_ts_utc="2025-12-31T23:40:00.000Z",
            unique_buyers=10,
        )
    return event


def _smoke_events() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (SMOKE / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _dataset(root: Path, name: str, events: list[dict[str, Any]]) -> Path:
    dataset = root / name
    dataset.mkdir(parents=True)
    data = "".join(json.dumps(event) + "\n" for event in events)
    (dataset / "events.jsonl").write_text(data, encoding="utf-8")
    manifest = {
        "dataset": name,
        "recorded_from_utc": events[0]["ts_utc"],
        "recorded_to_utc": events[-1]["ts_utc"],
        "seed_hint": SEED,
        "sources": {"rest": "hand-authored", "pumpportal": "hand-authored"},
        "sha256": {"events.jsonl": hashlib.sha256(data.encode("utf-8")).hexdigest()},
        "notes": "test dataset for Greptile round 1 timeline findings",
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dataset


def _rows(ledger: Path) -> list[dict[str, Any]]:
    store = LedgerStore(str(ledger))
    try:
        return store.read(limit=None)
    finally:
        store.close()


def test_default_serve_clock_prices_each_candidate_from_its_own_tick(tmp_path: Path) -> None:
    """Finding 4: an ordinary serve (no injected clock) follows the recorded timeline."""
    supervisor, _metrics, store = build_serve_replay(
        SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "serve.sqlite"
    )
    stamps = sorted({parse_ts_utc(str(e["ts_utc"])) for e in load_dataset(SMOKE).events})
    try:
        assert isinstance(supervisor.clock, FixtureClock)
        asyncio.run(serve_fixture_timeline(supervisor, stamps))
        rows = store.read(limit=None)
    finally:
        store.close()
    reasons = [r["payload"]["reason"] for r in rows if r["type"] == "OrderRejected"]
    # The 2.5 s candidate is complete at its own tick, so it is refused there, not at 30 s.
    assert "post_graduation_no_reserves" in reasons
    buys = [r for r in rows if r["type"] == "FillRecorded" and r["payload"]["side"] == "buy"]
    assert [b["payload"]["curve_before_s"] for b in buys] == [FULL_B]


def test_tick_inside_a_sell_latency_window_does_not_move_time_backwards(tmp_path: Path) -> None:
    """Finding 5: an unchanged tick at 30.100 after a 30.000 take-profit must not crash replay."""
    events = [*_smoke_events(), _tick(30.1, MINT_B, 24_750_000_000)]
    dataset = _dataset(tmp_path, "closeticks", events)
    result = run_once_replay(
        dataset, FilterSettings(), seed=SEED, ledger_path=tmp_path / "l.sqlite"
    )
    sells = [(t.outcome, t.rule) for t in result.trades if t.side == "sell"]
    assert sells == [("filled", "take_profit")]


def test_early_stop_loss_fires_before_a_later_buy(tmp_path: Path) -> None:
    """Finding 6: a stop-loss tick before a later candidate still closes the early position."""
    events = [
        *(e for e in _smoke_events() if e["ts_utc"] != _iso(30.0)),
        _tick(5.0, MINT_B, 5_940_000_000),  # -40% from the 9.9e9 entry: stop-loss
        _tick(10.0, MINT_C, 9_900_000_000, evidence=True),  # a later, unrelated candidate
    ]
    dataset = _dataset(tmp_path, "stopfirst", events)
    ledger = tmp_path / "l.sqlite"
    run_once_replay(dataset, FilterSettings(), seed=SEED, ledger_path=ledger)
    rows = _rows(ledger)
    stops = [r for r in rows if r["type"] == "PositionClosed" and r["payload"]["mint"] == MINT_B]
    buys_c = [r for r in rows if r["type"] == "OrderPlaced" and r["payload"]["mint"] == MINT_C]
    assert [s["payload"]["reason"] for s in stops] == ["stop_loss"]
    assert buys_c, "the later candidate should still be attempted"
    assert stops[0]["seq"] < buys_c[0]["seq"]


def test_operator_risk_setting_blocks_the_smoke_buy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 7: risk.max_open_positions = 0 from the operator's settings blocks the buy."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PUMPGROK_RISK__MAX_OPEN_POSITIONS", "0")
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 0
    rows = _rows(tmp_path / "var" / "replay" / "smoke" / "ledger.sqlite")
    buys = [r for r in rows if r["type"] == "FillRecorded" and r["payload"]["side"] == "buy"]
    assert buys == []


def test_reentry_after_exit_does_not_inherit_the_old_peak(tmp_path: Path) -> None:
    """Finding 8: a re-entry at 40 s is priced and exited from its own entry, not the old peak."""
    events = [*_smoke_events(), _tick(40.0, MINT_B, 12_000_000_000, evidence=True)]
    dataset = _dataset(tmp_path, "reentry", events)
    ledger = tmp_path / "l.sqlite"
    run_once_replay(dataset, FilterSettings(), seed=SEED, ledger_path=ledger)
    rows = _rows(ledger)
    closes = [r["payload"]["reason"] for r in rows if r["type"] == "PositionClosed"]
    assert "trailing_stop" not in closes
    buys = [r for r in rows if r["type"] == "FillRecorded" and r["payload"]["side"] == "buy"]
    assert len(buys) == 2, "the re-entry at 40 s should fill"


def test_verify_reports_the_final_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Finding 12: verify prints the final sequence of the completed chain."""
    monkeypatch.chdir(tmp_path)
    assert main(["verify", "--fixture", "smoke"]) == 0
    out = capsys.readouterr().out
    seq = int(out.split("seq=")[1].split()[0])
    rows = _rows(tmp_path / "var" / "replay" / "smoke" / "ledger.sqlite")
    assert seq == len(rows) == rows[-1]["seq"]
