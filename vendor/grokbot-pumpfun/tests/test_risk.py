"""Риск-менеджер: срабатывание всех пяти лимитов, размер позиции у границы
дневного бюджета и сброс суток."""

import pytest

from src.models import Config, Position, RiskConfig
from src.risk import (
    MAX_SHARE_OF_REMAINING_BUDGET,
    PositionWatcher,
    RiskManager,
    exit_signal,
    stop_loss_triggered,
)


class FakeClock:
    """Управляемое время: сутки переключаем руками, а не ждём полуночи."""

    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance_days(self, days: int = 1) -> None:
        self.now += days * 86_400


@pytest.fixture
def config() -> Config:
    cfg = Config()
    cfg.risk = RiskConfig(
        max_sol_per_trade=0.5,
        daily_loss_limit_sol=2.0,
        max_trades_per_day=3,
        max_open_positions=2,
        stop_loss_pct=30.0,
    )
    return cfg


@pytest.fixture
def manager(config) -> RiskManager:
    return RiskManager(config, clock=FakeClock())


def position(mint: str = "M", entry: float = 1.0, sol: float = 0.5,
             peak: float | None = None, opened_at: float = 0.0) -> Position:
    return Position(mint=mint, entry_price=entry, sol_spent=sol, opened_at=opened_at,
                    peak_price=entry if peak is None else peak)


# --- размер позиции -------------------------------------------------------


def test_size_is_proportional_to_score(manager):
    assert manager.position_size(1.0) == pytest.approx(0.5)
    assert manager.position_size(0.7) == pytest.approx(0.35)
    assert manager.position_size(0.0) == pytest.approx(0.0)


def test_size_capped_by_max_sol_per_trade(manager):
    """Скоринг выше единицы не увеличивает ставку."""
    assert manager.position_size(3.0) == pytest.approx(0.5)


def test_size_shrinks_near_daily_limit(manager):
    """Осталось 0.4 SOL бюджета -> в сделку идёт не больше 30% от них."""
    manager.realized_pnl_sol = -1.6
    assert manager.remaining_loss_budget == pytest.approx(0.4)
    expected = 0.4 * MAX_SHARE_OF_REMAINING_BUDGET
    assert manager.position_size(1.0) == pytest.approx(expected)
    assert expected < manager.risk.max_sol_per_trade


def test_tiny_remaining_budget_rejects_trade(manager):
    manager.realized_pnl_sol = -1.99
    decision = manager.evaluate("M", score=0.9)
    assert not decision.approved
    assert decision.reason.startswith("size_too_small")


def test_profit_does_not_inflate_budget(manager):
    """Прибыль не расширяет дневной лимит убытка сверх конфига."""
    manager.realized_pnl_sol = +5.0
    assert manager.remaining_loss_budget == pytest.approx(2.0)
    assert manager.position_size(1.0) == pytest.approx(0.5)


# --- лимиты ---------------------------------------------------------------


def test_healthy_trade_approved(manager):
    decision = manager.evaluate("M", score=0.8)
    assert decision.approved
    assert decision.size_sol == pytest.approx(0.4)


def test_daily_loss_limit_halts_trading(manager):
    manager.register_close("X", pnl_sol=-2.0)
    assert manager.halted
    decision = manager.evaluate("M", score=1.0)
    assert not decision.approved
    assert decision.reason.startswith("daily_loss_limit_hit")


def test_daily_loss_limit_boundary(manager):
    """Ровно лимит — уже стоп; на волосок меньше — ещё торгуем."""
    manager.realized_pnl_sol = -1.999
    assert not manager.halted
    manager.realized_pnl_sol = -2.0
    assert manager.halted


def test_max_trades_per_day(manager):
    for i in range(3):
        assert manager.evaluate(f"M{i}", 0.9).approved
        manager.register_open(position(f"M{i}"))
        manager.register_close(f"M{i}", pnl_sol=0.0)
    decision = manager.evaluate("M9", 0.9)
    assert not decision.approved
    assert decision.reason.startswith("max_trades_per_day")


def test_max_open_positions(manager):
    manager.register_open(position("A"))
    manager.register_open(position("B"))
    decision = manager.evaluate("C", 0.9)
    assert not decision.approved
    assert decision.reason.startswith("max_open_positions")


def test_freed_slot_allows_new_trade(manager):
    manager.register_open(position("A"))
    manager.register_open(position("B"))
    assert not manager.evaluate("C", 0.9).approved
    manager.register_close("A", pnl_sol=0.1)
    assert manager.evaluate("C", 0.9).approved


def test_no_double_position_in_same_mint(manager):
    manager.register_open(position("A"))
    decision = manager.evaluate("A", 0.9)
    assert not decision.approved
    assert decision.reason == "already_open"


# --- сутки ----------------------------------------------------------------


