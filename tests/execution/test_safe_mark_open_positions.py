"""Contract tests for scheduler-supplied paper marks and timeout-zero marks.

These exercise real ledger rows, the reducer and the adapter's fee accounting.
A supplied mapping is authoritative for that call: omitted held mints are gaps,
not a request for another price read.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.curve_math import sell_out
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.tools.onchain import curve_layout

START = 1_769_900_000.0
EQUITY = 10_000_000_000
MINT = "So11111111111111111111111111111111111111112"
OTHER = "So22222222222222222222222222222222222222222"
ZERO = "So33333333333333333333333333333333333333333"
UNKNOWN = "So44444444444444444444444444444444444444444"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
UNITS = 3_000_000
BASIS = 200_000_000
OTHER_UNITS = 1_000_000
OTHER_BASIS = 50_000_000
OTHER_MTM = 61_000_000
ZERO_UNITS = 2_000_000
ZERO_BASIS = 80_000_000


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _seed_position(
    store: LedgerStore, clock: FixtureClock, mint: str, units: int, basis: int
) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"pos-{mint}",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": mint,
            "price_entry": "0.00001",
            "token_units": units,
            "cost_basis_lamports": basis,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": "SOL-20260201-001",
            "score": "0.8",
        },
    )


def _mark(store: LedgerStore, clock: FixtureClock, mint: str, mtm: int, key: str) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=key,
        type="MarkToMarket",
        payload={
            "source": "paper",
            "ts_source": format_ts_utc(clock.now()),
            "cash_lamports": EQUITY,
            "equity_lamports": EQUITY + mtm,
            "unrealized_lamports": mtm,
            "prices_json": json.dumps(
                {mint: {"mtm_lamports": mtm, "spot": "1", "source": "curve"}}
            ),
        },
    )


def _adapter(
    store: LedgerStore, clock: FixtureClock, *, price_source: CountingSource
) -> PaperAdapter:
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(52)),
        clock=clock,
        autonomy="autonomous-paper",
        get_reserves=lambda _mint: (S0, T0),
        env={},
    )
    return PaperAdapter(
        store=store,
        risk=engine,
        ids=IdFactory(clock, make_rng(52)),
        clock=clock,
        rng=make_rng(52),
        budget=RiskBudget(),
        price_source=price_source,
        p_drop=0.0,
    )


class CountingSource:
    def __init__(self, snapshot: CurveSnapshot | None = None) -> None:
        self.snapshot = snapshot
        self.reads: list[str] = []

    async def curve(self, mint: str) -> CurveSnapshot | None:
        self.reads.append(mint)
        return self.snapshot


def _snapshot(mint: str = MINT, *, source: str = "fixture") -> CurveSnapshot:
    return CurveSnapshot(mint=mint, s_lamports=S0, t_units=T0, source=source, ts=START)


def _fold(store):
    state = initial_state(initial_equity_lamports=EQUITY, source="paper", day_utc="2026-02-01")
    for row in store.read(limit=None):
        state = reduce(state, row)
    return state


async def test_supplied_mixed_marks_preserve_gap_and_zero_without_selling(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        _seed_position(store, clock, OTHER, OTHER_UNITS, OTHER_BASIS)
        _seed_position(store, clock, ZERO, ZERO_UNITS, ZERO_BASIS)
        _mark(store, clock, OTHER, OTHER_MTM, "prior-gap")
        _mark(store, clock, ZERO, 25_000_000, "prior-zero")
        clock.advance_to(START + 5)
        source = CountingSource(_snapshot())
        adapter = _adapter(store, clock, price_source=source)
        before = store.read(limit=None)

        row = await adapter.mark_open_positions(
            snapshots={MINT: _snapshot()}, zero_mints={ZERO}, correlation_id="safe-marks"
        )

        assert row is not None
        assert source.reads == []
        new_rows = store.read(limit=None)[len(before) :]
        assert [event["type"] for event in new_rows] == ["MarkToMarket"]
        body = json.loads(str(row["payload_json"]))
        prices = json.loads(body["prices_json"])
        gross = sell_out(S0, T0, UNITS)
        venue = FeeModel().venue_fee(gross)
        trusted_value = gross - venue
        assert prices[MINT]["mtm_lamports"] == trusted_value
        assert prices[MINT]["venue_fee_lamports"] == venue
        assert prices[MINT]["ts_utc"] == format_ts_utc(START)
        assert OTHER not in prices
        assert prices[ZERO]["mtm_lamports"] == 0
        assert body["cash_lamports"] == EQUITY
        assert body["equity_lamports"] == EQUITY + trusted_value + OTHER_MTM
        assert body["unrealized_lamports"] == (
            trusted_value + OTHER_MTM - BASIS - OTHER_BASIS - ZERO_BASIS
        )

        state = _fold(store)
        assert state.positions[MINT].last_mtm_lamports == trusted_value
        assert state.positions[OTHER].last_mtm_lamports == OTHER_MTM
        assert state.positions[ZERO].last_mtm_lamports == 0
        assert state.positions[ZERO].last_mtm_ts_utc
        assert state.positions[ZERO].token_units == ZERO_UNITS
        assert state.positions[ZERO].cost_basis_lamports == ZERO_BASIS
        assert not state.positions[ZERO].mtm_frozen
        assert state.cash_lamports == EQUITY
        assert adapter.equity_lamports() == body["equity_lamports"]
    finally:
        store.close()


async def test_zero_only_writes_mark_and_keeps_position_open(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, ZERO, ZERO_UNITS, ZERO_BASIS)
        _mark(store, clock, ZERO, 25_000_000, "prior")
        clock.advance_to(START + 5)
        source = CountingSource()
        adapter = _adapter(store, clock, price_source=source)
        adapter._last_reserves[ZERO] = (11, 22)
        adapter._last_price_ts[ZERO] = START - 20
        before = store.read(limit=None)

        row = await adapter.mark_open_positions(snapshots={}, zero_mints={ZERO})

        assert row is not None
        assert source.reads == []
        assert adapter._last_reserves[ZERO] == (11, 22)
        assert adapter._last_price_ts[ZERO] == START - 20
        assert [e["type"] for e in store.read(limit=None)[len(before) :]] == ["MarkToMarket"]
        state = _fold(store)
        assert state.positions[ZERO].last_mtm_lamports == 0
        assert state.positions[ZERO].token_units == ZERO_UNITS
        assert state.positions[ZERO].cost_basis_lamports == ZERO_BASIS
        assert state.cash_lamports == EQUITY
        assert adapter.equity_lamports() == EQUITY
    finally:
        store.close()


@pytest.mark.parametrize(
    "invalid", ["unknown", "unverified", "mismatch", "source", "reserves", "complete", "overlap"]
)
async def test_invalid_supplied_snapshot_rejects_atomically(
    tmp_path: Path, invalid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        _seed_position(store, clock, OTHER, OTHER_UNITS, OTHER_BASIS)
        source = CountingSource()
        adapter = _adapter(store, clock, price_source=source)
        monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
        adapter._last_reserves[MINT] = (11, 22)
        adapter._last_price_ts[MINT] = START - 20
        snapshots = {MINT: _snapshot()}
        if invalid == "unknown":
            snapshots[UNKNOWN] = _snapshot(UNKNOWN)
        elif invalid == "unverified":
            snapshots[OTHER] = _snapshot(OTHER, source="rpc")
        elif invalid == "mismatch":
            snapshots[OTHER] = _snapshot(MINT)
        elif invalid == "source":
            snapshots[OTHER] = _snapshot(OTHER, source="unknown")
        elif invalid == "reserves":
            snapshots[OTHER] = _snapshot(OTHER).model_copy(update={"s_lamports": 0})
        elif invalid == "complete":
            snapshots[OTHER] = _snapshot(OTHER).model_copy(update={"complete": True})
        before_rows = store.read(limit=None)
        before_reserves = adapter._last_reserves.copy()
        before_times = adapter._last_price_ts.copy()

        with pytest.raises(ValueError):
            await adapter.mark_open_positions(
                snapshots=snapshots, zero_mints={MINT} if invalid == "overlap" else set()
            )

        assert store.read(limit=None) == before_rows
        assert adapter._last_reserves == before_reserves
        assert adapter._last_price_ts == before_times
        assert source.reads == []
    finally:
        store.close()


async def test_unknown_zero_mint_rejects_without_writes_or_cache_changes(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        source = CountingSource()
        adapter = _adapter(store, clock, price_source=source)
        adapter._last_reserves[MINT] = (11, 22)
        adapter._last_price_ts[MINT] = START - 20
        rows = store.read(limit=None)
        reserves = adapter._last_reserves.copy()
        times = adapter._last_price_ts.copy()
        with pytest.raises(ValueError):
            await adapter.mark_open_positions(snapshots={MINT: _snapshot()}, zero_mints={UNKNOWN})
        assert store.read(limit=None) == rows
        assert adapter._last_reserves == reserves
        assert adapter._last_price_ts == times
        assert source.reads == []
    finally:
        store.close()


async def test_trust_demotion_rejects_previously_accepted_rpc_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        source = CountingSource()
        adapter = _adapter(store, clock, price_source=source)
        snap = _snapshot(source="rpc")
        monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
        assert (
            await adapter.mark_open_positions(snapshots={MINT: snap}, zero_mints=set()) is not None
        )
        before_rows = store.read(limit=None)
        before_reserves = adapter._last_reserves.copy()
        before_times = adapter._last_price_ts.copy()
        clock.advance_to(START + 5)
        monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")

        with pytest.raises(ValueError):
            await adapter.mark_open_positions(snapshots={MINT: snap}, zero_mints=set())

        assert store.read(limit=None) == before_rows
        assert adapter._last_reserves == before_reserves
        assert adapter._last_price_ts == before_times
        assert source.reads == []
    finally:
        store.close()


async def test_default_mark_call_still_reads_existing_price_source(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        source = CountingSource(_snapshot())
        adapter = _adapter(store, clock, price_source=source)
        row = await adapter.mark_open_positions(correlation_id="legacy")
        assert row is not None
        assert source.reads == [MINT]
        gross = sell_out(S0, T0, UNITS)
        assert _fold(store).positions[MINT].last_mtm_lamports == gross - FeeModel().venue_fee(gross)
    finally:
        store.close()


@pytest.mark.parametrize("source_name", ["rpc", "unknown"])
async def test_default_untrusted_snapshot_is_a_gap_without_cache_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_name: str
) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
        source = CountingSource(_snapshot(source=source_name))
        adapter = _adapter(store, clock, price_source=source)
        adapter._last_reserves[MINT] = (11, 22)
        adapter._last_price_ts[MINT] = START - 20
        before = store.read(limit=None)

        assert await adapter.mark_open_positions() is None
        assert source.reads == [MINT]
        assert store.read(limit=None) == before
        assert adapter._last_reserves[MINT] == (11, 22)
        assert adapter._last_price_ts[MINT] == START - 20
    finally:
        store.close()


async def test_default_rpc_demotion_preserves_last_trusted_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        source = CountingSource(_snapshot(source="rpc"))
        adapter = _adapter(store, clock, price_source=source)
        monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
        assert await adapter.mark_open_positions() is not None
        before = store.read(limit=None)
        reserves = adapter._last_reserves.copy()
        timestamps = adapter._last_price_ts.copy()
        clock.advance_to(START + 5)
        source.snapshot = _snapshot(source="rpc").model_copy(
            update={"s_lamports": S0 * 2, "ts": START + 5}
        )
        monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")

        assert await adapter.mark_open_positions() is None
        assert store.read(limit=None) == before
        assert adapter._last_reserves == reserves
        assert adapter._last_price_ts == timestamps
    finally:
        store.close()


@pytest.mark.parametrize("timestamp", [START + 11, START - 1, float("nan"), float("inf")])
async def test_supplied_future_or_regressing_timestamps_reject_atomically(
    tmp_path: Path, timestamp: float
) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        adapter = _adapter(store, clock, price_source=CountingSource())
        assert await adapter.mark_open_positions(snapshots={MINT: _snapshot()}) is not None
        clock.advance_to(START + 10)
        before = store.read(limit=None)
        reserves = adapter._last_reserves.copy()
        timestamps = adapter._last_price_ts.copy()
        invalid = _snapshot().model_copy(update={"s_lamports": S0 * 2, "ts": timestamp})

        with pytest.raises(ValueError):
            await adapter.mark_open_positions(snapshots={MINT: invalid})

        assert store.read(limit=None) == before
        assert adapter._last_reserves == reserves
        assert adapter._last_price_ts == timestamps
    finally:
        store.close()


async def test_default_gap_uses_unmarked_position_basis_in_row_equity(tmp_path: Path) -> None:
    class PerMintSource(CountingSource):
        async def curve(self, mint: str) -> CurveSnapshot | None:
            self.reads.append(mint)
            return _snapshot() if mint == MINT else None

    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        _seed_position(store, clock, OTHER, OTHER_UNITS, OTHER_BASIS)
        adapter = _adapter(store, clock, price_source=PerMintSource())
        row = await adapter.mark_open_positions()
        assert row is not None
        body = json.loads(str(row["payload_json"]))
        gross = sell_out(S0, T0, UNITS)
        net = gross - FeeModel().venue_fee(gross)
        assert body["equity_lamports"] == EQUITY + net + OTHER_BASIS
        assert body["unrealized_lamports"] == net - BASIS
        assert adapter.equity_lamports() == body["equity_lamports"]
    finally:
        store.close()


async def test_out_of_order_snapshot_rejected_after_adapter_restart(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        marker = _adapter(store, clock, price_source=CountingSource())
        assert await marker.mark_open_positions(snapshots={MINT: _snapshot()}) is not None
    finally:
        store.close()

    clock.advance_to(START + 10)
    reopened = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        adapter = _adapter(reopened, clock, price_source=CountingSource())
        before = reopened.read(limit=None)
        old = _snapshot().model_copy(update={"s_lamports": S0 * 2, "ts": START - 1})
        with pytest.raises(ValueError):
            await adapter.mark_open_positions(snapshots={MINT: old})
        assert reopened.read(limit=None) == before
        assert adapter._last_reserves == {}
        assert adapter._last_price_ts == {}
    finally:
        reopened.close()
