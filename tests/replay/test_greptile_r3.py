"""Marks describe one instant and carry the age of their prices (Greptile round 3).

Finding 2: all held mints are marked in one MarkToMarket row per instant, so the peak
never sees a mix of new and old prices. Finding 3: each mint's mark keeps the recorded
time of the tick it was priced from, and freshness is checked for every held mint.
Datasets are built from the smoke fixture in a temporary directory.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.supervisor.scheduler import run_once_replay

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
MINT_B = "SmokeMintBBBB2222222222222222222222222222222"
MINT_C = "SmokeMintCCCC3333333333333333333333333333333"
MINT_D = "SmokeMintDDDD4444444444444444444444444444444"
T_UNITS = 121_500_000_000_000


def _iso(offset: float) -> str:
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
        "notes": "test dataset for Greptile round 3 mark findings",
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dataset


def _rows(ledger: Path) -> list[dict[str, Any]]:
    store = LedgerStore(str(ledger))
    try:
        return store.read(limit=None)
    finally:
        store.close()


def _buys(result: Any, mint: str) -> list[str]:
    return [t.outcome for t in result.trades if t.mint == mint and t.side == "buy"]


def test_two_mints_moving_opposite_are_marked_once_per_instant(tmp_path: Path) -> None:
    """Finding 2: one combined MarkToMarket at 10 s, no false peak, no drawdown halt."""
    events = [
        *(e for e in _smoke_events() if e["ts_utc"] != _iso(30.0)),
        _tick(5.0, MINT_C, 9_900_000_000, evidence=True),  # second open position
        _tick(7.0, MINT_C, 9_900_000_000),  # its prior mark, before the instant that moves it
        _tick(10.0, MINT_B, 12_000_000_000),  # rises ~21%
        _tick(10.0, MINT_C, 8_000_000_000),  # falls ~19% at the same instant
        _tick(12.0, MINT_D, 9_900_000_000, evidence=True),  # later valid buy
    ]
    dataset = _dataset(tmp_path, "opposite", events)
    ledger = tmp_path / "l.sqlite"
    # A tight drawdown limit: a false peak from a mixed mark would halt the buy.
    budget = RiskBudget(drawdown_halt_fraction=Decimal("0.0001"))
    result = run_once_replay(
        dataset, FilterSettings(), seed=SEED, ledger_path=ledger, budget=budget
    )
    rows = _rows(ledger)
    at_ten_prefix = "2026-01-01T00:00:10"
    at_ten = [
        r for r in rows if r["type"] == "MarkToMarket" and r["ts_utc"].startswith(at_ten_prefix)
    ]
    combined = [
        r for r in at_ten if {MINT_B, MINT_C} <= set(json.loads(r["payload"]["prices_json"]))
    ]
    assert len(combined) == 1, "one MarkToMarket must carry both held mints at 10 s"
    assert not [r for r in rows if r["type"] == "HaltSet"], "no false drawdown halt"
    assert _buys(result, MINT_D) == ["filled"]


@pytest.mark.parametrize(
    ("fresh_b", "expected"),
    [(False, "data_stale"), (True, "filled")],
    ids=["silent_mint_is_stale", "fresh_tick_is_not_stale"],
)
def test_a_silent_held_mint_makes_the_balance_stale(
    tmp_path: Path, fresh_b: bool, expected: str
) -> None:
    """Finding 3: a held mint whose last tick is past the staleness limit refuses buys."""
    events = [*(e for e in _smoke_events() if e["ts_utc"] != _iso(30.0))]
    if fresh_b:
        events.append(_tick(99.0, MINT_B, 9_900_000_000))  # B still ticking, 1 s old
    events.append(_tick(100.0, MINT_D, 9_900_000_000))  # the replay keeps moving
    events.append(_tick(100.0, MINT_C, 9_900_000_000, evidence=True))  # later buy
    dataset = _dataset(tmp_path, f"silent-{fresh_b}", events)
    ledger = tmp_path / "l.sqlite"
    result = run_once_replay(dataset, FilterSettings(), seed=SEED, ledger_path=ledger)
    rows = _rows(ledger)
    if expected == "filled":
        assert _buys(result, MINT_C) == ["filled"]
    else:
        reasons = [
            r["payload"]["reason"]
            for r in rows
            if r["type"] == "OrderRejected" and MINT_C in str(r["payload"]["detail"])
        ]
        assert reasons == ["data_stale"]
        assert _buys(result, MINT_C) == ["rejected"]
