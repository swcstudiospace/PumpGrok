"""RSK-01: the R34 max_token_fraction row is each strategy's own slice (criterion 2).

A buy attributed to a strategy is capped on the existing row against that strategy's slice, and
a second strategy in the same mint is not charged the first strategy's cost basis.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.ticket_refs import append_with_ticket_ref
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
MINT_A = "So11111111111111111111111111111111111111112"
CREATOR = "Creator1111111111111111111111111111111111"
ALPHA_TICKET = "SOL-20260201-001"
BETA_TICKET = "SOL-20260201-002"
BUY_SEAT = "bot-04-sniper"
BIG_RESERVES = (42_000_000_000, 764_000_000_000_000)


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock) -> RiskEngine:
    return RiskEngine(
        store=store,
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="autonomous-paper",
        budget=RiskBudget(),
        get_reserves=lambda _mint: BIG_RESERVES,
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


def _buy(ids: IdFactory, ticket: str, size: int) -> OrderRequest:
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
