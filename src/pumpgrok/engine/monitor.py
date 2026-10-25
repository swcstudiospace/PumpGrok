"""PumpPortal new-launch monitor: filter on the fly, no trade subscription.

Port of the retired oracle ``src/monitor.py``. All prose is English;
the vendor text is Russian.

Deliberate divergences from the oracle (see STRUCT-003, R45/R46):

- ``_buyers`` and ``_subscribe_trades`` are deleted. The stream sends
  ``subscribeNewToken`` only, never ``subscribeTokenTrade``,
  ``unsubscribeTokenTrade``, or ``logsSubscribe``.
- ``Token.unique_buyers`` starts as ``None`` (no evidence). Where the
  vendor fired ``few_buyers`` on a missing count, the port fires
  ``data_unavailable`` and ``_promote`` treats it as terminal: without a
  trade stream a buffered token can never gain evidence, so buffering it
  would only leak memory until the TTL sweep.
- ``parse_create_event``, ``handle_event``, ``sweep``, and
  ``Token.age_seconds`` take ``now`` explicitly. ``now or time.time()``
  defaults are banned: ``0.0`` is falsy and would silently become wall
  time.
- ``websockets.asyncio.client.connect`` is the only connect path, called
  as ``connect(url, proxy=None, max_queue=data.ws_max_queue)``. Timeouts
  and sleeps go through the injected clock.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from websockets.asyncio.client import connect

from pumpgrok.config.settings import DataSettings, FilterSettings
from pumpgrok.engine.models import Token
from pumpgrok.replay.clock import Clock

log = logging.getLogger(__name__)

# A pump.fun curve counts as filled at about 85 SOL in reserve.
CURVE_COMPLETION_SOL = 85.0

# Same completion threshold in lamports (INT-01: reserves are integer money).
CURVE_COMPLETION_LAMPORTS = 85 * 1_000_000_000

# How long to keep a launch buffered while it never gains buyers.
PENDING_TTL_SECONDS = 900.0

# Memory ceilings. The process lives for days and pump.fun sees thousands
# of launches per hour: without bounds the buffer and the seen set grow
# without end.
MAX_PENDING = 2_000
MAX_REMEMBERED = 20_000


class SeenSet:
    """The last N keys. Oldest are evicted, memory does not leak."""

    def __init__(self, maxlen: int = MAX_REMEMBERED) -> None:
        self._items: OrderedDict[str, None] = OrderedDict()
        self._maxlen = maxlen

    def add(self, key: str) -> None:
        self._items.pop(key, None)
        self._items[key] = None
        while len(self._items) > self._maxlen:
            self._items.popitem(last=False)

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)


def _coerce_float(value: Any, default: float) -> float:
    """Best-effort float for untrusted socket fields. Default on garbage."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_lamports(value: Any, default: int) -> int:
    """Best-effort SOL amount to integer lamports, ROUND_HALF_UP. Default on garbage."""
    try:
        scaled = Decimal(str(value)) * 1_000_000_000
    except (ArithmeticError, ValueError, TypeError):
        return default
    try:
        return int(scaled.to_integral_value(rounding=ROUND_HALF_UP))
    except (ArithmeticError, ValueError, TypeError):
        return default


def parse_create_event(payload: dict[str, Any], now: float) -> Token | None:
    """A token-creation event becomes a Token. None when it is not one."""
    try:
        if payload.get("txType") not in ("create", "created"):
            return None
        mint = payload.get("mint") or payload.get("mintAddress")
        if not mint:
            return None

        created = payload.get("timestamp") or payload.get("createdTimestamp")
        created_num = _coerce_float(created, now)
        created_ts = created_num / 1000.0 if created and created_num > 1e11 else created_num
        sol_in_curve = _coerce_lamports(payload.get("vSolInBondingCurve"), 0)

        return Token(
            mint=mint,
            name=payload.get("name"),
            symbol=payload.get("symbol"),
            description=payload.get("description"),
            image_uri=payload.get("image") or payload.get("image_uri"),
            metadata_uri=payload.get("uri") or payload.get("metadata_uri"),
            twitter=payload.get("twitter"),
            telegram=payload.get("telegram"),
            website=payload.get("website"),
            creator=payload.get("traderPublicKey") or payload.get("creator"),
            created_timestamp=created_ts,
            sol_in_curve=sol_in_curve,
            market_cap_sol=_coerce_lamports(payload.get("marketCapSol"), 0),
            curve_progress=min(1.0, sol_in_curve / CURVE_COMPLETION_LAMPORTS),
        )
    except (TypeError, ValueError, AttributeError) as exc:
        log.warning("dropping malformed create event: %s", type(exc).__name__)
        return None


