"""INV-R-07..08: size-cap matrix with R34 rule ids; sells stay open for exits."""

from __future__ import annotations

from decimal import Decimal
import json
import random
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import parse_human_phrase, record_human_approval
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import STEP_IDS, RiskEngine
from pumpgrok.tools.risk.check_limits import R34_RULE_IDS

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "So22222222222222222222222222222222222222222"
MINT_C = "So33333333333333333333333333333333333333333"
MINT_D = "So44444444444444444444444444444444444444444"
MINT_E = "So55555555555555555555555555555555555555555"
CREATOR_1 = "Creator1111111111111111111111111111111111"
CREATOR_2 = "Creator2222222222222222222222222222222222"
S0 = 42_000_000_000
T0 = 764_000_000_000_000
SIZE = 200_000_000

CAP_CASES = [
    "ledger_inconsistent",
    "kill_switch",
    "halted",
    "breaker_open",
    "live_gate",
    "approval_missing",
    "approval_mismatch",
    "seat_may_trade",
    "max_trades_per_day",
    "max_open_positions",
    "already_open",
    "creator_already_open",
    "max_trade_fraction",
    "max_token_fraction",
    "daily_loss_halt",
    "drawdown_halt",
    "data_stale",
    "size_too_small",
    "below_liquidity_floor",
]


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
    kwargs.setdefault("autonomy", "autonomous-paper")
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(21)),
        clock=clock,
        **kwargs,
    )


def _buy(
    clock: FixtureClock,
    ids: IdFactory,
    mint: str = MINT_A,
    size: int = SIZE,
    approval_id: str | None = None,
) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=mint,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=size,
        max_slippage_bps=50,
        approval_id=approval_id or f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _sell(clock: FixtureClock, ids: IdFactory, units: int = 3_000_000) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT_A,
        side="sell",
        decision_id=ids.ulid(),
        token_units=units,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _append(store: LedgerStore, clock: FixtureClock, type: str, payload: dict[str, Any]) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"seed-{store.count() + 1}",
        type=type,
        payload=payload,
    )


def _fill_payload(
    clock: FixtureClock, ids: IdFactory, cash_delta: int = 0, side: str = "sell"
) -> dict[str, Any]:
    return {
        "source": "paper",
        "order_id": ids.ulid(),
        "decision_id": ids.ulid(),
        "side": side,
        "mint": MINT_A,
        "filled_lamports": 0,
        "filled_units": 0,
        "filled_fraction": "1",
        "price_avg": "0.00001",
        "venue_fee_lamports": 0,
        "network_cost_lamports": 0,
        "cash_delta_lamports": cash_delta,
        "latency_s": "1.0",
        "venue_tx_ref": "",
    }


def _position_payload(mint: str, creator: str, units: int, basis: int) -> dict[str, Any]:
    return {
        "source": "paper",
        "mint": mint,
        "price_entry": "0.00001",
        "token_units": units,
        "cost_basis_lamports": basis,
        "opened_ts_utc": format_ts_utc(START),
        "symbol": "TST",
        "creator": creator,
        "ticket_id": TICKET,
        "score": "0.8",
    }


def _halt_payload(reason: str) -> dict[str, Any]:
    return {
        "source": "paper",
        "reason": reason,
        "detail": "seeded",
        "equity_lamports": EQUITY,
        "day_start_equity_lamports": EQUITY,
        "set_by": "risk_engine",
    }


def _breaker_payload(breaker: str) -> dict[str, Any]:
    return {
        "source": "paper",
        "breaker": breaker,
        "metric": "seeded",
        "threshold": "seeded",
        "cooldown_s": 60,
    }


def _mtm_payload(prices: dict[str, int]) -> dict[str, Any]:
    return {
        "source": "paper",
        "ts_source": "curve",
        "cash_lamports": EQUITY,
        "equity_lamports": EQUITY,
        "unrealized_lamports": 0,
        "prices_json": json.dumps(
            {m: {"mtm_lamports": v, "spot": "0.00001", "source": "curve"} for m, v in prices.items()}
        ),
    }


