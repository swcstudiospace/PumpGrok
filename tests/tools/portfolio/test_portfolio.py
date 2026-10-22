"""RED: portfolio tools (ledger_read/write, exposure, pnl) — TOOL-005.

- portfolio.ledger_write registered and PermissionDenied for all ten seats
- exposure/pnl read the ledger; empty ledger yields zeros, never an exception
"""

from __future__ import annotations

import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest
from pydantic import ValidationError

from pumpgrok.core.bot import BotManifest, ToolGrant
from pumpgrok.core.errors import PermissionDenied
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.tools import build_registry
from pumpgrok.tools.portfolio.exposure import (
    EXPOSURE_SPEC,
    ExposureIn,
    build_exposure_tool,
)
from pumpgrok.tools.portfolio.ledger_read import (
    LEDGER_READ_SPEC,
    LedgerReadIn,
    build_ledger_read_tool,
)
from pumpgrok.tools.portfolio.ledger_write import (
    LEDGER_WRITE_SPEC,
    LedgerWriteIn,
    build_ledger_write_tool,
)
from pumpgrok.tools.portfolio.pnl import PNL_SPEC, PnlIn, build_pnl_tool

START = 1469918176.385
SEATS = [
    "bot-00-chief",
    "bot-01-scout",
    "bot-02-risk",
    "bot-03-whale",
    "bot-04-sniper",
    "bot-05-rug",
    "bot-06-exit",
    "bot-07-shill",
    "bot-08-signal",
    "bot-09-journal",
]


def _manifest(seat: str) -> BotManifest:
    return BotManifest(
        id=seat,
        display=seat,
        channel="DM",
        purpose="test seat",
        inputs=[],
        outputs=[],
        skills=[],
        allowed_tools=[ToolGrant(name="market.price", side_effect=SideEffect.READ)],
        risk_budget={},
        forbidden=[],
        fail_safe="halt",
        schedule=[],
        escalation=[],
        owned_paths=[],
        receipts_dir="var/receipts",
        prompt_source="test",
    )


def _resolve(reg, capability: str, bot: BotManifest):
    factory = IdFactory(FixtureClock(start=START), random.Random(7))
    with bind_correlation(CorrelationId.new(factory)):
        return reg.find(capability, max_side_effect=SideEffect.PAPER_WRITE, bot=bot)


def _store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_ledger_write_spec_is_paper_write() -> None:
    assert LEDGER_WRITE_SPEC.side_effect is SideEffect.PAPER_WRITE
    assert LEDGER_WRITE_SPEC.timeout_s == 5.0
    assert LEDGER_WRITE_SPEC.retry.attempts == 1
    assert LEDGER_WRITE_SPEC.rate_limit_key == "ledger"
    assert LEDGER_WRITE_SPEC.idempotent is True


def test_ledger_write_never_a_seat_grant() -> None:
    with pytest.raises(ValidationError):
        BotManifest(
            **{
                **_manifest("bot-02-risk").model_dump(),
                "allowed_tools": [{"name": "portfolio.ledger_write", "side_effect": "paper-write"}],
            }
        )


def test_ledger_write_denied_for_all_ten_seats(tmp_path: Path) -> None:
    store = _store(tmp_path)
    reg, _ = build_registry(clock=FixtureClock(start=START))
    reg.register(build_ledger_write_tool(store, FixtureClock(start=START)))
    for seat in SEATS:
        with pytest.raises(PermissionDenied):
            _resolve(reg, "portfolio.ledger_write", _manifest(seat))
    store.close()


def test_ledger_write_rejects_unknown_event_type(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValidationError):
        LedgerWriteIn(
            type="RobotTakeover",
            source="paper",
            payload={},
            idempotency_key="k" * 32,
        )
    store.close()


