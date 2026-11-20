"""Characterization: RiskEngine._evaluate, inputs to outputs (QLT-05, RSK-08, CONTEXT D-10).

Pins the 19-step walk on the unsplit engine before plan 11-04 splits RiskEngine._evaluate.
Each scenario builds a fresh ledger, runs one order through check() or _evaluate() and
asserts the decision: reason, passed, sizing, caps, probe and the 19 evaluated rows in
STEP_IDS order. Rows follow the walk rule: steps before the first failure pass unless the
walk skips them, the failing step fails and every later step is skipped.

The two replay hashes that the walk feeds (smoke-10m and the trading smoke fixture) are
pinned at the end of this file, measured through the verify entry in an empty directory
(CONTEXT D-08, D-09).
"""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import random
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "replay"))

from pin_support import pinned_process_state

from pumpgrok.cli import main as cli_main
from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import STEP_IDS, RiskDecision, RiskEngine, order_hash_for
from pumpgrok.risk.engine.constants import _RECHECK_STEPS, EXIT_SKIP_STEPS

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
BUY_SEAT = "bot-04-sniper"
SELL_SEAT = "bot-06-exit"

#: Recorded replay pins (tests/fixtures/replay/pins and CHANGELOG Phase 11 entries).
SMOKE_10M_EVENTS_HASH = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d"
TRADING_SMOKE_EVENTS_HASH = "bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54"

_HASH_LINE = re.compile(r"^events\.hash=([0-9a-f]{64})$", re.MULTILINE)
_CHAIN_LINE = re.compile(r"^verify=CONSISTENT seq=(\d+) events=(\d+)$", re.MULTILINE)

Scenario = Callable[[Path], RiskDecision]


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, seed: int = 11, **kwargs: Any) -> RiskEngine:
    kwargs.setdefault("autonomy", "autonomous-paper")
    kwargs.setdefault("get_reserves", lambda _mint: BIG_RESERVES)
    kwargs.setdefault("budget", RiskBudget())
    return RiskEngine(
        store=store,
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        **kwargs,
    )


_KEY_SEQ = itertools.count(1)


def _append(
    store: LedgerStore, clock: FixtureClock, event_type: str, payload: dict[str, Any]
) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"char-{next(_KEY_SEQ)}",
        type=event_type,
        payload=payload,
    )


def _approval_payload(
    clock: FixtureClock,
    approval_id: str,
    kind: str,
    mint: str,
    *,
    size: int = 0,
    units: int = 0,
    rule: str = "",
) -> dict[str, Any]:
    return {
        "source": "paper",
        "id": approval_id,
        "kind": kind,
        "approved_by": "human:alice",
        "at": format_ts_utc(clock.now()),
        "ticket_id": TICKET,
        "mint": mint,
        "size_lamports": size,
        "token_units": units,
        "max_slippage_bps": 50,
        "exit_rule_id": rule,
        "raw_message": f"approve {TICKET} {mint}",
        "consumed": False,
    }