def _tamper(store: LedgerStore) -> LedgerStore:
    """Simulate at-rest tampering below the append-only triggers."""
    db_path_str = str(store.path)
    store.close()
    raw = sqlite3.connect(db_path_str)
    try:
        raw.execute("DROP TRIGGER IF EXISTS events_append_only_u;")
        raw.execute("UPDATE events SET payload_json = '{\"tampered\": true}' WHERE seq = 1;")
        raw.commit()
    finally:
        raw.close()
    return LedgerStore(db_path_str)


def _seed(rule: str, store: LedgerStore, clock: FixtureClock, ids: IdFactory) -> dict[str, Any]:
    """Per-rule ledger/engine setup; returns extra engine kwargs."""
    if rule == "max_trades_per_day":
        for _ in range(20):
            _append(store, clock, "FillRecorded", _fill_payload(clock, ids, side="buy"))
    elif rule == "max_open_positions":
        for mint in (MINT_A, MINT_B, MINT_C):
            _append(store, clock, "PositionOpened", _position_payload(mint, CREATOR_1, 1_000, 1_000))
    elif rule == "already_open":
        _append(store, clock, "PositionOpened", _position_payload(MINT_A, CREATOR_1, 1_000, 1_000))
    elif rule == "creator_already_open":
        _append(store, clock, "PositionOpened", _position_payload(MINT_A, CREATOR_1, 1_000, 1_000))
    elif rule == "max_token_fraction":
        # Residual-basis row: zero open units passes already_open, so the
        # max_token_fraction cap step itself trims the 200M buy to 100M.
        _append(
            store, clock, "PositionOpened", _position_payload(MINT_A, CREATOR_1, 0, 400_000_000)
        )
        _append(store, clock, "MarkToMarket", _mtm_payload({MINT_A: 1_000_000}))
    elif rule == "daily_loss_halt":
        _append(store, clock, "FillRecorded", _fill_payload(clock, ids, cash_delta=-600_000_000))
    elif rule == "drawdown_halt":
        _append(store, clock, "FillRecorded", _fill_payload(clock, ids, cash_delta=2_000_000_000))
        _append(store, clock, "FillRecorded", _fill_payload(clock, ids, cash_delta=-2_000_000_000))
    elif rule == "data_stale":
        _append(store, clock, "PositionOpened", _position_payload(MINT_B, CREATOR_1, 1_000, 1_000))
    elif rule == "halted":
        _append(store, clock, "HaltSet", _halt_payload("manual"))
    elif rule == "breaker_open":
        _append(store, clock, "BreakerTripped", _breaker_payload("data_stale"))
    if rule == "kill_switch":
        return {"env": {"PUMPGROK_KILLSWITCH": "1"}}
    if rule == "live_gate":
        return {"mode": "live"}
    if rule in ("approval_missing", "approval_mismatch"):
        return {"autonomy": "manual-ticket"}
    if rule == "below_liquidity_floor":
        return {"get_reserves": lambda _mint: (1_000_000_000, 100_000_000_000_000)}
    return {}