def passes_filter(token: Token, cfg: FilterSettings, now: float) -> tuple[bool, str]:
    """Base filter. Returns (passed, reason for rejection or "ok").

    The reason always travels with the verdict: it becomes the skip log,
    otherwise nobody can later tell what the flow died on.
    """
    # Terminal verdicts first (metadata, full curve), then temporary ones:
    # a token with a temporary verdict may still mature in the buffer.
    if cfg.require_metadata and not token.has_metadata:
        return False, "no_metadata"
    if token.curve_progress >= cfg.max_curve_progress:
        return False, "curve_too_full"
    if token.age_seconds(now) < cfg.min_age_seconds:
        return False, "too_young"
    if token.unique_buyers is None:
        return False, "data_unavailable"
    if token.unique_buyers < cfg.min_unique_buyers:
        return False, "few_buyers"
    return True, "ok"


class LaunchMonitor:
    """New-token subscription with on-the-fly filtering, no trade leg."""

    def __init__(
        self,
        data: DataSettings,
        filter_cfg: FilterSettings,
        clock: Clock,
        on_skip: Callable[[Token, str], None] | None = None,
    ) -> None:
        self.data = data
        self.filter_cfg = filter_cfg
        self.clock = clock
        self.on_skip = on_skip
        self.pending: dict[str, Token] = {}
        self._emitted = SeenSet()

    # -- event handling ----------------------------------------------------

    def handle_event(self, payload: dict[str, Any], now: float) -> Token | None:
        """One socket message. Returns a token ready to move downstream.

        Non-create payloads are ignored: without a trade subscription there
        is no buyer evidence to fold in, so buys, sells, and curve updates
        from the socket change nothing.
        """
        if payload.get("txType") not in ("create", "created"):
            return None
        token = parse_create_event(payload, now)
        if token and token.mint not in self._emitted:
            self._evict_if_crowded()
            self.pending[token.mint] = token
        return None

    def _promote(self, token: Token, now: float) -> Token | None:
        """Check a matured token and take it out of the buffer if decided."""
        ok, reason = passes_filter(token, self.filter_cfg, now)
        if ok:
            self._forget(token.mint)
            self._emitted.add(token.mint)
            return token
        # too_young may still mature; everything else is final. In
        # particular data_unavailable never resolves: no trade stream
        # exists that could supply the missing evidence.
        if reason in ("too_young", "few_buyers"):
            return None
        self._forget(token.mint)
        self._emitted.add(token.mint)
        if self.on_skip:
            self.on_skip(token, reason)
        return None

    def sweep(self, now: float) -> list[Token]:
        """Walk the buffer: matured tokens out, stale ones gone."""
        ready: list[Token] = []
        for mint in list(self.pending):
            token = self.pending[mint]
            promoted = self._promote(token, now)
            if promoted is not None:
                ready.append(promoted)
            elif now - token.created_timestamp > PENDING_TTL_SECONDS:
                self._forget(mint)
                self._emitted.add(mint)
                if self.on_skip:
                    self.on_skip(token, "stale_no_traction")
        return ready

    def _forget(self, mint: str) -> None:
        self.pending.pop(mint, None)

    def _evict_if_crowded(self) -> None:
        """Buffer over full: drop the oldest unmatured launches."""
        while len(self.pending) >= MAX_PENDING:
            oldest = min(self.pending, key=lambda mint: self.pending[mint].created_timestamp)
            token = self.pending[oldest]
            self._forget(oldest)
            self._emitted.add(oldest)
            if self.on_skip:
                self.on_skip(token, "buffer_overflow")

    # -- socket ------------------------------------------------------------

    async def stream(self) -> AsyncIterator[Token]:
        """Endless stream of filtered tokens. Reconnects on its own."""
        sweeper_delay = 10.0
        backoff = 1.0
        while True:
            try:
                async with connect(
                    self.data.ws_url, proxy=None, max_queue=self.data.ws_max_queue
                ) as ws:
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    log.info("monitor connected to %s", self.data.ws_url)
                    backoff = 1.0
                    last_sweep = self.clock.now()
                    while True:
                        try:
                            async with self.clock.timeout(sweeper_delay):
                                raw = await ws.recv()
                        except TimeoutError:
                            raw = None
                        if raw:
                            try:
                                payload = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(payload, dict):
                                token = self.handle_event(payload, self.clock.now())
                                if token is not None:
                                    yield token
                        if self.clock.now() - last_sweep >= sweeper_delay:
                            last_sweep = self.clock.now()
                            for token in self.sweep(self.clock.now()):
                                yield token
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # dropped socket: wait and reconnect
                log.warning("monitor dropped (%s), reconnecting in %.0fs", exc, backoff)
                with contextlib.suppress(asyncio.CancelledError):
                    await self.clock.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