def test_new_day_resets_counters_and_unhalts(config):
    clock = FakeClock()
    manager = RiskManager(config, clock=clock)
    manager.register_open(position("A"))
    manager.register_close("A", pnl_sol=-2.5)
    assert manager.halted

    clock.advance_days(1)
    assert manager.roll_day_if_needed()
    assert not manager.halted
    assert manager.trades_today == 0
    assert manager.realized_pnl_sol == 0.0
    assert manager.evaluate("B", 0.9).approved


def test_day_roll_keeps_open_positions(config):
    clock = FakeClock()
    manager = RiskManager(config, clock=clock)
    manager.register_open(position("A"))
    clock.advance_days(1)
    manager.roll_day_if_needed()
    assert "A" in manager.positions


def test_same_day_does_not_reset(manager):
    manager.register_open(position("A"))
    assert not manager.roll_day_if_needed()
    assert manager.trades_today == 1


# --- стоп-лосс ------------------------------------------------------------


def test_stop_loss_boundary():
    pos = position(entry=1.0)
    assert stop_loss_triggered(pos, price=0.70, stop_loss_pct=30.0)
    assert not stop_loss_triggered(pos, price=0.71, stop_loss_pct=30.0)


def test_stop_loss_ignores_missing_price():
    pos = position(entry=1.0)
    assert not stop_loss_triggered(pos, price=0.0, stop_loss_pct=30.0)
    assert not stop_loss_triggered(position(entry=0.0), price=0.5, stop_loss_pct=30.0)


async def test_watcher_sells_only_dumped_positions(manager):
    manager.register_open(position("DUMP", entry=1.0))
    manager.register_open(position("FINE", entry=1.0))
    prices = {"DUMP": 0.5, "FINE": 0.95}
    sold: list[tuple[str, str]] = []

    async def price_fn(mint: str) -> float:
        return prices[mint]

    async def sell_fn(pos, price, reason) -> None:
        sold.append((pos.mint, reason))
        manager.register_close(pos.mint, pnl_sol=-0.25)

    watcher = PositionWatcher(manager, price_fn, sell_fn)
    assert await watcher.check_once() == ["DUMP"]
    assert sold == [("DUMP", "stop_loss")]
    assert "FINE" in manager.positions


async def test_watcher_survives_price_errors(manager):
    manager.register_open(position("A", entry=1.0))

    async def price_fn(mint: str) -> float:
        raise RuntimeError("RPC лёг")

    async def sell_fn(pos, price, reason) -> None:  # pragma: no cover - не должен вызваться
        raise AssertionError("продажа без цены")

    watcher = PositionWatcher(manager, price_fn, sell_fn)
    assert await watcher.check_once() == []
    assert "A" in manager.positions


# --- выходы вверх и по времени -------------------------------------------


@pytest.fixture
def exits(config) -> RiskConfig:
    config.risk.stop_loss_pct = 30.0
    config.risk.take_profit_pct = 120.0
    config.risk.trailing_stop_pct = 35.0
    config.risk.max_hold_seconds = 3600.0
    return config.risk


def test_holds_while_nothing_triggered(exits):
    assert exit_signal(position(entry=1.0, opened_at=1000.0), 1.5, exits, now=1100.0) is None


def test_take_profit_fires(exits):
    signal = exit_signal(position(entry=1.0, opened_at=1000.0), 2.2, exits, now=1100.0)
    assert signal is not None and signal.reason == "take_profit"
    assert "+120" in signal.detail


def test_take_profit_boundary(exits):
    assert exit_signal(position(entry=1.0), 2.2, exits, now=1.0).reason == "take_profit"
    assert exit_signal(position(entry=1.0), 2.19, exits, now=1.0) is None


def test_stop_loss_wins_over_everything(exits):
    """Просадка ниже стопа закрывает позицию, даже если она была в плюсе."""
    signal = exit_signal(position(entry=1.0, peak=3.0, opened_at=0.0), 0.6, exits, now=1.0)
    assert signal.reason == "stop_loss"


def test_trailing_stop_fires_after_peak(exits):
    pos = position(entry=1.0, peak=2.0, opened_at=1000.0)
    assert exit_signal(pos, 1.4, exits, now=1100.0) is None          # откат 30%
    signal = exit_signal(pos, 1.29, exits, now=1100.0)               # откат 35.5%
    assert signal is not None and signal.reason == "trailing_stop"
    assert "от пика" in signal.detail


def test_trailing_ignores_price_below_entry(exits):
    """Ниже входа за позицию отвечает стоп-лосс, а не трейлинг."""
    signal = exit_signal(position(entry=1.0, peak=1.0, opened_at=1000.0), 0.8, exits, now=1100.0)
    assert signal is None


def test_trailing_uses_live_price_as_peak(exits):
    """Пик обновляется прямо в проверке: рывок вверх и обратно не теряется."""
    pos = position(entry=1.0, peak=1.0)
    assert exit_signal(pos, 2.19, exits, now=1.0) is None            # ещё не take-profit
    assert pos.peak_price == 1.0                                     # сама функция не пишет
    pos.peak_price = 2.19
    assert exit_signal(pos, 1.4, exits, now=1.0).reason == "trailing_stop"