def _order_for(
    rule: str, store: LedgerStore, clock: FixtureClock, ids: IdFactory
) -> OrderRequest:
    if rule == "already_open":
        return _buy(clock, ids, mint=MINT_A)
    if rule == "creator_already_open":
        return _buy(clock, ids, mint=MINT_B)
    if rule in ("max_open_positions",):
        return _buy(clock, ids, mint=MINT_D)
    if rule == "size_too_small":
        return _buy(clock, ids, size=5_000_000)
    if rule == "max_trade_fraction":
        return _buy(clock, ids, size=300_000_000)
    if rule == "seat_may_trade":
        return _buy(clock, ids)
    if rule == "approval_mismatch":
        approval_id = f"apr-{ids.ulid()}"
        record = parse_human_phrase(
            f"approve {TICKET} {MINT_A} 0.3 100",
            kind="human_buy",
            by="human:alice",
            approval_id=approval_id,
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        record_human_approval(
            store, record, ts_utc=format_ts_utc(clock.now()), source="paper",
            correlation_id="test",
        )
        return _buy(clock, ids, approval_id=approval_id)
    return _buy(clock, ids)


def test_r34_vocabulary_matches_check_limits_tool() -> None:
    assert list(STEP_IDS) == list(R34_RULE_IDS)
    assert len(STEP_IDS) == 19


@pytest.mark.parametrize("rule", CAP_CASES)
def test_check_order_caps(tmp_path: Path, rule: str) -> None:
    """INV-R-07: every buy-side cap trips with its R34 rule id, or caps the size."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(21))
        extra = _seed(rule, store, clock, ids)
        if rule == "ledger_inconsistent":
            _append(store, clock, "HaltSet", _halt_payload("manual"))
            store = _tamper(store)
        engine = _engine(store, clock, **extra)
        order = _order_for(rule, store, clock, ids)
        seat = "bot-00-chief" if rule == "seat_may_trade" else "bot-04-sniper"
        creator = CREATOR_1 if rule == "creator_already_open" else None
        decision = engine.check(order, seat=seat, creator=creator)
        evaluated = {row["id"]: row["status"] for row in decision.evaluated}
        assert list(evaluated) == list(R34_RULE_IDS)
        if rule == "max_trade_fraction":
            assert decision.passed is True
            assert decision.capped is True
            assert decision.size_lamports == int(Decimal(EQUITY) * Decimal("0.02"))
            assert decision.caps.get("max_trade_fraction") == decision.size_lamports
            assert evaluated[rule] == "pass"
            return
        if rule == "max_token_fraction":
            assert decision.passed is True
            assert decision.capped is True
            assert decision.size_lamports == 100_000_000
            assert decision.caps.get("max_token_fraction") == 100_000_000
            assert evaluated[rule] == "pass"
            return
        assert decision.passed is False
        assert decision.reason == rule, f"{rule}: got {decision.reason}"
        assert evaluated[rule] == "fail"
    finally:
        store.close()


def test_sells_always_allowed_except_ledger_and_live_gate(tmp_path: Path) -> None:
    """INV-R-08: halt/kill/breaker never stop an exit sell; ledger/live-gate do."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(21))
        _append(store, clock, "PositionOpened", _position_payload(MINT_A, CREATOR_1, 3_000_000, 30))
        _append(store, clock, "HaltSet", _halt_payload("manual"))
        _append(store, clock, "BreakerTripped", _breaker_payload("data_stale"))
        kill_engine = _engine(store, clock, env={"PUMPGROK_KILLSWITCH": "1"})
        decision = kill_engine.check(_sell(clock, ids), seat="bot-02-risk", exit_reason="kill_flatten")
        assert decision.passed is True
        store = _tamper(store)
        tampered_engine = _engine(store, clock, env={"PUMPGROK_KILLSWITCH": "1"})
        refused = tampered_engine.check(
            _sell(clock, ids), seat="bot-02-risk", exit_reason="kill_flatten"
        )
        assert refused.passed is False
        assert refused.reason == "ledger_inconsistent"
    finally:
        store.close()
    store_b = _store(tmp_path / "b")
    try:
        clock_b = FixtureClock(start=START)
        ids_b = IdFactory(clock_b, make_rng(21))
        live_engine = _engine(store_b, clock_b, mode="live")
        live_refused = live_engine.check(
            _sell(clock_b, ids_b), seat="bot-06-exit", exit_reason="exit_rule"
        )
        assert live_refused.passed is False
        assert live_refused.reason == "live_gate"
    finally:
        store_b.close()


def test_sell_mtm_seed_shape(tmp_path: Path) -> None:
    """Guard: the position seed above folds with token units intact."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _append(store, clock, "PositionOpened", _position_payload(MINT_A, CREATOR_1, 3_000_000, 30))
        engine = _engine(store, clock)
        state = engine._fold()
        assert state.positions[MINT_A].token_units == 3_000_000
        assert store.read(types=["PositionOpened"], limit=None)[0]["payload"]["mint"] == MINT_A
    finally:
        store.close()
