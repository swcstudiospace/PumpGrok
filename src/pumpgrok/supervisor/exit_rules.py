"""Exit rules over the ledger's open paper positions (STRUCT-003, PAPER-007, TOOL-009).

Each exit-seat pass folds the ledger into open positions, reads the curve at the
cycle's clock, and runs the ported rules (``engine/exits.py``) through the ported
``PositionWatcher``. A rule that fires is handed to ``place_sell``, which submits
one sell through the exit seat's granted ``exec.place``. A sell the venue reports
``unknown`` is never retried: that position is held out of later passes (R18,
single-send), so the desk does not sell it twice.

Peaks for the trailing stop live in memory for the run. A restart re-learns them
from the next curve read; the vendor persisted them to disk.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.models import ExitPosition
from pumpgrok.engine.watcher import PositionWatcher
from pumpgrok.execution.curve_math import spot
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import Clock, parse_ts_utc
from pumpgrok.replay.sources import FixtureCurveSource

__all__ = ["ExitRules", "LedgerExitBook", "PlaceSell", "RuleSell"]

#: ``(mint, ticket_id, token_units, rule)`` -> the place tool's output payload.
PlaceSell = Callable[[str, str, int, str], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class RuleSell:
    """One rule-fired sell and what the place tool answered."""

    mint: str
    rule: str
    status: str
    reason: str


@dataclass
class LedgerExitBook:
    """``PositionBook`` over the ledger: open paper positions, peaks kept in memory."""

    exits: ExitsSettings
    _positions: dict[str, ExitPosition] = field(default_factory=dict)
    _tickets: dict[str, str] = field(default_factory=dict)
    _held_out: set[str] = field(default_factory=set)

    @property
    def positions(self) -> dict[str, ExitPosition]:
        return self._positions

    @property
    def exit_config(self) -> ExitsSettings:
        return self.exits

    @property
    def poll_seconds(self) -> float:
        return self.exits.stop_loss_poll_seconds

    def persist(self) -> None:
        """Peaks stay in memory; nothing is written. See the module docstring."""

    def ticket(self, mint: str) -> str:
        return self._tickets[mint]

    def hold_out(self, mint: str) -> None:
        """Stop offering a position whose sell the venue left unknown (never retried)."""
        self._held_out.add(mint)

    def sync(self, store: LedgerStore) -> None:
        """Rebuild the open positions from the ledger; keep each peak already seen."""
        state = initial_state(source="replay", initial_equity_lamports=0, day_utc="")
        for event in store.read(limit=None):
            state = reduce(state, event)
        fresh: dict[str, ExitPosition] = {}
        for mint, view in state.positions.items():
            if view.token_units <= 0 or mint in self._held_out:
                continue
            prior = self._positions.get(mint)
            if prior is not None:
                fresh[mint] = prior
                continue
            entry = float(view.price_entry)
            fresh[mint] = ExitPosition(
                mint=mint,
                entry_price=entry,
                peak_price=entry,
                token_amount=float(view.token_units),
                opened_at=parse_ts_utc(view.opened_ts_utc),
            )
            self._tickets[mint] = view.ticket_id
        self._positions = fresh


class ExitRules:
    """One run's exit rules: the ported watcher wired to the ledger, curve reads and sells."""

    def __init__(
        self,
        *,
        store: LedgerStore,
        curves: FixtureCurveSource,
        exits: ExitsSettings,
        clock: Clock,
        place_sell: PlaceSell,
    ) -> None:
        self._store = store
        self._curves = curves
        self._place_sell = place_sell
        self._book = LedgerExitBook(exits)
        self._sold: list[RuleSell] = []
        self._watcher = PositionWatcher(self._book, self._price, self._sell, clock)

    async def _price(self, mint: str) -> float:
        snapshot = await self._curves.curve(mint)
        if snapshot is None or snapshot.t_units <= 0:
            return 0.0
        return float(spot(snapshot.s_lamports, snapshot.t_units))

    async def _sell(self, position: ExitPosition, price: float, reason: str) -> None:
        ticket = self._book.ticket(position.mint)
        result = await self._place_sell(position.mint, ticket, int(position.token_amount), reason)
        status = str(result["status"])
        if status == "unknown":
            self._book.hold_out(position.mint)
        self._sold.append(
            RuleSell(
                mint=position.mint,
                rule=reason,
                status=status,
                reason=str(result.get("reason") or ""),
            )
        )

    def holding(self) -> bool:
        """Whether any open paper position is held right now (reads the ledger, no sells)."""
        self._book.sync(self._store)
        return bool(self._book.positions)

    async def check(self, now: float) -> list[RuleSell]:
        """One pass over the open positions at ``now``; returns the rule sells it placed."""
        self._book.sync(self._store)
        self._sold = []
        await self._watcher.check_once(now)
        return list(self._sold)
