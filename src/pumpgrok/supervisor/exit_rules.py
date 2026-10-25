"""Exit rules over the ledger's open paper positions (STRUCT-003, PAPER-007, TOOL-009).

Each exit-seat pass folds the ledger into open positions, reads the curve at the
cycle's clock, and runs the ported rules (``engine/exits.py``) through the ported
``PositionWatcher``. A rule that fires is handed to ``place_sell``, which submits
one sell through the exit seat's granted ``exec.place``. A sell the venue reports
``unknown`` is never retried: that position is held out of later passes (R18,
single-send), so the desk does not sell it twice.

A position whose curve has completed (graduated) cannot take an ordinary order, so
it is closed first, at its last pre-graduation reserves, with reason ``graduated``.

A position is identified by its opening ``PositionOpened`` sequence, not only its
mint. A re-entry in the same mint therefore starts a new position with a fresh entry
and peak; it never inherits the peak of the trade it replaced.

Peaks for the trailing stop live in memory for the run. A restart re-learns them
from the next curve read; the vendor persisted them to disk.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.models import PRICE_SCALE, ExitPosition
from pumpgrok.engine.watcher import PositionWatcher
from pumpgrok.execution.curve_math import spot
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import Clock, parse_ts_utc
from pumpgrok.replay.sources import FixtureCurveSource

__all__ = ["ExitRules", "GraduateClose", "LedgerExitBook", "PlaceSell", "RuleSell"]

#: ``(mint, ticket_id, token_units, rule)`` -> the place tool's output payload.
PlaceSell = Callable[[str, str, int, str], Awaitable[dict[str, Any]]]

#: ``(mint, last_s, last_t)`` -> the PositionClosed row, or None when no position is open.
GraduateClose = Callable[[str, int, int], Awaitable[dict[str, Any] | None]]


def _scaled_price(lamports_per_token: Decimal) -> int:
    """Lamports-per-token quote to the integer ``PRICE_SCALE`` price (INT-01)."""
    return int((lamports_per_token * PRICE_SCALE).to_integral_value(rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class RuleSell:
    """One rule-fired sell (or graduation close) and what the venue answered."""

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
    #: mint -> the ``PositionOpened`` sequence of the position currently tracked.
    _identity: dict[str, int] = field(default_factory=dict)
    #: (mint, opening sequence) pairs whose sell the venue left unknown.
    _held_out: set[tuple[str, int]] = field(default_factory=set)

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
        """Stop offering the tracked position in ``mint`` whose sell the venue left unknown."""
        self._held_out.add((mint, self._identity[mint]))

    def sync(self, store: LedgerStore) -> None:
        """Rebuild the open positions from the ledger, one tracked position per mint.

        The peak carries over only while the opening sequence is unchanged. Entry,
        amount, opening time and ticket are refreshed from the ledger on every pass.
        """
        state = initial_state(source="replay", initial_equity_lamports=0, day_utc="")
        opened_seq: dict[str, int] = {}
        for event in store.read(limit=None):
            if event["type"] == "PositionOpened":
                opened_seq[str(event["payload"]["mint"])] = int(event["seq"])
            state = reduce(state, event)
        fresh: dict[str, ExitPosition] = {}
        identity: dict[str, int] = {}
        for mint, view in state.positions.items():
            if view.token_units <= 0:
                continue
            seq = opened_seq.get(mint, 0)
            if (mint, seq) in self._held_out:
                continue
            entry = _scaled_price(view.price_entry)
            prior = self._positions.get(mint)
            same_position = prior is not None and self._identity.get(mint) == seq
            peak = prior.peak_price if same_position and prior is not None else entry
            fresh[mint] = ExitPosition(
                mint=mint,
                entry_price=entry,
                peak_price=peak,
                token_amount=int(view.token_units),
                opened_at=parse_ts_utc(view.opened_ts_utc),
            )
            identity[mint] = seq
            self._tickets[mint] = view.ticket_id
        self._positions = fresh
        self._identity = identity


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
        graduate: GraduateClose | None = None,
    ) -> None:
        self._store = store
        self._curves = curves
        self._place_sell = place_sell
        self._graduate = graduate
        self._book = LedgerExitBook(exits)
        self._sold: list[RuleSell] = []
        self._watcher = PositionWatcher(self._book, self._price, self._sell, clock)

    async def _price(self, mint: str) -> int:
        snapshot = await self._curves.curve(mint)
        if snapshot is None or snapshot.t_units <= 0:
            return 0
        return _scaled_price(spot(snapshot.s_lamports, snapshot.t_units))

    async def _sell(self, position: ExitPosition, price: int, reason: str) -> None:
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

    async def _close_graduated(self) -> None:
        """Close each open position whose curve completed, at its last open reserves.

        The adapter refuses ordinary orders on a completed curve, rule sells included,
        so this runs before the ordinary rules and the position closes as ``graduated``.
        """
        if self._graduate is None:
            return
        for mint in list(self._book.positions):
            snapshot = await self._curves.curve(mint)
            if snapshot is None or not snapshot.complete:
                continue
            reserves = self._curves.last_open_reserves(mint)
            if reserves is None:
                continue
            row = await self._graduate(mint, reserves[0], reserves[1])
            if row is not None:
                self._sold.append(RuleSell(mint=mint, rule="graduated", status="filled", reason=""))

    def holding(self) -> bool:
        """Whether any open paper position is held right now (reads the ledger, no sells)."""
        self._book.sync(self._store)
        return bool(self._book.positions)

    async def check(self, now: float) -> list[RuleSell]:
        """One pass over the open positions at ``now``; returns the sells it placed."""
        self._book.sync(self._store)
        self._sold = []
        await self._close_graduated()
        self._book.sync(self._store)
        await self._watcher.check_once(now)
        return list(self._sold)
