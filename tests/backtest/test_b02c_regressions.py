"""B02c regression pins: each test fails on the pre-sweep base (d03de9e)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from pumpgrok.backtest.divergence import check as divergence_check
from pumpgrok.backtest.gaps import _apply_positions
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.grok.cache import cache_key
from pumpgrok.grok.gateway import CircuitBreaker, sanitize
from pumpgrok.risk.breakers import LossVelocityBreaker
from pumpgrok.strategies.base import TapePoint
from pumpgrok.strategies.recovery import StrategyBook
from pumpgrok.strategies.tape import Tape
from pumpgrok.tools.risk.kill_switch import kill_switch_key
from pumpgrok.upgrade.params import ParamSet


def test_tape_window_keeps_more_than_64_ticks() -> None:
    tape = Tape()
    for step in range(200):
        tape.record("M", TapePoint(ts=float(step), price_lamports=step))
    assert len(tape.points("M")) > 64


def test_strategy_book_window_sees_dense_lookback() -> None:
    book = StrategyBook.fresh()
    for step in range(100):
        book.observe("M", float(step), step)
    window = book.window("M", now=99.0, seconds=300.0)
    assert len(window) == 100


def test_reopened_mint_visible_after_first_gap() -> None:
    events = (
        {"ts": 0.0, "kind": "open", "mint": "M", "mark_lamports": 100, "cost_basis_lamports": 100},
        {"ts": 10.0, "kind": "open", "mint": "M", "mark_lamports": 110, "cost_basis_lamports": 110},
    )
    _flags, open_mints = _apply_positions(events, ((5.0, 8.0),), haircut_bps=0, exclude=False)
    assert open_mints == ("M",)


def test_zero_trade_divergence_never_blocks() -> None:
    empty = MetricsReport(
        total_return=Decimal(0),
        max_drawdown=Decimal(0),
        sharpe_ratio=Decimal(0),
        win_rate=Decimal(0),
        trade_count=0,
        exposure_lamports=0,
        turnover_lamports=0,
    )
    traded = MetricsReport(
        total_return=Decimal("0.5"),
        max_drawdown=Decimal(0),
        sharpe_ratio=Decimal("2"),
        win_rate=Decimal("1"),
        trade_count=3,
        exposure_lamports=10,
        turnover_lamports=30,
    )
    verdict = divergence_check(empty, traded)
    assert verdict.blocks_promotion is False


def test_budget_refuses_zero_halt_fractions() -> None:
    with pytest.raises(ValueError):
        RiskBudget(daily_loss_halt_fraction=Decimal("0"))
    with pytest.raises(ValueError):
        RiskBudget(drawdown_halt_fraction=Decimal("0"))


def test_paramset_copies_caller_dict() -> None:
    source: dict = {"a": {"b": 1}}
    param = ParamSet(strategy=source)
    source["a"]["b"] = 99
    assert param.strategy == {"a": {"b": 1}}


def test_paramset_hash_is_cached() -> None:
    param = ParamSet(filter={"min_unique_buyers": 5})
    first = param.content_hash
    assert first == param.content_hash


def test_kill_key_changes_with_epoch() -> None:
    clock = SimpleNamespace(now=lambda: 0.0)
    assert kill_switch_key("set", "r", clock, epoch=0) != kill_switch_key(
        "set", "r", clock, epoch=1
    )


def test_loss_velocity_is_exact_fraction() -> None:
    now = [100.0]
    breaker = LossVelocityBreaker(lambda: now[0])
    breaker._points.extend([(0.0, 1000), (10.0, 980)])
    loss = breaker._window_loss(10.0, 900.0)
    assert loss is not None and float(loss) == pytest.approx(0.02)


def test_sanitize_drops_surrogates() -> None:
    cleaned = sanitize("ok\ud800 text")
    cleaned.encode("utf-8")


def test_breaker_probe_token_blocks_second_probe() -> None:
    now = [0.0]
    breaker = CircuitBreaker(SimpleNamespace(now=lambda: now[0]))
    for _ in range(3):
        breaker.record_failure()
    now[0] = 1_000.0
    assert breaker.admits() is True
    token = breaker.start()
    assert breaker.admits() is False
    breaker.record_failure(token - 1)  # stale settle must not free the probe
    assert breaker._probe is True
    breaker.record_failure(token)
    assert breaker._probe is False


def test_cache_keys_distinguish_decimal_from_string() -> None:
    base = {
        "agent": "narrative",
        "model": "grok-test",
        "prompt_sha": "a" * 64,
        "schema": "verdict.v1",
        "sanitizer_version": "1",
    }
    dec = cache_key(**base, fields={"prerank": Decimal("0.5")})  # type: ignore[arg-type]
    text = cache_key(**base, fields={"prerank": "0.5"})  # type: ignore[arg-type]
    assert dec != text