def test_max_hold_closes_stale_position(exits):
    pos = position(entry=1.0, opened_at=1000.0)
    assert exit_signal(pos, 1.05, exits, now=1000.0 + 3599) is None
    signal = exit_signal(pos, 1.05, exits, now=1000.0 + 3601)
    assert signal is not None and signal.reason == "max_hold"


def test_max_hold_does_not_cut_a_runner(exits):
    """Позиция, которая едет вверх, закроется по take-profit, а не по таймеру."""
    pos = position(entry=1.0, peak=2.5, opened_at=1000.0)
    signal = exit_signal(pos, 2.5, exits, now=1000.0 + 99_999)
    assert signal.reason == "take_profit"


def test_zero_disables_each_rule(exits):
    exits.take_profit_pct = 0.0
    exits.trailing_stop_pct = 0.0
    exits.max_hold_seconds = 0.0
    pos = position(entry=1.0, peak=5.0, opened_at=1.0)
    assert exit_signal(pos, 4.0, exits, now=10**9) is None
    assert exit_signal(pos, 0.5, exits, now=10**9).reason == "stop_loss"


def test_no_signal_without_price(exits):
    assert exit_signal(position(entry=1.0), 0.0, exits, now=1.0) is None
    assert exit_signal(position(entry=0.0), 1.0, exits, now=1.0) is None


async def test_watcher_tracks_peak_and_persists(config, tmp_path):
    from src.state import StateStore

    store = StateStore(tmp_path / "state.json")
    manager = RiskManager(config, clock=FakeClock(), store=store)
    manager.risk.take_profit_pct = 0.0
    manager.risk.trailing_stop_pct = 0.0
    manager.register_open(position("A", entry=1.0))

    prices = iter([1.5, 2.0])

    async def price_fn(mint: str) -> float:
        return next(prices)

    async def sell_fn(pos, price, reason) -> None:  # pragma: no cover
        raise AssertionError("выхода быть не должно")

    watcher = PositionWatcher(manager, price_fn, sell_fn)
    await watcher.check_once()
    await watcher.check_once()

    assert manager.positions["A"].peak_price == 2.0
    saved = store.load()
    assert saved.positions["A"].peak_price >= 1.5      # пик пережил бы рестарт


async def test_watcher_reports_exit_reason(config):
    manager = RiskManager(config, clock=FakeClock())
    manager.risk.take_profit_pct = 50.0
    manager.register_open(position("A", entry=1.0))
    seen: list[str] = []

    async def price_fn(mint: str) -> float:
        return 1.6

    async def sell_fn(pos, price, reason) -> None:
        seen.append(reason)
        manager.register_close(pos.mint, pnl_sol=0.3)

    watcher = PositionWatcher(manager, price_fn, sell_fn)
    assert await watcher.check_once() == ["A"]
    assert seen == ["take_profit"]


# --- позиция без котировок ------------------------------------------------


async def test_position_without_price_is_reported_blind(manager):
    manager.register_open(position("A", entry=1.0))

    async def price_fn(mint: str) -> float:
        raise RuntimeError("провайдер лёг")

    async def sell_fn(pos, price, reason) -> None:  # pragma: no cover
        raise AssertionError("продажа без цены")

    watcher = PositionWatcher(manager, price_fn, sell_fn)
    for _ in range(watcher.BLIND_AFTER - 1):
        await watcher.check_once()
    assert watcher.blind == []                # ещё терпим

    await watcher.check_once()
    assert watcher.blind == ["A"]             # а вот теперь молчать нельзя


async def test_zero_price_counts_as_missing(manager):
    manager.register_open(position("A", entry=1.0))

    async def price_fn(mint: str) -> float:
        return 0.0

    async def sell_fn(pos, price, reason) -> None:  # pragma: no cover
        raise AssertionError("продажа по нулевой цене")

    watcher = PositionWatcher(manager, price_fn, sell_fn)
    for _ in range(watcher.BLIND_AFTER):
        await watcher.check_once()
    assert watcher.blind == ["A"]


async def test_recovered_price_clears_blindness(manager):
    manager.register_open(position("A", entry=1.0))
    prices = [0.0, 0.0, 0.0, 1.05]

    async def price_fn(mint: str) -> float:
        return prices.pop(0)

    async def sell_fn(pos, price, reason) -> None:  # pragma: no cover
        raise AssertionError("выхода быть не должно")

    watcher = PositionWatcher(manager, price_fn, sell_fn)
    for _ in range(4):
        await watcher.check_once()
    assert watcher.blind == []
    assert "A" not in watcher.price_failures


async def test_closed_position_is_not_blind(manager):
    manager.register_open(position("A", entry=1.0))

    async def price_fn(mint: str) -> float:
        return 0.0

    async def sell_fn(pos, price, reason) -> None:  # pragma: no cover
        raise AssertionError("не должно вызваться")

    watcher = PositionWatcher(manager, price_fn, sell_fn)
    for _ in range(watcher.BLIND_AFTER):
        await watcher.check_once()
    manager.register_close("A", pnl_sol=0.0)
    assert watcher.blind == []
