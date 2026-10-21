"""R62: a degraded reputation book fails closed (plan 04-06).

A corrupt reputation file quarantines to a degraded (empty) book. RiskEngine
refuses new buys with the breaker-scope reason ``reputation_degraded`` plus an
Escalation, while exits, kill-flatten and read-only views still run. The book
rebuilds from ledger PositionOpened/PositionClosed rows; a book with nothing
to rebuild from stays degraded and keeps refusing.
"""

from __future__ import annotations

import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.engine.reputation import ReputationBook
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import STEP_IDS, RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
CREATOR_1 = "Creator1111111111111111111111111111111111"

BIG_RESERVES = (42_000_000_000, 764_000_000_000_000)

_KEY_SEQ = iter(range(1, 10_000))


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(
    store: LedgerStore,
    clock: FixtureClock,
    reputation: ReputationBook | None = None,
    seed: int = 11,
) -> RiskEngine:
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: BIG_RESERVES,
        reputation=reputation,
    )


def _buy(clock: FixtureClock, ids: IdFactory, size: int = 200_000_000) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT_A,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=size,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _sell(
    clock: FixtureClock,
    ids: IdFactory,
    units: int = 3_000_000,
) -> OrderRequest:
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


def _append(
    store: LedgerStore,
    clock: FixtureClock,
    type: str,
    payload: dict[str, Any],
) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"test-{next(_KEY_SEQ)}",
        type=type,
        payload=payload,
    )


def _degraded_book(tmp_path: Path, clock: FixtureClock) -> ReputationBook:
    path = tmp_path / "reputation.json"
    path.write_text("{not json", encoding="utf-8")
    return ReputationBook.load(path, clock=clock)


def test_corrupt_file_degraded_book_refuses_buy_with_escalation(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        book = _degraded_book(tmp_path, clock)
        assert book.degraded
        assert book.creators == {}

        engine = _engine(store, clock, reputation=book)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")

        assert decision.passed is False
        assert decision.reason == "reputation_degraded"
        assert [row["id"] for row in decision.evaluated] == list(STEP_IDS)
        states = {row["id"]: row["status"] for row in decision.evaluated}
        assert states["breaker_open"] == "fail"
        for step in STEP_IDS[:3]:
            assert states[step] == "pass", step

        escalations = [
            event
            for event in store.read(types=["Escalation"], limit=None)
            if event["payload"].get("kind") == "reputation_degraded"
        ]
        assert len(escalations) == 1
        assert escalations[0]["payload"]["seat"] == "bot-02-risk"

        # A second buy the same day still refuses but emits no second row.
        repeat = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert repeat.passed is False
        assert repeat.reason == "reputation_degraded"
        again = [
            event
            for event in store.read(types=["Escalation"], limit=None)
            if event["payload"].get("kind") == "reputation_degraded"
        ]
        assert len(again) == 1
    finally:
        store.close()


def test_exit_and_kill_flatten_execute_on_degraded_book(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        book = _degraded_book(tmp_path, clock)
        engine = _engine(store, clock, reputation=book)

        exit_sell = engine.check(_sell(clock, ids), seat="bot-06-exit", exit_reason="exit_rule")
        assert exit_sell.passed is True
        assert exit_sell.reason == "pass"

        flatten = engine.check(_sell(clock, ids), seat="bot-04-sniper", exit_reason="kill_flatten")
        assert flatten.passed is True
        assert flatten.reason == "pass"
    finally:
        store.close()


def test_read_only_views_run_on_degraded_book(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    book = _degraded_book(tmp_path, clock)
    assert "0 creators" in book.summary()
    assert book.verdict("someone-new", block_after_rugs=1) is None
    assert book.verdict(None, block_after_rugs=1) is None


def _seed_rug_ledger(store: LedgerStore, clock: FixtureClock) -> None:
    _append(
        store,
        clock,
        "PositionOpened",
        {
            "source": "paper",
            "mint": MINT_A,
            "price_entry": "0.0001",
            "token_units": 1_000_000,
            "cost_basis_lamports": 100_000_000,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": CREATOR_1,
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )
    _append(
        store,
        clock,
        "PositionClosed",
        {
            "source": "paper",
            "mint": MINT_A,
            "price_exit": "0.00001",
            "proceeds_lamports": 10_000_000,
            "realized_pnl_lamports": -90_000_000,
            "reason": "stop_loss",
            "pnl_pct": "-0.9",
            "hold_seconds": 60,
            "venue_tx_ref": "",
        },
    )


def test_rebuild_restores_book_from_ledger(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        _seed_rug_ledger(store, clock)
        book = ReputationBook.rebuild_from_ledger(store, clock=clock)
        assert not book.degraded
        record = book.creators[CREATOR_1]
        assert record.tokens_bought == 1
        assert record.closed == 1
        assert record.rugs == 1
        assert record.worst_pnl_pct == -90.0
        assert record.realized_pnl_sol == -90_000_000 / 1_000_000_000

        engine = _engine(store, clock, reputation=book)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is True
        assert decision.reason == "pass"
    finally:
        store.close()


def test_unrestorable_book_stays_degraded_and_refuses(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(11))
    try:
        # An orphan close with no opener cannot be attributed to a creator.
        _append(
            store,
            clock,
            "PositionClosed",
            {
                "source": "paper",
                "mint": MINT_A,
                "price_exit": "0.00001",
                "proceeds_lamports": 10_000_000,
                "realized_pnl_lamports": -90_000_000,
                "reason": "stop_loss",
                "pnl_pct": "-0.9",
                "hold_seconds": 60,
                "venue_tx_ref": "",
            },
        )
        book = ReputationBook.rebuild_from_ledger(store, clock=clock)
        assert book.degraded
        assert book.creators == {}

        engine = _engine(store, clock, reputation=book)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is False
        assert decision.reason == "reputation_degraded"
    finally:
        store.close()