async def test_ledger_write_appends_and_replays_duplicate(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_ledger_write_tool(store, FixtureClock(start=START))
    payload = {
        "type": "Escalation",
        "source": "paper",
        "payload": {"source": "paper", "kind": "rug_alert", "seat": "bot-05-rug", "detail": "x"},
        "idempotency_key": "d" * 32,
    }
    first = await tool(LedgerWriteIn.model_validate(payload))
    assert first.duplicate is False
    assert first.seq == 1
    second = await tool(LedgerWriteIn.model_validate(payload))
    assert second.duplicate is True
    assert second.seq == 1
    assert store.count() == 1
    store.close()


async def test_ledger_read_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    clock = FixtureClock(start=START)
    writer = build_ledger_write_tool(store, clock)
    key = "e" * 32
    await writer(
        LedgerWriteIn(
            type="Escalation",
            source="paper",
            payload={"source": "paper", "kind": "rug_alert", "seat": "bot-05-rug", "detail": "x"},
            idempotency_key=key,
        )
    )
    assert LEDGER_READ_SPEC.side_effect is SideEffect.READ
    reader = build_ledger_read_tool(store, clock)
    out = await reader(LedgerReadIn())
    assert len(out.events) == 1
    assert out.events[0]["type"] == "Escalation"
    assert out.events[0]["idempotency_key"] == key
    assert out.latest_snapshot is None
    store.close()


async def test_exposure_empty_ledger_is_zeros(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_exposure_tool(store, FixtureClock(start=START))
    assert EXPOSURE_SPEC.rate_limit_key == "ledger"
    out = await tool(ExposureIn())
    assert out.equity_lamports == 0
    assert out.cash_lamports == 0
    assert out.open_positions == 0
    assert out.per_token == []
    store.close()


async def test_pnl_empty_ledger_is_zeros(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_pnl_tool(store, FixtureClock(start=START))
    assert PNL_SPEC.rate_limit_key == "ledger"
    out = await tool(PnlIn(window="day"))
    assert out.realised_lamports == 0
    assert out.trades == 0
    assert out.win_rate is None
    assert out.profit_factor is None
    store.close()


def _funded_then_spent(store: LedgerStore, clock: FixtureClock, spent: int) -> None:
    """Fund 1 SOL, then spend ``spent`` lamports on a buy with no open position."""
    store.set_meta("initial_equity_lamports", "1000000000")
    store.set_meta("source", "paper")
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="t",
        idempotency_key="review-r3-f16-spend",
        type="FillRecorded",
        payload={
            "source": "paper",
            "order_id": "o-f16",
            "decision_id": "d-f16",
            "side": "buy",
            "mint": "So11111111111111111111111111111111111111112",
            "filled_lamports": spent,
            "filled_units": 10,
            "filled_fraction": "1",
            "price_avg": "1",
            "venue_fee_lamports": 0,
            "network_cost_lamports": 0,
            "cash_delta_lamports": -spent,
        },
    )


async def test_exposure_reports_funded_equity_after_loss(tmp_path: Path) -> None:
    """Review finding 16: exposure reads current equity from the ledger, not a snapshot key."""
    store = _store(tmp_path)
    clock = FixtureClock(start=START)
    _funded_then_spent(store, clock, 300_000_000)
    out = await build_exposure_tool(store, clock)(ExposureIn())
    store.close()
    assert out.equity_lamports == 700_000_000
    assert out.cash_lamports == 700_000_000


async def test_pnl_reports_current_drawdown_and_daily_loss(tmp_path: Path) -> None:
    """Review finding 16: pnl ratios come from the folded balance, not hardcoded zeros."""
    store = _store(tmp_path)
    clock = FixtureClock(start=START)
    _funded_then_spent(store, clock, 300_000_000)
    out = await build_pnl_tool(store, clock)(PnlIn(window="all"))
    store.close()
    assert out.day_start_equity_lamports == 1_000_000_000
    assert out.peak_equity_lamports == 1_000_000_000
    assert out.drawdown_fraction == Decimal("0.3")
    assert out.daily_loss_fraction == Decimal("0.3")
