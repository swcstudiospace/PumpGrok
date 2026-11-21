"""Fail-closed live price source (MKT-07, T-13-02a).

No network call inside: the caller feeds ticks/gaps. Disconnected yields
None; a completed curve refuses entry via :mod:`pumpgrok.datafeed.graduation`;
a gap holds the last good value (marked stale, never reused as new); a
timeout marks zero. Every call consults ``rpc_curve_price_allowed``.
"""

from __future__ import annotations

from pumpgrok.datafeed.events import CurveTick, GapEvent
from pumpgrok.datafeed.graduation import entry_refused
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.tools.onchain.curve_layout import rpc_curve_price_allowed


class LivePriceSource:
    """Thin wrapper over the tick stream and the allowlist price gate."""

    def __init__(self, *, timeout_s: float = 120.0) -> None:
        self._timeout_s = timeout_s
        self._connected = False
        self._ticks: dict[str, CurveTick] = {}
        self._gaps: set[str] = set()
        self._last_seen: dict[str, float] = {}

    def set_connected(self, connected: bool) -> None:
        self._connected = connected

    @property
    def connected(self) -> bool:
        return self._connected

    def on_tick(self, tick: CurveTick) -> None:
        self._ticks[tick.mint] = tick
        self._gaps.discard(tick.mint)
        self._last_seen[tick.mint] = parse_ts_utc(tick.ts_utc)

    def on_gap(self, gap: GapEvent) -> None:
        if gap.mint is not None:
            self._gaps.add(gap.mint)

    def is_stale(self, mint: str) -> bool:
        """True while a gap holds the position (last good kept, not new)."""
        return mint in self._gaps

    def entry_allowed(self, mint: str) -> bool:
        """False when disconnected, unverified, or the curve is complete."""
        if not self._connected:
            return False
        tick = self._ticks.get(mint)
        if tick is None:
            return False
        if not rpc_curve_price_allowed(curve_source=tick.curve_source):
            return False
        return not entry_refused(complete=tick.complete)

    def price(self, mint: str, *, now_epoch: float) -> int | None:
        """Integer lamports price, or None when no price may be used.

        Timeout yields 0 (mark zero) rather than a stale price.
        """
        if not self._connected:
            return None
        tick = self._ticks.get(mint)
        if tick is None:
            return None
        if not rpc_curve_price_allowed(curve_source=tick.curve_source):
            return None
        last = self._last_seen.get(mint, now_epoch)
        if now_epoch - last > self._timeout_s:
            return 0
        return tick.virtual_sol_reserves_lamports
