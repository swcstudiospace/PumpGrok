"""Риск-менеджер: пять ограничителей и размер позиции.

Последний гейт перед исполнением, и единственный, который не спрашивает
Grok ни о чём. Все пороги — из конфига:

1. потолок SOL на сделку
2. дневной лимит убытка (достигнут — пайплайн стоит до следующего дня)
3. максимум сделок в день
4. максимум одновременно открытых позиций
5. стоп-лосс в процентах, мониторится фоновой задачей

Размер позиции пропорционален скорингу, но не выше потолка и не больше
30% остатка дневного лимита убытка.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from pydantic import BaseModel

from .models import Config, Position, RiskConfig, TradeDecision
from .state import PipelineState, StateStore, describe

log = logging.getLogger(__name__)

# Доля остатка дневного лимита, которой можно рискнуть в одной сделке.
MAX_SHARE_OF_REMAINING_BUDGET = 0.30

# Меньше этого объёма сделка не имеет смысла: съедят комиссии и чаевые.
MIN_TRADE_SOL = 0.01


class RiskManager:
    """Состояние дня, открытые позиции и решение о размере."""

    def __init__(
        self,
        config: Config,
        clock: Callable[[], float] = time.time,
        store: StateStore | None = None,
    ) -> None:
        self.config = config
        self.risk: RiskConfig = config.risk
        self.clock = clock
        self.store = store
        self.day = self._today()
        self.trades_today = 0
        self.realized_pnl_sol = 0.0          # отрицательное = убыток
        self.positions: dict[str, Position] = {}
        self.grok_calls_today = 0

    # -- состояние на диске ------------------------------------------------

    def restore(self) -> bool:
        """Поднять состояние с диска. True, если что-то восстановлено.

        Позиции восстанавливаются всегда: они реально открыты на цепочке,
        сколько бы времени ни прошло. Счётчики дня — только если файл от
        сегодняшних суток: чужой день своих лимитов нам не диктует.
        """
        if self.store is None:
            return False
        state = self.store.load()
        if state is None:
            return False

        self.positions = dict(state.positions)
        if state.day == self.day:
            self.trades_today = state.trades_today
            self.realized_pnl_sol = state.realized_pnl_sol
            self.grok_calls_today = state.grok_calls_today
        else:
            log.info("состояние от %s, сегодня %s — счётчики дня начинаем заново",
                     state.day or "?", self.day)
        log.info("состояние восстановлено: %s", describe(state))
        if self.halted:
            log.warning("после восстановления дневной лимит убытка уже выбран — "
                        "торговли сегодня не будет")
        return True

    def persist(self) -> None:
        """Сохранить состояние. Вызывается после каждого изменения денег."""
        if self.store is None:
            return
        self.store.save(
            PipelineState(
                day=self.day,
                trades_today=self.trades_today,
                realized_pnl_sol=self.realized_pnl_sol,
                grok_calls_today=self.grok_calls_today,
                positions=self.positions,
            )
        )

    # -- сутки -------------------------------------------------------------

    def _today(self) -> str:
        return datetime.fromtimestamp(self.clock(), tz=UTC).strftime("%Y-%m-%d")

    def roll_day_if_needed(self) -> bool:
        """Новые сутки — обнулить счётчики. Открытые позиции не трогаем."""
        today = self._today()
        if today != self.day:
            log.info("новые сутки %s: счётчики сброшены (было сделок %d, PnL %.4f)",
                     today, self.trades_today, self.realized_pnl_sol)
            self.day = today
            self.trades_today = 0
            self.realized_pnl_sol = 0.0
            self.grok_calls_today = 0
            self.persist()
            return True
        return False

    # -- состояние ---------------------------------------------------------

    @property
    def daily_loss(self) -> float:
        """Убыток за сутки положительным числом. Прибыль -> 0."""
        return max(0.0, -self.realized_pnl_sol)

    @property
    def remaining_loss_budget(self) -> float:
        return max(0.0, self.risk.daily_loss_limit_sol - self.daily_loss)

    @property
    def halted(self) -> bool:
        """Дневной лимит убытка выбран — до конца суток не торгуем."""
        self.roll_day_if_needed()
        return self.daily_loss >= self.risk.daily_loss_limit_sol

    @property
    def open_count(self) -> int:
        return len(self.positions)

    # -- решение -----------------------------------------------------------

    def position_size(self, score: float) -> float:
        """Размер позиции: пропорционален скорингу, ограничен сверху дважды."""
        by_score = self.risk.max_sol_per_trade * max(0.0, min(1.0, score))
        by_budget = self.remaining_loss_budget * MAX_SHARE_OF_REMAINING_BUDGET
        return round(min(by_score, by_budget), 6)

    def evaluate(self, mint: str, score: float) -> TradeDecision:
        """Пропустить сделку или нет, и на какую сумму."""
        self.roll_day_if_needed()

        if self.halted:
            return TradeDecision(
                approved=False,
                reason=f"daily_loss_limit_hit ({self.daily_loss:.4f} SOL)",
            )
        if self.trades_today >= self.risk.max_trades_per_day:
            return TradeDecision(
                approved=False,
                reason=f"max_trades_per_day ({self.trades_today}/{self.risk.max_trades_per_day})",
            )
        if self.open_count >= self.risk.max_open_positions:
            return TradeDecision(
                approved=False,
                reason=f"max_open_positions ({self.open_count}/{self.risk.max_open_positions})",
            )
        if mint in self.positions:
            return TradeDecision(approved=False, reason="already_open")

        size = self.position_size(score)
        if size < MIN_TRADE_SOL:
            return TradeDecision(
                approved=False,
                reason=f"size_too_small ({size:.6f} SOL)",
                size_sol=size,
            )
        return TradeDecision(approved=True, size_sol=size, reason="ok")

    # -- учёт --------------------------------------------------------------

    def register_open(self, position: Position) -> None:
        self.roll_day_if_needed()
        self.positions[position.mint] = position
        self.trades_today += 1
        self.persist()

    def register_close(self, mint: str, pnl_sol: float) -> Position | None:
        position = self.positions.pop(mint, None)
        self.realized_pnl_sol += pnl_sol
        self.persist()
        if self.halted:
            log.warning("дневной лимит убытка выбран, торговля остановлена до %s",
                        "следующих суток UTC")
        return position

    def snapshot(self) -> dict[str, float | int | str]:
        return {
            "day": self.day,
            "trades_today": self.trades_today,
            "open_positions": self.open_count,
            "realized_pnl_sol": round(self.realized_pnl_sol, 6),
            "remaining_loss_budget": round(self.remaining_loss_budget, 6),
            "halted": self.halted,
            "grok_calls_today": self.grok_calls_today,
        }


# --------------------------------------------------------------------------
# Выходы из позиции
# --------------------------------------------------------------------------

# Порядок правил — это порядок приоритета. Сначала спасаем деньги, потом
# забираем прибыль, потом бережём прибыль, и только потом закрываем по
# времени: позиция, которая едет вверх, не должна закрыться по таймеру.
EXIT_REASONS = ("stop_loss", "take_profit", "trailing_stop", "max_hold")


class ExitSignal(BaseModel):
    """Причина закрыть позицию и то, чем она обоснована."""

    reason: str
    detail: str = ""


def pnl_pct(position: Position, price: float) -> float:
    if position.entry_price <= 0:
        return 0.0
    return (price - position.entry_price) / position.entry_price * 100.0


def stop_loss_triggered(position: Position, price: float, stop_loss_pct: float) -> bool:
    if position.entry_price <= 0 or price <= 0 or stop_loss_pct <= 0:
        return False
    return -pnl_pct(position, price) >= stop_loss_pct


def exit_signal(
    position: Position,
    price: float,
    risk: RiskConfig,
    now: float | None = None,
) -> ExitSignal | None:
    """Пора ли выходить и почему. None — держим дальше.

    Стоп-лосс здесь только одно из четырёх правил. Без остальных позиция,
    выросшая втрое, не имеет ни одного способа закрыться в плюс — она
    просто ждёт, пока откатится обратно к стопу.
    """
    if price <= 0 or position.entry_price <= 0:
        return None

    change = pnl_pct(position, price)

    if risk.stop_loss_pct and -change >= risk.stop_loss_pct:
        return ExitSignal(reason="stop_loss", detail=f"{change:+.1f}% от входа")

    if risk.take_profit_pct and change >= risk.take_profit_pct:
        return ExitSignal(reason="take_profit", detail=f"{change:+.1f}% от входа")

    # Трейлинг работает только выше входа: ниже за позицию отвечает стоп-лосс,
    # иначе два правила спорили бы за одну и ту же просадку.
    peak = max(position.peak_price, price)
    if risk.trailing_stop_pct and peak > position.entry_price:
        drawdown = (peak - price) / peak * 100.0
        if drawdown >= risk.trailing_stop_pct:
            return ExitSignal(
                reason="trailing_stop",
                detail=f"откат {drawdown:.1f}% от пика {pnl_pct(position, peak):+.1f}%",
            )

    if risk.max_hold_seconds and position.opened_at:
        held = (now or time.time()) - position.opened_at
        if held >= risk.max_hold_seconds:
            return ExitSignal(
                reason="max_hold",
                detail=f"{held / 60:.0f} мин в позиции, {change:+.1f}%",
            )

    return None


class PositionWatcher:
    """Фоновая задача: опрашивает цены открытых позиций и зовёт продажу.

    Цена и продажа приходят снаружи колбэками — сюда не тянется ни RPC, ни
    executor, поэтому это тестируется без сети.
    """

    # Насколько должен подрасти пик, чтобы записать его на диск. Каждый
    # тик писать состояние незачем, а потерять пик при рестарте — значит
    # заново начать трейлинг от текущей цены.
    PEAK_PERSIST_STEP = 1.01

    # Столько проходов подряд без котировки — и позиция считается слепой:
    # правила выхода по ней не работают, а молчать об этом нельзя.
    BLIND_AFTER = 3

    def __init__(
        self,
        manager: RiskManager,
        price_fn: Callable[[str], Awaitable[float]],
        sell_fn: Callable[[Position, float, str], Awaitable[None]],
    ) -> None:
        self.manager = manager
        self.price_fn = price_fn
        self.sell_fn = sell_fn
        self.price_failures: dict[str, int] = {}
        self._task: asyncio.Task | None = None

    @property
    def blind(self) -> list[str]:
        """Позиции, по которым давно нет цены. Выходы по ним не работают."""
        return [mint for mint, misses in self.price_failures.items()
                if misses >= self.BLIND_AFTER and mint in self.manager.positions]

    async def check_once(self) -> list[str]:
        """Один проход по открытым позициям. Возвращает закрытые минты."""
        triggered: list[str] = []
        persist_needed = False

        for position in list(self.manager.positions.values()):
            try:
                price = await self.price_fn(position.mint)
            except Exception as exc:
                log.warning("цена для %s недоступна: %s", position.mint, exc)
                price = 0.0
            if price <= 0:
                self._miss(position.mint)
                continue
            self.price_failures.pop(position.mint, None)

            if price > position.peak_price:
                persist_needed = persist_needed or (
                    price >= position.peak_price * self.PEAK_PERSIST_STEP
                )
                position.peak_price = price

            signal = exit_signal(position, price, self.manager.risk)
            if signal is None:
                continue

            log.info("выход из %s по правилу %s (%s): вход %.12f, сейчас %.12f",
                     position.mint[:8], signal.reason, signal.detail,
                     position.entry_price, price)
            await self.sell_fn(position, price, signal.reason)
            triggered.append(position.mint)
            persist_needed = False        # продажа сохранит состояние сама

        if persist_needed:
            self.manager.persist()
        return triggered

    def _miss(self, mint: str) -> None:
        """Учесть проход без котировки и сказать вслух, когда их слишком много."""
        misses = self.price_failures.get(mint, 0) + 1
        self.price_failures[mint] = misses
        if misses == self.BLIND_AFTER:
            log.error("позиция %s без цены %d проходов подряд — правила выхода "
                      "по ней сейчас не работают", mint[:8], misses)

    async def run(self) -> None:
        interval = self.manager.risk.stop_loss_poll_seconds
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("присмотр за позициями упал на проходе: %s", exc)
            await asyncio.sleep(interval)

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self.run(), name="position-watcher")
        return self._task

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
