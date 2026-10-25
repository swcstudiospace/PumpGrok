"""Shared curve snapshots, inflight registry, and ledger-row helpers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict

from pumpgrok.core.errors import OrderRejectedError, OrderUnknownError
from pumpgrok.ledger.reducer import PositionView
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.risk.killswitch import InflightBarrier


class CurveSnapshot(BaseModel):
    """Reserves observed at one instant. Integers; ratios stay Decimal."""

    model_config = ConfigDict(frozen=True)

    mint: str
    s_lamports: int
    t_units: int
    complete: bool = False
    source: str = "fixture"
    slot: int | None = None
    # Recorded time of the reading (fixture tick time). None for a live read, which is
    # priced at the moment it is taken.
    ts: float | None = None


class PriceSource(Protocol):
    """Curve reads. Live-paper binds RPC/REST; replay binds fixture ticks."""

    async def curve(self, mint: str) -> CurveSnapshot | None: ...


def _rejection_from_row(
    stored: Mapping[str, Any], *, fallback: OrderRejectedError
) -> OrderRejectedError:
    """Rebuild the refusal recorded in a stored ``OrderRejected`` row.

    A ``confirmation_timeout`` row maps to ``OrderUnknownError`` (the timed-out
    attempt is never retried); every other reason maps to the documented
    ``OrderRejectedError``. Unparseable rows fall back to the live error.
    """
    payload = stored.get("payload", {})
    if not isinstance(payload, dict):
        return fallback
    reason = str(payload.get("reason", fallback.reason))
    detail = str(payload.get("detail", fallback.detail))
    stage = str(payload.get("stage", fallback.stage))
    fees = payload.get("fees_lamports", fallback.fees_lamports)
    try:
        fees_lamports = int(fees)
    except (TypeError, ValueError):
        fees_lamports = fallback.fees_lamports
    if reason == "confirmation_timeout":
        return OrderUnknownError(reason, detail, stage=stage, fees_lamports=fees_lamports)
    return OrderRejectedError(reason, detail, stage=stage, fees_lamports=fees_lamports)


class _InflightOrders:
    """Orders between ACCEPTED and settlement; each key is mirrored into the barrier.

    The barrier is shared with the kill-switch flatten, which waits for it to
    drain. The set keeps the adapter's own membership test (``cancel``).
    """

    def __init__(self) -> None:
        self.barrier = InflightBarrier()
        self._keys: set[str] = set()

    def add(self, key: str) -> None:
        self._keys.add(key)
        self.barrier.register(key)

    def discard(self, key: str) -> None:
        self._keys.discard(key)
        self.barrier.done(key)

    def __contains__(self, key: object) -> bool:
        return key in self._keys


class _BuyQuote(NamedTuple):
    """Priced BUY at the decision reserves: fill, fees, and slippage threshold."""

    size: int
    filled: int
    fraction: Decimal
    venue_fee: int
    x_net: int
    slippage_bps: int
    out0: int
    threshold: int


class _BuyConfirmed(NamedTuple):
    """CONFIRMING outcome with the cap recompute applied and the fill priced."""

    curve1: CurveSnapshot
    latency_s: float
    filled: int
    fraction: Decimal
    venue_fee: int
    x_net: int
    out0: int
    threshold: int
    out1: int


def _at_iso(at: Any) -> str:
    if isinstance(at, datetime):
        return at.isoformat()
    return str(at)


def _ledger_mark_epoch(pos: PositionView) -> float | None:
    """Epoch of the last ledger mark for an open position; None when unmarked."""
    if not pos.last_mtm_ts_utc:
        return None
    try:
        return parse_ts_utc(pos.last_mtm_ts_utc)
    except ValueError:
        return None
