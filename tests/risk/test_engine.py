"""RISK-001: the 19-step RiskEngine.check with first-failure-wins (plan 04-05).

One order flows through every R34 step in exact order to a bound
RiskDecision; each step rejects independently; a repeat check with the same
order_hash returns the identical decision.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
import sqlite3
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import (
    _DECISION_CACHE_MAX,
    FLOOR_HALTED_DAILY,
    STEP_IDS,
    RiskEngine,
    order_hash_for,
)
from pumpgrok.tools.risk.check_limits import R34_RULE_IDS

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "So22222222222222222222222222222222222222222"
MINT_C = "So33333333333333333333333333333333333333333"
MINT_D = "So44444444444444444444444444444444444444444"
CREATOR_1 = "Creator1111111111111111111111111111111111"
CREATOR_2 = "Creator2222222222222222222222222222222222"

BIG_RESERVES = (42_000_000_000, 764_000_000_000_000)


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(
    store: LedgerStore,
    clock: FixtureClock,
    seed: int = 11,
    autonomy: str = "autonomous-paper",
    **kwargs: Any,
) -> RiskEngine:
    kwargs.setdefault("get_reserves", lambda _mint: BIG_RESERVES)
    kwargs.setdefault("budget", RiskBudget())
    return RiskEngine(
        store=store,
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        autonomy=autonomy,  # type: ignore[arg-type]
        **kwargs,
    )


_KEY_SEQ = itertools.count(1)


def _append(
    store: LedgerStore,
    clock: FixtureClock,
    type: str,
    payload: dict[str, Any],
    *,
    source: str = "paper",
) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source=source,
        correlation_id="test",
        idempotency_key=f"test-{next(_KEY_SEQ)}",
        type=type,
        payload=payload,
    )


def _approval_payload(
    clock: FixtureClock,
    approval_id: str,
    kind: str,
    ticket: str,
    mint: str,
    *,
    size: int = 0,
    units: int = 0,
    slippage: int = 50,
    rule: str = "",
) -> dict[str, Any]:
    return {
        "source": "paper",
        "id": approval_id,
        "kind": kind,
        "approved_by": "human:alice",
        "at": format_ts_utc(clock.now()),
        "ticket_id": ticket,
        "mint": mint,
        "size_lamports": size,
        "token_units": units,
        "max_slippage_bps": slippage,
        "exit_rule_id": rule,
        "raw_message": f"approve {ticket} {mint}",
        "consumed": False,
    }


def _buy(
    clock: FixtureClock,
    ids: IdFactory,
    mint: str = MINT_A,
    size: int = 200_000_000,
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


def _sell(
    clock: FixtureClock,
    ids: IdFactory,
    mint: str = MINT_A,
    units: int = 3_000_000,
    approval_id: str | None = None,
) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=mint,
        side="sell",
        decision_id=ids.ulid(),
        token_units=units,
        max_slippage_bps=50,
        approval_id=approval_id or f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _fill_payload(
    clock: FixtureClock, ids: IdFactory, side: str, mint: str, cash_delta: int = 0
) -> dict[str, Any]:
    return {
        "source": "paper",
        "order_id": ids.ulid(),
        "decision_id": ids.ulid(),
        "side": side,
        "mint": mint,
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


def _position_payload(
    clock: FixtureClock, mint: str, creator: str, units: int, basis: int
) -> dict[str, Any]:
    return {
        "source": "paper",
        "mint": mint,
        "price_entry": "0.00001",
        "token_units": units,
        "cost_basis_lamports": basis,
        "opened_ts_utc": format_ts_utc(clock.now()),
        "symbol": "TST",
        "creator": creator,
        "ticket_id": TICKET,
        "score": "0.8",
    }


def _mtm_payload(prices: dict[str, int]) -> dict[str, Any]:
    return {
        "source": "paper",
        "ts_source": "curve",
        "cash_lamports": EQUITY,
        "equity_lamports": EQUITY,
        "unrealized_lamports": 0,
        "prices_json": json.dumps(
            {
                m: {"mtm_lamports": v, "spot": "0.00001", "source": "curve"}
                for m, v in prices.items()
            }
        ),
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


def test_step_order_matches_r34_vocabulary() -> None:
    assert list(STEP_IDS) == list(R34_RULE_IDS)
    assert len(STEP_IDS) == 19


def test_tracer_one_buy_passes_all_steps(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    engine = _engine(store, clock)
    order = _buy(clock, ids)
    decision = engine.check(order, seat="bot-04-sniper")
    try:
        assert decision.passed is True
        assert decision.reason == "pass"
        assert decision.order_hash == order_hash_for(order)
        assert [row["id"] for row in decision.evaluated] == list(STEP_IDS)
        assert all(row["status"] == "pass" for row in decision.evaluated)
        assert decision.approval_id is not None
        assert decision.approval is not None
        assert decision.approval.approved_by == "risk_engine"
        assert decision.size_lamports == 200_000_000
        assert decision.capped is False
        repeat = engine.check(order, seat="bot-04-sniper")
        assert repeat.decision_id == decision.decision_id
        assert repeat.order_hash == decision.order_hash
    finally:
        store.close()


def _eval_map(decision: Any) -> dict[str, str]:
    return {row["id"]: row["status"] for row in decision.evaluated}


def _assert_first_failure(decision: Any, step: str) -> None:
    assert decision.passed is False
    assert decision.reason == step
    states = _eval_map(decision)
    assert [row["id"] for row in decision.evaluated] == list(STEP_IDS)
    idx = list(STEP_IDS).index(step)
    for earlier in STEP_IDS[:idx]:
        assert states[earlier] == "pass", earlier
    assert states[step] == "fail"
    for later in STEP_IDS[idx + 1 :]:
        assert states[later] == "skip", later


def test_ledger_inconsistent_rejects_first(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "JournalNote",
            {
                "source": "paper",
                "seat": "desk",
                "note_kind": "note",
                "text": "x",
                "refs": [],
            },
        )
        raw = sqlite3.connect(str(tmp_path / "ledger.sqlite"))
        raw.execute("DROP TRIGGER events_append_only_u;")
        raw.execute("UPDATE events SET payload_json = '{}' WHERE seq = 1;")
        raw.commit()
        raw.close()
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "ledger_inconsistent")
    finally:
        store.close()


def test_kill_switch_env_rejects_buys(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, env={"PUMPGROK_KILLSWITCH": "1"})
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "kill_switch")
    finally:
        store.close()


def test_halted_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(store, clock, "HaltSet", _halt_payload("manual"))
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "halted")
    finally:
        store.close()


def test_breaker_open_rejects_buys(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(store, clock, "BreakerTripped", _breaker_payload("data_stale"))
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "breaker_open")
    finally:
        store.close()


def test_live_gate_rejects_in_live_mode(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, mode="live")
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "live_gate")
    finally:
        store.close()


def test_approval_missing_in_manual_mode(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, autonomy="manual-ticket")
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "approval_missing")
    finally:
        store.close()


def test_approval_mismatch_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        approval_id = f"apr-{ids.ulid()}"
        _append(
            store,
            clock,
            "ApprovalRecorded",
            _approval_payload(clock, approval_id, "human_buy", TICKET, MINT_A, size=1),
        )
        engine = _engine(store, clock, autonomy="manual-ticket")
        order = _buy(clock, ids, size=200_000_000, approval_id=approval_id)
        decision = engine.check(order, seat="bot-04-sniper")
        _assert_first_failure(decision, "approval_mismatch")
    finally:
        store.close()


def test_seat_may_trade_rejects_cross_orders(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock)
        buy = engine.check(_buy(clock, ids), seat="bot-06-exit")
        _assert_first_failure(buy, "seat_may_trade")
        sell_ids = IdFactory(clock, random.Random(12))
        sell = engine.check(_sell(clock, sell_ids), seat="bot-04-sniper")
        _assert_first_failure(sell, "seat_may_trade")
    finally:
        store.close()


def test_max_trades_per_day_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        for _ in range(20):
            _append(store, clock, "FillRecorded", _fill_payload(clock, ids, "buy", MINT_B))
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "max_trades_per_day")
    finally:
        store.close()


def test_max_open_positions_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        for mint in (MINT_A, MINT_B, MINT_C):
            _append(
                store,
                clock,
                "PositionOpened",
                _position_payload(clock, mint, CREATOR_1, 1_000_000, 1_000_000),
            )
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids, mint=MINT_D), seat="bot-04-sniper")
        _assert_first_failure(decision, "max_open_positions")
    finally:
        store.close()


def test_already_open_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "PositionOpened",
            _position_payload(clock, MINT_A, CREATOR_1, 1_000_000, 1_000_000),
        )
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids, mint=MINT_A), seat="bot-04-sniper")
        _assert_first_failure(decision, "already_open")
    finally:
        store.close()


def test_creator_already_open_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "PositionOpened",
            _position_payload(clock, MINT_A, CREATOR_1, 1_000_000, 1_000_000),
        )
        _append(store, clock, "MarkToMarket", _mtm_payload({MINT_A: 1_000_000}))
        engine = _engine(store, clock)
        decision = engine.check(
            _buy(clock, ids, mint=MINT_B), seat="bot-04-sniper", creator=CREATOR_1
        )
        _assert_first_failure(decision, "creator_already_open")
        other = engine.check(_buy(clock, ids, mint=MINT_B), seat="bot-04-sniper", creator=CREATOR_2)
        assert other.passed is True
    finally:
        store.close()


def test_max_trade_fraction_caps(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids, size=500_000_000), seat="bot-04-sniper")
        assert decision.passed is True
        assert decision.capped is True
        assert decision.size_lamports == 200_000_000
        assert decision.caps == {"max_trade_fraction": 200_000_000}
    finally:
        store.close()


def test_fraction_caps_use_decimal_math(tmp_path: Path) -> None:
    """WR-06: fraction caps are exact Decimal math on lamports (R28).

    ``float(Decimal("0.8455548"))`` is inexact, so the old
    ``int(float(fraction) * equity)`` cap lands one lamport above the
    Decimal computation at this equity. Money stays int; ratios stay Decimal.
    """
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        store.set_meta("initial_equity_lamports", "592936786815")
        engine = _engine(
            store,
            clock,
            budget=RiskBudget(max_trade_fraction=Decimal("0.8455548")),
            get_reserves=lambda _mint: (10**15, 10**18),
        )
        decision = engine.check(_buy(clock, ids, size=600_000_000_000), seat="bot-04-sniper")
        assert decision.capped is True
        assert decision.caps["max_trade_fraction"] == 501360546187
        assert decision.caps["max_trade_fraction"] == int(Decimal("0.8455548") * 592936786815)
        assert decision.caps["max_token_fraction"] == int(Decimal("0.05") * 592936786815)
    finally:
        store.close()


def test_max_token_fraction_rejects_below_minimum(tmp_path: Path) -> None:
    # The cost-basis term only binds when the mint is not open (an open mint
    # is refused earlier by already_open): a zero-unit basis row isolates the
    # cap-floor branch of step 14.
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "PositionOpened",
            _position_payload(clock, MINT_A, CREATOR_1, 0, 495_000_000),
        )
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids, size=600_000_000), seat="bot-04-sniper")
        _assert_first_failure(decision, "max_token_fraction")
    finally:
        store.close()


def test_daily_loss_halt_appends_and_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "FillRecorded",
            _fill_payload(clock, ids, "sell", MINT_A, cash_delta=-600_000_000),
        )
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "daily_loss_halt")
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        payload = halts[0]["payload"]
        assert payload["reason"] == "daily_loss"
        assert payload["detail"] == FLOOR_HALTED_DAILY
        assert payload["detail"].encode() == (b"FLOOR HALTED \xe2\x80\x93 DAILY LOSS LIMIT")
        assert (
            halts[0]["idempotency_key"]
            == hashlib.sha256(b"HaltSet|daily_loss|2026-10-21").hexdigest()
        )
    finally:
        store.close()


def test_drawdown_halt_appends_and_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "FillRecorded",
            _fill_payload(clock, ids, "sell", MINT_A, cash_delta=2_000_000_000),
        )
        _append(
            store,
            clock,
            "FillRecorded",
            _fill_payload(clock, ids, "sell", MINT_A, cash_delta=-2_000_000_000),
        )
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "drawdown_halt")
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        assert halts[0]["payload"]["reason"] == "drawdown"
    finally:
        store.close()


def test_data_stale_rejects_with_open_position(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "PositionOpened",
            _position_payload(clock, MINT_B, CREATOR_1, 1_000_000, 1_000_000),
        )
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "data_stale")
        clock.advance_to(START + 10.0)
        _append(store, clock, "MarkToMarket", _mtm_payload({MINT_B: 1_000_000}))
        fresh = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert fresh.passed is True
    finally:
        store.close()


def test_size_too_small_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids, size=5_000_000), seat="bot-04-sniper")
        _assert_first_failure(decision, "size_too_small")
    finally:
        store.close()


def test_below_liquidity_floor_rejects(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        thin = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, random.Random(11)),
            clock=clock,
            autonomy="autonomous-paper",
            get_reserves=lambda _mint: (1_000_000_000, 100_000_000_000_000),
        )
        decision = thin.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(decision, "below_liquidity_floor")
        noreserve = _engine(store, clock, get_reserves=lambda _mint: None)
        missing = noreserve.check(_buy(clock, ids), seat="bot-04-sniper")
        _assert_first_failure(missing, "below_liquidity_floor")
    finally:
        store.close()


def test_exit_sell_skips_stop_and_limit_steps(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(store, clock, "HaltSet", _halt_payload("manual"))
        _append(store, clock, "BreakerTripped", _breaker_payload("data_stale"))
        approval_id = f"apr-{ids.ulid()}"
        _append(
            store,
            clock,
            "ApprovalRecorded",
            _approval_payload(
                clock, approval_id, "exit_rule", TICKET, MINT_A, units=3_000_000, rule="stop_loss"
            ),
        )
        engine = _engine(store, clock, autonomy="manual-ticket", env={"PUMPGROK_KILLSWITCH": "1"})
        order = _sell(clock, ids, approval_id=approval_id)
        decision = engine.check(order, seat="bot-06-exit", exit_reason="exit_rule")
        assert decision.passed is True
        assert decision.reason == "pass"
        states = _eval_map(decision)
        for step in (
            "kill_switch",
            "halted",
            "breaker_open",
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
        ):
            assert states[step] == "skip", step
        for step in (
            "ledger_inconsistent",
            "live_gate",
            "approval_missing",
            "approval_mismatch",
            "seat_may_trade",
        ):
            assert states[step] == "pass", step
    finally:
        store.close()


def test_kill_flatten_sell_passes_from_any_seat(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, env={"PUMPGROK_KILLSWITCH": "1"})
        decision = engine.check(_sell(clock, ids), seat="bot-04-sniper", exit_reason="kill_flatten")
        assert decision.passed is True
        assert decision.approval is not None
        assert decision.approval.approved_by == "risk_engine"
    finally:
        store.close()


def test_confirming_recheck_rejects_inflight(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    killswitch = tmp_path / "KILLSWITCH"
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, killswitch_path=killswitch)
        order = _buy(clock, ids)
        assert engine.check(order, seat="bot-04-sniper").passed is True
        killswitch.write_text("operator stop", encoding="utf-8")
        recheck = engine.check(order, seat="bot-04-sniper", stage="CONFIRMING")
        assert recheck.passed is False
        assert recheck.reason == "kill_switch"
        states = _eval_map(recheck)
        for step in (
            "live_gate",
            "approval_missing",
            "approval_mismatch",
            "seat_may_trade",
            "max_open_positions",
        ):
            assert states[step] == "skip", step
    finally:
        store.close()


def test_confirming_refuses_buy_once_the_last_slot_is_taken(tmp_path: Path) -> None:
    """Review finding 13: two buys both pass ACCEPTED with one slot left.

    The first fills before the second confirms, so the second is refused at
    CONFIRMING with ``max_open_positions`` instead of leaving four positions.
    """
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "PositionOpened",
            _position_payload(clock, MINT_A, CREATOR_1, 1_000_000, 1_000_000),
        )
        _append(
            store,
            clock,
            "PositionOpened",
            _position_payload(clock, MINT_B, CREATOR_2, 1_000_000, 1_000_000),
        )
        _append(store, clock, "MarkToMarket", _mtm_payload({MINT_A: 1_000_000, MINT_B: 1_000_000}))
        engine = _engine(store, clock)
        first = _buy(clock, ids, mint=MINT_C)
        second = _buy(clock, ids, mint=MINT_D)
        assert engine.check(first, seat="bot-04-sniper").passed is True
        assert engine.check(second, seat="bot-04-sniper").passed is True
        assert engine.check(first, seat="bot-04-sniper", stage="CONFIRMING").passed is True
        _append(
            store,
            clock,
            "PositionOpened",
            _position_payload(clock, MINT_C, "Creator3333333333333333333333333333333333", 1, 1),
        )
        late = engine.check(second, seat="bot-04-sniper", stage="CONFIRMING")
        assert late.passed is False
        assert late.reason == "max_open_positions"
    finally:
        store.close()


def test_confirming_refuses_exit_sell_once_its_holding_is_closed(tmp_path: Path) -> None:
    """Review finding 7: a flatten closes the holding while an exit sell confirms.

    The exit sell must not sell the same tokens again: at CONFIRMING with no
    open holding it is refused with ``no_position``.
    """
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "PositionOpened",
            _position_payload(clock, MINT_A, CREATOR_1, 3_000_000, 1_000_000),
        )
        _append(store, clock, "MarkToMarket", _mtm_payload({MINT_A: 1_000_000}))
        approval_id = f"apr-{ids.ulid()}"
        _append(
            store,
            clock,
            "ApprovalRecorded",
            _approval_payload(
                clock, approval_id, "exit_rule", TICKET, MINT_A, units=3_000_000, rule="stop_loss"
            ),
        )
        engine = _engine(store, clock, autonomy="manual-ticket")
        order = _sell(clock, ids, approval_id=approval_id)
        assert engine.check(order, seat="bot-06-exit", exit_reason="exit_rule").passed is True
        _append(
            store,
            clock,
            "PositionClosed",
            {
                "source": "paper",
                "mint": MINT_A,
                "price_exit": "0.00001",
                "proceeds_lamports": 3_000_000,
                "realized_pnl_lamports": 0,
                "reason": "kill_flatten",
            },
        )
        late = engine.check(order, seat="bot-06-exit", exit_reason="exit_rule", stage="CONFIRMING")
        assert late.passed is False
        assert late.reason == "no_position"
    finally:
        store.close()


def test_repeat_check_returns_identical_decision(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock)
        order = _buy(clock, ids)
        first = engine.check(order, seat="bot-04-sniper")
        second = engine.check(order, seat="bot-04-sniper")
        assert second.decision_id == first.decision_id
        assert second.order_hash == first.order_hash
        assert second.evaluated == first.evaluated
    finally:
        store.close()


def test_cached_pass_does_not_survive_halt(tmp_path: Path) -> None:
    """WR-01: a cached PASS is not replayed after a halt engages."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock)
        order = _buy(clock, ids)
        first = engine.check(order, seat="bot-04-sniper")
        assert first.passed is True
        assert engine.check(order, seat="bot-04-sniper").decision_id == first.decision_id
        _append(store, clock, "HaltSet", _halt_payload("manual"))
        after = engine.check(order, seat="bot-04-sniper")
        assert after.passed is False
        assert after.reason == "halted"
        assert after.evaluated != first.evaluated
    finally:
        store.close()


def test_decision_cache_is_bounded(tmp_path: Path) -> None:
    """WR-01: the decision cache evicts oldest entries past its cap."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock)
        order = _buy(clock, ids)
        engine.check(order, seat="bot-04-sniper")
        for index in range(_DECISION_CACHE_MAX + 10):
            engine._decisions[f"old-{index}"] = engine.check(order, seat="bot-04-sniper")
        engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert len(engine._decisions) <= _DECISION_CACHE_MAX
    finally:
        store.close()
