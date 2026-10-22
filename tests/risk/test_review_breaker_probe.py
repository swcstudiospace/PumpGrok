"""Review finding 9: a half-open breaker's probe must reach its owning order.

The admitted probe belongs to the order that took it. That order's repeat
checks (the CONFIRMING re-check, or a repeated ACCEPTED check) must not see
the probe as taken by someone else, and any other order must still be refused
until the owner's probe is resolved.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import RiskEngine, order_hash_for

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "So22222222222222222222222222222222222222222"
S0 = 42_000_000_000
T0 = 764_000_000_000_000
SIZE = 200_000_000
BUY_SEAT = "bot-04-sniper"
BREAKER = "data_stale"
DATA_STALE_COOLDOWN_S = 60.0


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, **kwargs: Any) -> RiskEngine:
    kwargs.setdefault("get_reserves", lambda _mint: (S0, T0))
    kwargs.setdefault("env", {})
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(41)),
        clock=clock,
        autonomy="autonomous-paper",
        **kwargs,
    )


def _buy(clock: FixtureClock, ids: IdFactory, mint: str = MINT_A) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=mint,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _open_half_open_data_stale(engine: RiskEngine, clock: FixtureClock) -> None:
    """Trip data_stale with three misses, then advance past its cooldown."""
    for _ in range(3):
        engine.note_miss(
            clock.now(),
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
        )
    assert engine.check(_buy(clock, IdFactory(clock, random.Random(1)))).passed is False
    clock.advance_to(clock.now() + DATA_STALE_COOLDOWN_S + 1.0)


def test_owner_confirming_recheck_is_not_blocked_by_its_own_probe(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        engine = _engine(store, clock)
        _open_half_open_data_stale(engine, clock)
        ids = IdFactory(clock, random.Random(5))
        order = _buy(clock, ids)

        accepted = engine.check(order, seat=BUY_SEAT, stage="ACCEPTED")
        assert accepted.passed is True
        assert accepted.probe is True

        recheck = engine.check(order, seat=BUY_SEAT, stage="CONFIRMING")
        assert recheck.passed is True, recheck.reason
        assert recheck.probe is True
    finally:
        store.close()


def test_owner_repeat_accepted_check_keeps_its_probe(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        engine = _engine(store, clock)
        _open_half_open_data_stale(engine, clock)
        ids = IdFactory(clock, random.Random(6))
        order = _buy(clock, ids)

        first = engine.check(order, seat=BUY_SEAT, stage="ACCEPTED")
        again = engine.check(order, seat=BUY_SEAT, stage="ACCEPTED")
        assert first.passed is True
        assert again.passed is True
        assert again.probe is True
    finally:
        store.close()


def test_other_order_is_refused_until_owner_probe_resolves(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        engine = _engine(store, clock)
        _open_half_open_data_stale(engine, clock)
        ids = IdFactory(clock, random.Random(7))
        owner = _buy(clock, ids, MINT_A)
        other = _buy(clock, ids, MINT_B)

        assert engine.check(owner, seat=BUY_SEAT, stage="ACCEPTED").passed is True

        blocked = engine.check(other, seat=BUY_SEAT, stage="ACCEPTED")
        assert blocked.passed is False
        assert blocked.reason == "breaker_open"

        # The owner's outcome resolves the probe; the breaker then closes.
        engine.resolve_probe(BREAKER, True, source="paper", correlation_id="test")
        admitted = engine.check(other, seat=BUY_SEAT, stage="ACCEPTED")
        assert admitted.passed is True, admitted.reason
    finally:
        store.close()


def test_release_order_probes_frees_breaker_for_other_orders(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        engine = _engine(store, clock)
        _open_half_open_data_stale(engine, clock)
        ids = IdFactory(clock, random.Random(8))
        owner = _buy(clock, ids, MINT_A)
        other = _buy(clock, ids, MINT_B)

        assert engine.check(owner, seat=BUY_SEAT, stage="ACCEPTED").probe is True
        assert engine.check(other, seat=BUY_SEAT, stage="ACCEPTED").reason == "breaker_open"

        engine.release_order_probes(
            order_hash_for(owner), True, source="paper", correlation_id="test"
        )
        admitted = engine.check(other, seat=BUY_SEAT, stage="ACCEPTED")
        assert admitted.passed is True, admitted.reason
    finally:
        store.close()


def test_release_order_probes_is_idempotent_and_ignores_non_owners(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        engine = _engine(store, clock)
        _open_half_open_data_stale(engine, clock)
        ids = IdFactory(clock, random.Random(9))
        owner = _buy(clock, ids, MINT_A)
        stranger = _buy(clock, ids, MINT_B)

        assert engine.check(owner, seat=BUY_SEAT, stage="ACCEPTED").passed is True
        # A non-owner hash releases nothing: the probe stays with the owner.
        engine.release_order_probes(
            order_hash_for(stranger), False, source="paper", correlation_id="test"
        )
        assert engine._breakers.by_name(BREAKER).probe_inflight is True

        release = order_hash_for(owner)
        engine.release_order_probes(release, True, source="paper", correlation_id="test")
        # Second release finds no inflight probe and must not raise.
        engine.release_order_probes(release, True, source="paper", correlation_id="test")
        assert engine._breakers.by_name(BREAKER).probe_inflight is False
    finally:
        store.close()
