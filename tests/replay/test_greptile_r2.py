"""Replay and serve stay sound under valid settings (Greptile round 2, findings 2-5).

Datasets are built from the smoke fixture in a temporary directory. The bundled
fixture is never edited here.
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
from pumpgrok.config.settings import ExitsSettings, FilterSettings
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.supervisor.health import is_ok
from pumpgrok.supervisor.scheduler import (
    build_serve_replay,
    dataset_stamps,
    run_once_replay,
    serve_fixture_timeline,
)

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
MINT_B = "SmokeMintBBBB2222222222222222222222222222222"
MINT_C = "SmokeMintCCCC3333333333333333333333333333333"
T_UNITS = 121_500_000_000_000


def _iso(offset: float) -> str:
    stamp = parse_ts_utc("2026-01-01T00:00:00.000Z") + offset
    whole = int(stamp)
    millis = round((stamp - whole) * 1000)
    return f"{datetime.fromtimestamp(whole, UTC):%Y-%m-%dT%H:%M:%S}.{millis:03d}Z"


def _tick(
    offset: float, mint: str, s: int, *, complete: bool = False, evidence: bool = False
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "ts_utc": _iso(offset),
        "kind": "tick",
        "mint": mint,
        "S": s,
        "T": T_UNITS,
        "complete": complete,
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
        "notes": "test dataset for Greptile round 2 findings",
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dataset


def _rows(ledger: Path) -> list[dict[str, Any]]:
    store = LedgerStore(str(ledger))
    try:
        return store.read(limit=None)
    finally:
        store.close()


# Finding 2: a valid zero daily-loss fraction halts the replay; the run still succeeds.
def test_zero_daily_loss_fraction_halts_and_the_run_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PUMPGROK_RISK__DAILY_LOSS_HALT_FRACTION", "0")
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 0
    ledger = tmp_path / "var" / "replay" / "smoke" / "ledger.sqlite"
    halts = [r for r in _rows(ledger) if r["type"] == "HaltSet"]
    assert [h["payload"]["reason"] for h in halts] == ["daily_loss"]
    assert main(["verify", "--fixture", "smoke"]) == 0


# Finding 3: a healthy seat that is not stale at the take-profit tick stays healthy.
def test_take_profit_tick_records_no_stale_heartbeat_and_healthz_stays_ok(tmp_path: Path) -> None:
    supervisor, _metrics, store = build_serve_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        clock=FixtureClock(start=dataset_stamps(load_dataset(SMOKE))[0]),
        ledger_path=tmp_path / "serve.sqlite",
    )
    stamps = dataset_stamps(load_dataset(SMOKE))
    try:
        asyncio.run(serve_fixture_timeline(supervisor, stamps, heartbeats=True))
        rows = store.read(limit=None)
        status = supervisor.health_status()
    finally:
        store.close()
    assert [r["payload"]["reason"] for r in rows if r["type"] == "PositionClosed"] == [
        "take_profit"
    ]
    stale = [
        r["payload"]["seat"]
        for r in rows
        if r["type"] == "Escalation" and r["payload"]["kind"] == "heartbeat_stale"
    ]
    assert "bot-04-sniper" not in stale
    assert is_ok(status)


# Finding 4: after the first BUY, a later valid candidate is not refused as data_stale.
def test_later_candidate_is_not_refused_data_stale_after_a_buy(tmp_path: Path) -> None:
    events = [
        *(e for e in _smoke_events() if e["ts_utc"] != _iso(30.0)),
        _tick(10.0, MINT_C, 9_900_000_000, evidence=True),
    ]
    ledger = tmp_path / "l.sqlite"
    dataset = _dataset(tmp_path, "later", events)
    result = run_once_replay(dataset, FilterSettings(), seed=SEED, ledger_path=ledger)
    rows = _rows(ledger)
    c_rejects = [
        r["payload"]["reason"]
        for r in rows
        if r["type"] == "OrderRejected" and MINT_C in r["payload"]["detail"]
    ]
    assert "data_stale" not in c_rejects
    c_buys = [t for t in result.trades if t.mint == MINT_C and t.side == "buy"]
    assert [t.outcome for t in c_buys] == ["filled"]
    # The open position was marked before the later order, so loss checks see its value.
    c_order_seq = min(
        r["seq"] for r in rows if r["type"] == "OrderPlaced" and MINT_C in str(r["payload"])
    )
    marks = [r for r in rows if r["type"] == "MarkToMarket" and r["seq"] < c_order_seq]
    assert marks, "a MarkToMarket must precede the later order"
    assert MINT_B in marks[-1]["payload"]["prices_json"]
    assert marks[-1]["payload"]["equity_lamports"] > 0


# Finding 5: a graduated position closes before ordinary exit rules run.
@pytest.mark.parametrize(
    ("case", "offset", "s_lamports", "exits"),
    [
        (
            "stop_loss",
            5.0,
            5_940_000_000,  # -40% from the 9.9e9 entry, on a completed curve
            ExitsSettings(
                stop_loss_pct=30, take_profit_pct=0, trailing_stop_pct=0, max_hold_seconds=0
            ),
        ),
        (
            "max_hold",
            20.0,
            9_900_000_000,  # unchanged price, held past the 10 s limit
            ExitsSettings(
                stop_loss_pct=0, take_profit_pct=0, trailing_stop_pct=0, max_hold_seconds=10
            ),
        ),
    ],
    ids=["stop_loss", "max_hold"],
)
def test_graduated_position_closes_under_an_ordinary_exit_rule(
    tmp_path: Path, case: str, offset: float, s_lamports: int, exits: ExitsSettings
) -> None:
    events = [
        *(e for e in _smoke_events() if e["ts_utc"] != _iso(30.0)),
        _tick(offset, MINT_B, s_lamports, complete=True),
    ]
    ledger = tmp_path / "l.sqlite"
    dataset = _dataset(tmp_path, f"grad-{case}", events)
    run_once_replay(dataset, FilterSettings(), seed=SEED, ledger_path=ledger, exits=exits)
    rows = _rows(ledger)
    closed = [r for r in rows if r["type"] == "PositionClosed" and r["payload"]["mint"] == MINT_B]
    sells = [
        r
        for r in rows
        if r["type"] == "FillRecorded"
        and r["payload"]["side"] == "sell"
        and r["payload"]["mint"] == MINT_B
    ]
    assert [c["payload"]["reason"] for c in closed] == ["graduated"]
    assert len(sells) == 1