def _fill_payload(ids: IdFactory, side: str, mint: str, cash_delta: int = 0) -> dict[str, Any]:
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
    prices_json = {
        m: {"mtm_lamports": v, "spot": "0.00001", "source": "curve"} for m, v in prices.items()
    }
    return {
        "source": "paper",
        "ts_source": "curve",
        "cash_lamports": EQUITY,
        "equity_lamports": EQUITY,
        "unrealized_lamports": 0,
        "prices_json": json.dumps(prices_json),
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


def _buy(
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
    ids: IdFactory, mint: str = MINT_A, units: int = 3_000_000, approval_id: str | None = None
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


def _expected_rows(
    failed: str | None, skipped: frozenset[str] = frozenset()
) -> list[dict[str, str]]:
    """The 19 rows the walk must produce: pass, skipped, the failing step, then skip."""
    rows: list[dict[str, str]] = []
    reached = False
    for step in STEP_IDS:
        if reached:
            status = "skip"
        elif step == failed:
            status = "fail"
            reached = True
        elif step in skipped:
            status = "skip"
        else:
            status = "pass"
        rows.append({"id": step, "status": status})
    return rows


def _pass_rows(skipped: frozenset[str] = frozenset()) -> list[dict[str, str]]:
    return _expected_rows(None, skipped)


# --- scenarios: each builds a fresh ledger under tmp_path and returns one decision ----------


def _s_buy_passes(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        return _engine(store, clock).check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_kill_switch_env(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, env={"PUMPGROK_KILLSWITCH": "1"})
        return engine.check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_halted(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(store, clock, "HaltSet", _halt_payload("manual"))
        return _engine(store, clock).check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_breaker_open(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(store, clock, "BreakerTripped", _breaker_payload("data_stale"))
        return _engine(store, clock).check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_live_gate(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        return _engine(store, clock, mode="live").check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_approval_missing(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, autonomy="manual-ticket")
        return engine.check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_approval_mismatch(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        approval_id = f"apr-{ids.ulid()}"
        _append(
            store,
            clock,
            "ApprovalRecorded",
            _approval_payload(clock, approval_id, "human_buy", MINT_A, size=1),
        )
        engine = _engine(store, clock, autonomy="manual-ticket")
        return engine.check(_buy(ids, approval_id=approval_id), seat=BUY_SEAT)
    finally:
        store.close()


def _s_seat_may_trade(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        return _engine(store, clock).check(_buy(ids), seat=SELL_SEAT)
    finally:
        store.close()


def _s_max_trades_per_day(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        for _ in range(20):
            _append(store, clock, "FillRecorded", _fill_payload(ids, "buy", MINT_B))
        return _engine(store, clock).check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_max_open_positions(tmp_path: Path) -> RiskDecision:
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
        return _engine(store, clock).check(_buy(ids, mint=MINT_D), seat=BUY_SEAT)
    finally:
        store.close()


def _s_already_open(tmp_path: Path) -> RiskDecision:
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
        return _engine(store, clock).check(_buy(ids, mint=MINT_A), seat=BUY_SEAT)
    finally:
        store.close()


def _s_creator_already_open(tmp_path: Path) -> RiskDecision:
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
        return _engine(store, clock).check(_buy(ids, mint=MINT_B), seat=BUY_SEAT, creator=CREATOR_1)
    finally:
        store.close()


def _s_max_trade_fraction_caps(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        return _engine(store, clock).check(_buy(ids, size=500_000_000), seat=BUY_SEAT)
    finally:
        store.close()


def _s_max_token_fraction(tmp_path: Path) -> RiskDecision:
    # A zero-unit basis row isolates the cap-floor branch of step 14 (already_open
    # would refuse an open mint earlier).
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
        return _engine(store, clock).check(_buy(ids, size=600_000_000), seat=BUY_SEAT)
    finally:
        store.close()


def _s_daily_loss_halt(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "FillRecorded",
            _fill_payload(ids, "sell", MINT_A, cash_delta=-600_000_000),
        )
        return _engine(store, clock).check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_data_stale(tmp_path: Path) -> RiskDecision:
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
        return _engine(store, clock).check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_size_too_small(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        return _engine(store, clock).check(_buy(ids, size=5_000_000), seat=BUY_SEAT)
    finally:
        store.close()


def _s_below_liquidity_floor(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        thin = _engine(
            store, clock, get_reserves=lambda _mint: (1_000_000_000, 100_000_000_000_000)
        )
        return thin.check(_buy(ids), seat=BUY_SEAT)
    finally:
        store.close()


def _s_exit_sell_skips_stop_steps(tmp_path: Path) -> RiskDecision:
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
                clock, approval_id, "exit_rule", MINT_A, units=3_000_000, rule="stop_loss"
            ),
        )
        engine = _engine(store, clock, autonomy="manual-ticket", env={"PUMPGROK_KILLSWITCH": "1"})
        order = _sell(ids, approval_id=approval_id)
        return engine.check(order, seat=SELL_SEAT, exit_reason="exit_rule")
    finally:
        store.close()


def _s_kill_flatten_sell(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, env={"PUMPGROK_KILLSWITCH": "1"})
        return engine.check(_sell(ids), seat=BUY_SEAT, exit_reason="kill_flatten")
    finally:
        store.close()


def _s_confirming_kill_switch(tmp_path: Path) -> RiskDecision:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    killswitch = tmp_path / "KILLSWITCH"
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, killswitch_path=killswitch)
        order = _buy(ids)
        assert engine.check(order, seat=BUY_SEAT).passed is True
        killswitch.write_text("operator stop", encoding="utf-8")
        return engine.check(order, seat=BUY_SEAT, stage="CONFIRMING")
    finally:
        store.close()


_CONFIRMING_SKIPPED = frozenset(STEP_IDS) - _RECHECK_STEPS

#: scenario id -> (builder, expected reason, expected passed, expected rows)
SCENARIOS: dict[str, tuple[Scenario, str, bool, list[dict[str, str]]]] = {
    "buy_passes": (_s_buy_passes, "pass", True, _pass_rows()),
    "kill_switch_env": (_s_kill_switch_env, "kill_switch", False, _expected_rows("kill_switch")),
    "halted": (_s_halted, "halted", False, _expected_rows("halted")),
    "breaker_open": (_s_breaker_open, "breaker_open", False, _expected_rows("breaker_open")),
    "live_gate": (_s_live_gate, "live_gate", False, _expected_rows("live_gate")),
    "approval_missing": (
        _s_approval_missing,
        "approval_missing",
        False,
        _expected_rows("approval_missing"),
    ),
    "approval_mismatch": (
        _s_approval_mismatch,
        "approval_mismatch",
        False,
        _expected_rows("approval_mismatch"),
    ),
    "seat_may_trade": (
        _s_seat_may_trade,
        "seat_may_trade",
        False,
        _expected_rows("seat_may_trade"),
    ),
    "max_trades_per_day": (
        _s_max_trades_per_day,
        "max_trades_per_day",
        False,
        _expected_rows("max_trades_per_day"),
    ),
    "max_open_positions": (
        _s_max_open_positions,
        "max_open_positions",
        False,
        _expected_rows("max_open_positions"),
    ),
    "already_open": (_s_already_open, "already_open", False, _expected_rows("already_open")),
    "creator_already_open": (
        _s_creator_already_open,
        "creator_already_open",
        False,
        _expected_rows("creator_already_open"),
    ),
    "max_trade_fraction_caps": (_s_max_trade_fraction_caps, "pass", True, _pass_rows()),
    "max_token_fraction": (
        _s_max_token_fraction,
        "max_token_fraction",
        False,
        _expected_rows("max_token_fraction"),
    ),
    "daily_loss_halt": (
        _s_daily_loss_halt,
        "daily_loss_halt",
        False,
        _expected_rows("daily_loss_halt"),
    ),
    "data_stale": (_s_data_stale, "data_stale", False, _expected_rows("data_stale")),
    "size_too_small": (
        _s_size_too_small,
        "size_too_small",
        False,
        _expected_rows("size_too_small"),
    ),
    "below_liquidity_floor": (
        _s_below_liquidity_floor,
        "below_liquidity_floor",
        False,
        _expected_rows("below_liquidity_floor"),
    ),
    "exit_sell_skips_stop_steps": (
        _s_exit_sell_skips_stop_steps,
        "pass",
        True,
        _pass_rows(EXIT_SKIP_STEPS),
    ),
    "kill_flatten_sell": (_s_kill_flatten_sell, "pass", True, _pass_rows(EXIT_SKIP_STEPS)),
    "confirming_kill_switch": (
        _s_confirming_kill_switch,
        "kill_switch",
        False,
        _expected_rows("kill_switch", _CONFIRMING_SKIPPED),
    ),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_walk_outputs_reason_passed_and_nineteen_rows(tmp_path: Path, name: str) -> None:
    build, reason, passed, rows = SCENARIOS[name]
    decision = build(tmp_path)
    assert decision.reason == reason
    assert decision.passed is passed
    assert decision.evaluated == rows
    assert [row["id"] for row in decision.evaluated] == list(STEP_IDS)


def test_buy_pass_sizing_and_probe_outputs(tmp_path: Path) -> None:
    decision = _s_buy_passes(tmp_path)
    assert decision.size_lamports == 200_000_000
    assert decision.token_units is None
    assert decision.capped is False
    assert decision.caps == {}
    assert decision.probe is False
    assert decision.approval_id is not None
    assert decision.approval is not None
    assert decision.approval.approved_by == "risk_engine"
    assert decision.order_hash == order_hash_for(
        _buy(IdFactory(FixtureClock(start=START), random.Random(11)))
    )


def test_max_trade_fraction_outputs_cap_and_size(tmp_path: Path) -> None:
    decision = _s_max_trade_fraction_caps(tmp_path)
    assert decision.capped is True
    assert decision.size_lamports == 200_000_000
    assert decision.caps == {"max_trade_fraction": 200_000_000}


def test_sell_outputs_token_units_and_no_size(tmp_path: Path) -> None:
    decision = _s_kill_flatten_sell(tmp_path)
    assert decision.size_lamports is None
    assert decision.token_units == 3_000_000
    assert decision.approval is not None
    assert decision.approval.approved_by == "risk_engine"


def test_daily_loss_halt_appends_one_halt_row(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _append(
            store,
            clock,
            "FillRecorded",
            _fill_payload(ids, "sell", MINT_A, cash_delta=-600_000_000),
        )
        decision = _engine(store, clock).check(_buy(ids), seat=BUY_SEAT)
        assert decision.reason == "daily_loss_halt"
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        payload = halts[0]["payload"]
        assert isinstance(payload, dict)
        assert payload["reason"] == "daily_loss"
    finally:
        store.close()


def test_evaluate_direct_call_matches_the_check_walk(tmp_path: Path) -> None:
    """_evaluate is the step walk behind check(); a direct call yields the same rows."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock, env={"PUMPGROK_KILLSWITCH": "1"})
        order = _buy(ids)
        decision = engine._evaluate(
            order,
            order_hash=order_hash_for(order),
            seat=BUY_SEAT,
            exit_reason=None,
            creator=None,
            source="paper",
            correlation_id="desk",
            stage="ACCEPTED",
        )
        assert decision.passed is False
        assert decision.reason == "kill_switch"
        assert decision.order_hash == order_hash_for(order)
        assert decision.decision_id == order.decision_id
        assert decision.evaluated == _expected_rows("kill_switch")
    finally:
        store.close()


def test_check_caches_the_decision_for_a_repeat_order(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = _engine(store, clock)
        order = _buy(ids)
        first = engine.check(order, seat=BUY_SEAT)
        again = engine.check(order, seat=BUY_SEAT)
        assert again is first
    finally:
        store.close()


def test_identical_inputs_give_identical_decisions_across_fresh_ledgers(tmp_path: Path) -> None:
    runs: list[dict[str, Any]] = []
    for name in ("a", "b"):
        scratch = tmp_path / name
        scratch.mkdir()
        runs.append(_s_buy_passes(scratch).model_dump(mode="json"))
    assert runs[0] == runs[1]


def _verify(fixture: str) -> tuple[str, int, int]:
    """Run `pumpgrok verify --fixture <fixture>` in-process and parse its chain report."""
    captured = io.StringIO()
    with pinned_process_state(), contextlib.redirect_stdout(captured):
        code = cli_main(["verify", "--fixture", fixture])
    output = captured.getvalue()
    assert code == 0
    hashed = _HASH_LINE.search(output)
    chained = _CHAIN_LINE.search(output)
    assert hashed is not None
    assert chained is not None
    return hashed.group(1), int(chained.group(1)), int(chained.group(2))


def test_smoke_10m_replay_hash_and_chain_are_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _verify("smoke-10m") == (SMOKE_10M_EVENTS_HASH, 2, 41)


def test_trading_smoke_replay_hash_and_chain_are_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _verify("smoke") == (TRADING_SMOKE_EVENTS_HASH, 11, 5)
