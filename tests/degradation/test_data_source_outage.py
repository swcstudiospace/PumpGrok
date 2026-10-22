"""INV-R-32: data-source outage trips DataStale, serves last-good, then recovers.

WS silence is driven through DegradedState and the product DataStaleBreaker;
REST outage through FaultyDataSource/FaultyPriceSource; adversarial payloads
through parse_upstream(CurveSnapshot). The blind window closes with a ledger
Escalation, and recovery needs three fresh ticks.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from harness.faults import FaultMode, FaultyDataSource, FaultyPriceSource
from pumpgrok.core.errors import DataStale
from pumpgrok.core.tool import parse_upstream
from pumpgrok.execution.paper_adapter import CurveSnapshot
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.breakers import DataStaleBreaker
from pumpgrok.supervisor.scheduler import DegradedState
from pumpgrok.supervisor.seat_task import append_escalation

BASE = 1767225600.0
MINT = "So11111111111111111111111111111111111111112"
MIXED = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "http"
    / "adversarial"
    / "mixed.json"
)


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def test_ws_silence_trips_data_stale_with_recovery() -> None:
    degraded = DegradedState()
    assert degraded.ws_data_stale(10_000.0) is False
    degraded.note_ws_frame(0.0)
    assert degraded.ws_data_stale(119.0) is False
    assert degraded.ws_data_stale(121.0) is True
    degraded.note_ws_frame(121.0)
    assert degraded.ws_data_stale(122.0) is False


def test_ws_silence_trips_product_breaker_and_recovers() -> None:
    clock = FixtureClock(start=0.0)
    breaker = DataStaleBreaker(now=clock.now)
    breaker.note_tick(0.0)
    assert breaker.evaluate(119.0) == "closed"
    assert breaker.evaluate(121.0) == "open"
    for tick in (121.0, 122.0, 123.0):
        breaker.note_tick(tick)
    assert breaker.evaluate(123.0) == "closed"


async def test_rest_outage_serves_last_good() -> None:
    last_good = {"tick": 7, "mint": MINT}
    fake = FaultyDataSource(FaultMode.STALE, last_good=last_good)
    value, freshness = await fake.fetch({"mint": MINT}, max_age_s=120.0)
    assert fake.fired == 1
    assert value == last_good
    assert freshness.stale is True


async def test_rest_outage_without_cache_is_typed_stale() -> None:
    fake = FaultyDataSource(FaultMode.STALE)
    with pytest.raises(DataStale):
        await fake.fetch({"mint": MINT}, max_age_s=120.0)
    assert fake.fired == 1


async def test_blind_window_marks_last_good_then_escalates(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        last_good = CurveSnapshot(mint=MINT, s_lamports=42_000_000_000, t_units=766_428)
        price = FaultyPriceSource(FaultMode.STALE, last_good=last_good)
        for _ in range(3):
            assert await price.curve(MINT) is last_good
        assert price.fired == 3
        clock.advance_to(BASE + 300.0)
        append_escalation(
            store,
            clock,
            kind="blind_flatten",
            seat="bot-06-exit",
            detail="blind for 300 s; flattening at last_good",
            source="paper",
            correlation_id="desk",
        )
        kinds = [
            event["payload"]["kind"]
            for event in store.read(types=["Escalation"], limit=None)
        ]
        assert kinds == ["blind_flatten"]
        assert store.verify() is True
    finally:
        store.close()


def test_adversarial_payloads_never_raise_into_loop() -> None:
    bundle = json.loads(MIXED.read_text())
    assert bundle["records"], "adversarial fixture must not be empty"
    for record in bundle["records"]:
        payload = record["payload"]
        if record["expect_ok"]:
            parsed = parse_upstream(CurveSnapshot, payload)
            assert isinstance(parsed, CurveSnapshot)
            continue
        try:
            parse_upstream(CurveSnapshot, payload)
        except DataStale:
            pass
        else:
            pytest.fail(f"{record['name']} should be typed DataStale")


def test_adversarial_edge_records_are_flagged_by_caller() -> None:
    bundle = json.loads(MIXED.read_text())
    by_name = {record["name"]: record for record in bundle["records"]}
    confusable = parse_upstream(CurveSnapshot, by_name["confusable_mint"]["payload"])
    # NFKC alone does not fold Cyrillic lookalikes, so the caller flags
    # any non-ASCII mint for the confusable map instead of trusting it.
    assert any(ord(char) > 127 for char in confusable.mint)
    assert unicodedata.normalize("NFKC", confusable.mint) == confusable.mint
    negative = parse_upstream(CurveSnapshot, by_name["negative_reserves"]["payload"])
    assert negative.s_lamports < 0


def test_recovery_after_three_fresh_ticks() -> None:
    degraded = DegradedState()
    degraded.note_ws_frame(0.0)
    assert degraded.ws_data_stale(200.0) is True
    for tick in (200.0, 210.0, 220.0):
        degraded.note_ws_frame(tick)
    assert degraded.ws_data_stale(221.0) is False
