"""WebSocket-монитор новых лончей pump.fun.

Первая ступень пайплайна и самая грубая: фильтрует кодом, без LLM, и
отсеивает порядка 94% потока. Всё, что сюда не пролезло, дальше не идёт и
токенов Grok не тратит.

Свежесозданный токен не может пройти фильтр по возрасту, поэтому лончи
кладутся в буфер `pending`, накапливают сделки из того же сокета и
проверяются повторно, когда дорастут до `min_age_seconds`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from .models import Config, FilterConfig, Token

log = logging.getLogger(__name__)

# Кривая pump.fun считается заполненной примерно на 85 SOL в резерве.
CURVE_COMPLETION_SOL = 85.0

# Сколько держать лонч в буфере, если он так и не набрал покупателей.
PENDING_TTL_SECONDS = 900.0

# Потолки памяти. Процесс живёт сутками, а лончей на pump.fun тысячи в час:
# без ограничения и буфер, и список уже виденных растут без конца.
MAX_PENDING = 2_000
MAX_REMEMBERED = 20_000


class SeenSet:
    """Множество последних N ключей. Старые вытесняются, память не течёт."""

    def __init__(self, maxlen: int = MAX_REMEMBERED) -> None:
        self.maxlen = maxlen
        self._items: OrderedDict[str, None] = OrderedDict()

    def add(self, key: str) -> None:
        self._items[key] = None
        self._items.move_to_end(key)
        while len(self._items) > self.maxlen:
            self._items.popitem(last=False)

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)


def parse_create_event(payload: dict[str, Any]) -> Token | None:
    """Событие создания токена -> Token. None, если событие не про создание."""
    if payload.get("txType") not in ("create", "created"):
        return None
    mint = payload.get("mint") or payload.get("mintAddress")
    if not mint:
        return None

    sol_in_curve = float(payload.get("vSolInBondingCurve") or 0.0)
    created = payload.get("timestamp") or payload.get("createdTimestamp")
    created_ts = (
        float(created) / 1000.0
        if created and float(created) > 1e11
        else float(created or time.time())
    )

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
        market_cap_sol=float(payload.get("marketCapSol") or 0.0),
        curve_progress=min(1.0, sol_in_curve / CURVE_COMPLETION_SOL),
    )


def passes_filter(token: Token, cfg: FilterConfig) -> tuple[bool, str]:
    """Базовый фильтр. Возвращает (прошёл, причина отказа или "ok").

    Причина возвращается всегда — она уходит в лог как `skip.reason`, иначе
    потом не понять, на чём именно осыпался поток.
    """
    # Сначала окончательные приговоры (метаданные, переполненная кривая),
    # потом временные — токен с ними ещё может дозреть в буфере монитора.
    if cfg.require_metadata and not token.has_metadata:
        return False, "no_metadata"
    if token.curve_progress >= cfg.max_curve_progress:
        return False, "curve_too_full"
    if token.age_seconds < cfg.min_age_seconds:
        return False, "too_young"
    if token.unique_buyers < cfg.min_unique_buyers:
        return False, "few_buyers"
    return True, "ok"


class LaunchMonitor:
    """Подписка на новые токены и их сделки с фильтрацией на лету."""

    def __init__(
        self,
        config: Config,
        on_skip: Callable[[Token, str], None] | None = None,
    ) -> None:
        self.config = config
        self.filter = config.filter
        self.on_skip = on_skip
        self.pending: dict[str, Token] = {}
        self._buyers: dict[str, set[str]] = {}
        self._emitted = SeenSet()

    # -- обработка событий -------------------------------------------------

    def handle_event(self, payload: dict[str, Any]) -> Token | None:
        """Одно сообщение из сокета. Возвращает токен, если он готов идти дальше."""
        tx_type = payload.get("txType")

        if tx_type in ("create", "created"):
            token = parse_create_event(payload)
            if token and token.mint not in self._emitted:
                self._evict_if_crowded()
                self.pending[token.mint] = token
                # Создателя в покупатели не записываем: нужен счётчик
                # посторонних кошельков, а не всех подряд.
                self._buyers[token.mint] = set()
            return None

        mint = payload.get("mint")
        if not mint or mint not in self.pending:
            return None

        token = self.pending[mint]
        wallet = payload.get("traderPublicKey") or payload.get("wallet")
        if tx_type == "buy" and wallet:
            self._buyers[mint].add(wallet)
        token.unique_buyers = len(self._buyers[mint])

        sol_in_curve = payload.get("vSolInBondingCurve")
        if sol_in_curve is not None:
            token.sol_in_curve = float(sol_in_curve)
            token.curve_progress = min(1.0, token.sol_in_curve / CURVE_COMPLETION_SOL)
        if payload.get("marketCapSol") is not None:
            token.market_cap_sol = float(payload["marketCapSol"])

        return self._promote(token)

    def _promote(self, token: Token) -> Token | None:
        """Проверить дозревший токен и вынуть его из буфера, если решение принято."""
        ok, reason = passes_filter(token, self.filter)
        if ok:
            self._forget(token.mint)
            self._emitted.add(token.mint)
            return token
        # too_young / few_buyers — ещё может дозреть, остальное окончательно
        if reason in ("too_young", "few_buyers"):
            return None
        self._forget(token.mint)
        self._emitted.add(token.mint)
        if self.on_skip:
            self.on_skip(token, reason)
        return None

    def sweep(self, now: float | None = None) -> list[Token]:
        """Пройтись по буферу: дозревшие — наружу, протухшие — вон."""
        now = now or time.time()
        ready: list[Token] = []
        for mint in list(self.pending):
            token = self.pending[mint]
            promoted = self._promote(token)
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
        self._buyers.pop(mint, None)

    def _evict_if_crowded(self) -> None:
        """Буфер переполнен — выкидываем самые старые недозревшие лончи."""
        while len(self.pending) >= MAX_PENDING:
            oldest = min(self.pending, key=lambda mint: self.pending[mint].created_timestamp)
            token = self.pending[oldest]
            self._forget(oldest)
            self._emitted.add(oldest)
            if self.on_skip:
                self.on_skip(token, "buffer_overflow")

    # -- сокет -------------------------------------------------------------

    async def stream(self) -> AsyncIterator[Token]:
        """Бесконечный поток отфильтрованных токенов. Переподключается сам."""
        sweeper_delay = 10.0
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(self.config.data.ws_url) as ws:
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    log.info("монитор подключён к %s", self.config.data.ws_url)
                    backoff = 1.0
                    last_sweep = time.time()
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=sweeper_delay)
                        except TimeoutError:
                            raw = None
                        if raw:
                            try:
                                payload = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(payload, dict):
                                token = self.handle_event(payload)
                                if token is not None:
                                    await self._subscribe_trades(ws, token.mint, off=True)
                                    yield token
                                elif payload.get("txType") in ("create", "created"):
                                    mint = payload.get("mint")
                                    if mint:
                                        await self._subscribe_trades(ws, mint)
                        if time.time() - last_sweep >= sweeper_delay:
                            last_sweep = time.time()
                            for token in self.sweep():
                                yield token
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # обрыв сокета — ждём и переподключаемся
                log.warning("монитор отвалился (%s), переподключение через %.0fs", exc, backoff)
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    @staticmethod
    async def _subscribe_trades(ws: Any, mint: str, off: bool = False) -> None:
        method = "unsubscribeTokenTrade" if off else "subscribeTokenTrade"
        with contextlib.suppress(Exception):
            await ws.send(json.dumps({"method": method, "keys": [mint]}))
