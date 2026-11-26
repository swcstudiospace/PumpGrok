"""SC 10: the global exit book never double-sells a strategy position."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pumpgrok.config.sections.engine import ExitsSettings
from pumpgrok.engine.models import ExitPosition
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.strategy_state import record_attribution_ref
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.exit_rules import ExitRules, LedgerExitBook

MINT = "MintA11111111111111111111111111111111111"


def _open_store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def _rules(store: LedgerStore, place_sell) -> ExitRules:
    return ExitRules(
        store=store,
        curves=None,  # type: ignore[arg-type] -- _sell path only
        exits=ExitsSettings(),
        clock=FixtureClock(0.0),
        place_sell=place_sell,
    )


def test_claim_is_first_wins_per_ticket(tmp_path: Path) -> None:
    book = LedgerExitBook(ExitsSettings())
    assert book.claim_ticket("SOL-20260101-001") is True
    assert book.claim_ticket("SOL-20260101-001") is False
    assert book.claim_ticket("SOL-20260101-002") is True


def test_two_strategies_same_ticket_one_sell(tmp_path: Path) -> None:
    """Two strategies attributing one ticket position produce exactly one sell."""
    store = _open_store(tmp_path)
    try:
        ticket = "SOL-20260101-001"
        for strategy_id in ("momentum_breakout", "mean_reversion"):
            record_attribution_ref(
                store,
                strategy_id=strategy_id,
                ticket_id=ticket,
                mint=MINT,
                ts_utc="2026-01-01T00:00:00Z",
                source="paper",
                correlation_id=f"exit-filter-{strategy_id}",
            )
        sold: list[tuple[str, str, int, str]] = []

        async def _place_sell(mint: str, ticket_id: str, units: int, rule: str) -> dict[str, Any]:
            sold.append((mint, ticket_id, units, rule))
            return {"status": "filled", "reason": ""}

        rules = _rules(store, _place_sell)
        rules._book._tickets[MINT] = ticket
        position = ExitPosition(mint=MINT, entry_price=10, peak_price=12, token_amount=5)

        async def _race() -> None:
            # Two strategies' rule passes hitting the same ticket position.
            await rules._sell(position, 12, "take_profit")
            await rules._sell(position, 12, "trailing_stop")

        asyncio.run(_race())
        assert sold == [(MINT, ticket, 5, "take_profit")]
        assert len(rules._sold) == 1
    finally:
        store.close()


def test_reentry_new_ticket_sells_again(tmp_path: Path) -> None:
    """A fresh ticket (re-entry) is not blocked by a prior ticket's sell."""
    book = LedgerExitBook(ExitsSettings())
    assert book.claim_ticket("SOL-20260101-001") is True
    assert book.claim_ticket("SOL-20260101-002") is True
    assert book.claim_ticket("SOL-20260101-002") is False
