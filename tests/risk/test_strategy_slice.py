"""RSK-01: a buy above its strategy slice is capped or rejected on max_token_fraction.

TDD matrix: at cap passes, above cap is capped to the slice room, cap+1
lamports over the room is capped (never silently filled above the slice),
and an exhausted slice rejects on max_token_fraction with the reason on
the existing risk row. Slice state comes from ledger rows, never memory.

RSK-01: the R34 max_token_fraction row is each strategy's own slice (criterion 2).

A buy attributed to a strategy is capped on the existing row against that strategy's slice, and
a second strategy in the same mint is not charged the first strategy's cost basis.
"""

from __future__ import annotations

import itertools
import json
import random
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from pumpgrok.cli import main
from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.ticket_refs import append_with_ticket_ref
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.strategy_slice import SliceConfig, load_slice_config, spent_from_ledger

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
CREATOR = "Creator1111111111111111111111111111111111"
ALPHA_TICKET = "SOL-20260201-001"
BETA_TICKET = "SOL-20260201-002"
BUY_SEAT = "bot-04-sniper"
BIG_RESERVES = (42_000_000_000, 764_000_000_000_000)
STRATEGY = "momentum_breakout"


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _open(path: Path) -> LedgerStore:
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, *, enabled: bool = True) -> RiskEngine:
    config = SliceConfig(
        weights={STRATEGY: Decimal("0.02")},
        reserve=Decimal("0.80"),
        enabled=enabled,
    )
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="autonomous-paper",
        get_reserves=lambda _mint: BIG_RESERVES,
        slice_config=config,
    )


def _seed_alpha_position(store: LedgerStore, clock: FixtureClock, basis: int) -> None:
    """Alpha holds a zero-unit residual position in MINT_A with the given cost basis."""
    payload: dict[str, Any] = {
        "source": "paper",
        "mint": MINT_A,
        "price_entry": "0.00001",
        "token_units": 0,
        "cost_basis_lamports": basis,
        "opened_ts_utc": format_ts_utc(START),
        "symbol": "TST",
        "creator": CREATOR,
        "ticket_id": ALPHA_TICKET,
        "score": "0.8",
    }
    row = {
        "ts_utc": format_ts_utc(clock.now()),
        "source": "paper",
        "correlation_id": "test",
        "idempotency_key": f"position|{ALPHA_TICKET}",
        "type": "PositionOpened",
        "payload": payload,
    }
    append_with_ticket_ref(store, row, ticket_id=ALPHA_TICKET, strategy_id="alpha")


def _buy(ids: IdFactory, size: int, ticket: str = TICKET) -> OrderRequest:
    return OrderRequest(
        ticket_id=ticket,
        mint=MINT_A,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=size,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _record_spend(store: LedgerStore, clock: FixtureClock, size: int) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"spend-{size}-{clock.now()}",
        type="OrderPlaced",
        payload={
            "source": "paper",
            "order_id": "01H" + "0" * 23,
            "decision_id": "01H" + "0" * 23,
            "ticket_id": TICKET,
            "side": "buy",
            "mint": MINT_A,
            "slippage_bps": 50,
            "size_lamports": size,
            "approval_json": f'{{"strategy": "{STRATEGY}"}}',
        },
    )


def test_default_weights_sum_at_most_one_and_load_from_config() -> None:
    config = load_slice_config()
    assert config.weights == {
        "legacy_screening": Decimal("0.20"),
        "momentum_breakout": Decimal("0.20"),
        "new_launch_sniper": Decimal("0.20"),
        "mean_reversion": Decimal("0.20"),
    }
    assert config.reserve == Decimal("0.20")
    assert sum(config.weights.values(), Decimal("0")) + config.reserve <= Decimal("1.0")
    assert config.enabled is False  # config-gated off by default


def test_weights_summing_above_one_refuse_to_load(tmp_path: Path) -> None:
    bad = tmp_path / "slices.toml"
    bad.write_text(
        '[strategy.slice]\nenabled = true\nreserve = "0.20"\n'
        '[strategy.slice.weights]\nmomentum_breakout = "0.90"\n',
        encoding="utf-8",
    )
    try:
        load_slice_config(bad)
    except Exception as exc:
        assert isinstance(exc, ValueError)
    else:  # pragma: no cover
        raise AssertionError("weights above 1.0 must refuse to load")


def test_buy_at_the_slice_cap_passes(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    engine = _engine(store, clock)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 200_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is True
    assert decision.size_lamports == 200_000_000
    assert decision.capped is False


def test_buy_above_the_slice_is_capped_to_the_room(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    engine = _engine(store, clock)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 300_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is True
    assert decision.capped is True
    assert decision.size_lamports == 200_000_000
    assert decision.caps["strategy_slice"] == 200_000_000
    assert decision.reason == "pass"


def test_spent_from_ledger_shrinks_the_room_across_restart(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _record_spend(store, clock, 150_000_000)
    assert spent_from_ledger(store, STRATEGY) == 150_000_000
    # A fresh engine over the same ledger still sees the spend.
    engine = _engine(store, clock)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 300_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is True
    assert decision.size_lamports == 50_000_000
    assert decision.caps["strategy_slice"] == 50_000_000


def test_exhausted_slice_rejects_on_max_token_fraction(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _record_spend(store, clock, 195_000_000)
    engine = _engine(store, clock)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 300_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is False
    assert decision.reason == "max_token_fraction"
    assert any(
        row["id"] == "max_token_fraction" and row["status"] == "fail" for row in decision.evaluated
    )


def test_disabled_slice_behaves_exactly_as_before(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    engine = _engine(store, clock, enabled=False)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 300_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is True
    assert "strategy_slice" not in decision.caps


def test_strategy_buy_above_its_slice_is_capped_on_max_token_fraction(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    try:
        _seed_alpha_position(store, clock, basis=400_000_000)
        decision = _engine(store, clock).check(
            _buy(ids, ALPHA_TICKET, 200_000_000), seat=BUY_SEAT, strategy_id="alpha"
        )
        assert decision.passed is True
        assert decision.caps["max_token_fraction"] == 100_000_000
        assert decision.size_lamports == 100_000_000
    finally:
        store.close()


def test_strategy_buy_under_its_slice_is_unchanged(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    try:
        _seed_alpha_position(store, clock, basis=400_000_000)
        decision = _engine(store, clock).check(
            _buy(ids, ALPHA_TICKET, 50_000_000), seat=BUY_SEAT, strategy_id="alpha"
        )
        assert decision.passed is True
        assert "max_token_fraction" not in decision.caps
        assert decision.size_lamports == 50_000_000
    finally:
        store.close()


def test_second_strategy_in_the_same_mint_is_not_charged_the_first_basis(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    try:
        _seed_alpha_position(store, clock, basis=400_000_000)
        beta = _engine(store, clock).check(
            _buy(ids, BETA_TICKET, 200_000_000), seat=BUY_SEAT, strategy_id="beta"
        )
        assert beta.passed is True
        assert "max_token_fraction" not in beta.caps
        assert beta.size_lamports == 200_000_000

        desk = _engine(store, clock).check(_buy(ids, BETA_TICKET, 200_000_000), seat=BUY_SEAT)
        assert desk.caps["max_token_fraction"] == 100_000_000
    finally:
        store.close()