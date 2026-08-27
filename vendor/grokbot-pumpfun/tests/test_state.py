"""Состояние, переживающее рестарт.

Главное здесь — что процесс, поднятый заново, помнит открытые позиции и
дневные лимиты. Без этого рестарт обнуляет оба ограничителя.
"""

import json

import pytest

from src.models import Config, Position, RiskConfig
from src.risk import RiskManager
from src.state import PipelineState, StateStore, describe


class FakeClock:
    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance_days(self, days: int = 1) -> None:
        self.now += days * 86_400


@pytest.fixture
def config() -> Config:
    cfg = Config()
    cfg.risk = RiskConfig(max_sol_per_trade=0.5, daily_loss_limit_sol=2.0,
                          max_trades_per_day=5, max_open_positions=3)
    return cfg


@pytest.fixture
def store(tmp_path) -> StateStore:
    return StateStore(tmp_path / "state" / "pipeline.json")


def position(mint: str = "M", sol: float = 0.4) -> Position:
    return Position(mint=mint, symbol="S", entry_price=1e-7, sol_spent=sol,
                    token_amount=1000.0, opened_at=1.0, tx_hash="dry_run", score=0.8)


# --- хранилище ------------------------------------------------------------


def test_missing_file_is_not_an_error(store):
    assert store.load() is None


def test_save_and_load_roundtrip(store):
    state = PipelineState(day="2026-08-26", trades_today=2, realized_pnl_sol=-0.5,
                          grok_calls_today=17, positions={"M": position("M")})
    store.save(state)
    loaded = store.load()
    assert loaded is not None
    assert loaded.trades_today == 2
    assert loaded.realized_pnl_sol == -0.5
    assert loaded.grok_calls_today == 17
    assert loaded.positions["M"].sol_spent == 0.4
    assert loaded.updated_at > 0


def test_save_creates_parent_directory(tmp_path):
    store = StateStore(tmp_path / "глубоко" / "внутри" / "state.json")
    store.save(PipelineState(day="2026-08-26"))
    assert store.path.exists()


def test_save_leaves_no_temp_files(store):
    store.save(PipelineState(day="2026-08-26"))
    store.save(PipelineState(day="2026-08-27"))
    leftovers = [p.name for p in store.path.parent.iterdir() if ".tmp" in p.name]
    assert leftovers == []


def test_corrupt_file_is_set_aside_not_crashed(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{это не json")
    assert store.load() is None
    assert store.path.with_suffix(".json.corrupt").exists()


def test_wrong_shape_is_handled_like_corruption(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"positions": "не словарь"}))
    assert store.load() is None


def test_clear_removes_file(store):
    store.save(PipelineState(day="2026-08-26"))
    store.clear()
    assert not store.path.exists()
    store.clear()      # повторно — не падает


def test_describe_is_readable():
    text = describe(PipelineState(day="2026-08-26", trades_today=3,
                                  realized_pnl_sol=-0.25, positions={"M": position()}))
    assert "2026-08-26" in text and "открытых позиций 1" in text


# --- восстановление риск-менеджера ---------------------------------------


def test_restart_remembers_open_positions(config, store):
    first = RiskManager(config, clock=FakeClock(), store=store)
    first.register_open(position("A"))
    first.register_open(position("B"))

    second = RiskManager(config, clock=FakeClock(), store=store)
    assert second.restore()
    assert set(second.positions) == {"A", "B"}
    assert second.open_count == 2


def test_restart_does_not_reopen_the_same_token(config, store):
    """Иначе после рестарта пайплайн купит то же самое второй раз."""
    first = RiskManager(config, clock=FakeClock(), store=store)
    first.register_open(position("A"))

    second = RiskManager(config, clock=FakeClock(), store=store)
    second.restore()
    assert second.evaluate("A", 0.9).reason == "already_open"


def test_restart_keeps_daily_loss_limit(config, store):
    clock = FakeClock()
    first = RiskManager(config, clock=clock, store=store)
    first.register_open(position("A"))
    first.register_close("A", pnl_sol=-2.0)
    assert first.halted

    second = RiskManager(config, clock=clock, store=store)
    second.restore()
    assert second.halted
    assert not second.evaluate("B", 1.0).approved


def test_restart_keeps_trade_count(config, store):
    clock = FakeClock()
    first = RiskManager(config, clock=clock, store=store)
    for i in range(5):
        first.register_open(position(f"M{i}"))
        first.register_close(f"M{i}", pnl_sol=0.0)

    second = RiskManager(config, clock=clock, store=store)
    second.restore()
    assert second.trades_today == 5
    assert second.evaluate("N", 0.9).reason.startswith("max_trades_per_day")


def test_state_from_another_day_resets_counters_but_keeps_positions(config, store):
    clock = FakeClock()
    first = RiskManager(config, clock=clock, store=store)
    first.register_open(position("A"))
    first.register_close("A", pnl_sol=-2.0)
    first.register_open(position("B"))
    assert first.halted

    clock.advance_days(1)
    second = RiskManager(config, clock=clock, store=store)
    second.restore()
    assert "B" in second.positions        # позиция реально открыта на цепочке
    assert not second.halted              # а лимит — вчерашний
    assert second.trades_today == 0


def test_day_roll_persists_reset(config, store):
    clock = FakeClock()
    manager = RiskManager(config, clock=clock, store=store)
    manager.register_open(position("A"))
    manager.register_close("A", pnl_sol=-1.0)

    clock.advance_days(1)
    manager.roll_day_if_needed()

    reloaded = StateStore(store.path).load()
    assert reloaded is not None
    assert reloaded.trades_today == 0
    assert reloaded.realized_pnl_sol == 0.0


def test_manager_without_store_works(config):
    """Хранилище опционально: без него менеджер просто ничего не пишет."""
    manager = RiskManager(config, clock=FakeClock())
    manager.register_open(position("A"))
    assert not manager.restore()
    assert manager.open_count == 1


def test_unreadable_state_does_not_block_start(config, store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("мусор")
    manager = RiskManager(config, clock=FakeClock(), store=store)
    assert not manager.restore()
    assert manager.evaluate("A", 0.9).approved
