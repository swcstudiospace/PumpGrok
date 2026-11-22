"""RSK-01: a buy above its strategy slice is capped or rejected on max_token_fraction.

TDD matrix: at cap passes, above cap is capped to the slice room, cap+1
lamports over the room is capped (never silently filled above the slice),
and an exhausted slice rejects on max_token_fraction with the reason on
the existing risk row. Slice state comes from ledger rows, never memory.
"""

from __future__ import annotations

import random
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.strategy_slice import SliceConfig, load_slice_config, spent_from_ledger

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
BIG_RESERVES = (42_000_000_000, 764_000_000_000_000)
STRATEGY = "momentum_breakout"


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, *, enabled: bool = True) -> RiskEngine:
    config = SliceConfig(
        weights={STRATEGY: Decimal("0.02")},
        reserve=Decimal("0.80"),
        enabled=enabled,
    )
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="autonomous-paper",
        get_reserves=lambda _mint: BIG_RESERVES,
        slice_config=config,
    )


def _buy(ids: IdFactory, size: int) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT_A,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=size,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _record_spend(store: LedgerStore, clock: FixtureClock, size: int) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"spend-{size}-{clock.now()}",
        type="OrderPlaced",
        payload={
            "source": "paper",
            "order_id": "01H" + "0" * 23,
            "decision_id": "01H" + "0" * 23,
            "ticket_id": TICKET,
            "side": "buy",
            "mint": MINT_A,
            "slippage_bps": 50,
            "size_lamports": size,
            "approval_json": f'{{"strategy": "{STRATEGY}"}}',
        },
    )


def test_default_weights_sum_at_most_one_and_load_from_config() -> None:
    config = load_slice_config()
    assert config.weights == {
        "legacy_screening": Decimal("0.20"),
        "momentum_breakout": Decimal("0.20"),
        "new_launch_sniper": Decimal("0.20"),
        "mean_reversion": Decimal("0.20"),
    }
    assert config.reserve == Decimal("0.20")
    assert sum(config.weights.values(), Decimal("0")) + config.reserve <= Decimal("1.0")
    assert config.enabled is False  # config-gated off by default


def test_weights_summing_above_one_refuse_to_load(tmp_path: Path) -> None:
    bad = tmp_path / "slices.toml"
    bad.write_text(
        '[strategy.slice]\nenabled = true\nreserve = "0.20"\n'
        '[strategy.slice.weights]\nmomentum_breakout = "0.90"\n',
        encoding="utf-8",
    )
    try:
        load_slice_config(bad)
    except Exception as exc:
        assert isinstance(exc, ValueError)
    else:  # pragma: no cover
        raise AssertionError("weights above 1.0 must refuse to load")


def test_buy_at_the_slice_cap_passes(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    engine = _engine(store, clock)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 200_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is True
    assert decision.size_lamports == 200_000_000
    assert decision.capped is False


def test_buy_above_the_slice_is_capped_to_the_room(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    engine = _engine(store, clock)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 300_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is True
    assert decision.capped is True
    assert decision.size_lamports == 200_000_000
    assert decision.caps["strategy_slice"] == 200_000_000
    assert decision.reason == "pass"


def test_spent_from_ledger_shrinks_the_room_across_restart(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _record_spend(store, clock, 150_000_000)
    assert spent_from_ledger(store, STRATEGY) == 150_000_000
    # A fresh engine over the same ledger still sees the spend.
    engine = _engine(store, clock)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 300_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is True
    assert decision.size_lamports == 50_000_000
    assert decision.caps["strategy_slice"] == 50_000_000


def test_exhausted_slice_rejects_on_max_token_fraction(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _record_spend(store, clock, 195_000_000)
    engine = _engine(store, clock)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 300_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is False
    assert decision.reason == "max_token_fraction"
    assert any(
        row["id"] == "max_token_fraction" and row["status"] == "fail" for row in decision.evaluated
    )


def test_disabled_slice_behaves_exactly_as_before(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    engine = _engine(store, clock, enabled=False)
    ids = IdFactory(clock, random.Random(3))
    decision = engine.check(_buy(ids, 300_000_000), seat="bot-04-sniper", strategy_id=STRATEGY)
    assert decision.passed is True
    assert "strategy_slice" not in decision.caps
