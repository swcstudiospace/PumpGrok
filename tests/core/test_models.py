"""Model tests: RiskBudget, canonical_json, ApprovalRecord, BotManifest."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.bot import BotManifest, ToolGrant
from pumpgrok.core.idempotency import canonical_json, derive_idempotency_key
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.side_effect import SideEffect

NINE_KEYS = {
    "max_trade_fraction": Decimal("0.02"),
    "max_token_fraction": Decimal("0.05"),
    "daily_loss_halt_fraction": Decimal("0.05"),
    "drawdown_halt_fraction": Decimal("0.15"),
    "max_open_positions": 3,
    "max_trades_per_day": 20,
    "liquidity_floor_multiple": 10,
    "partial_fill_fraction": Decimal("0.02"),
    "paper_equity_sol": Decimal("10"),
}


def test_risk_budget_nine_keys_and_daily_loss_cap() -> None:
    budget = RiskBudget(**NINE_KEYS)
    assert budget.paper_equity_lamports == 10_000_000_000
    assert budget.may_open_exposure is True
    with pytest.raises(Exception):
        RiskBudget(**{**NINE_KEYS, "daily_loss_halt_fraction": Decimal("0.051")})
    with pytest.raises(Exception):
        RiskBudget(**{**NINE_KEYS, "paper_equity_sol": Decimal("1.5")}, extra="x")  # type: ignore[call-arg]


def test_canonical_json_sorts_rejects_float_decimal_as_str() -> None:
    assert canonical_json({"b": 1, "a": [3, 2]}) == '{"a":[3,2],"b":1}'
    assert canonical_json({"amt": Decimal("1.50")}) == '{"amt":"1.50"}'
    with pytest.raises(TypeError):
        canonical_json({"x": 1.5})
    with pytest.raises(TypeError):
        canonical_json({"x": [1, 2.0]})
    with pytest.raises(TypeError):
        canonical_json({"x": {"y": float("nan")}})


def test_derive_idempotency_key_stable_and_scoped() -> None:
    payload = {
        "ticket_id": "SOL-20260101-001",
        "scope": "s",
        "correlation_id": "root.9",
    }
    first = derive_idempotency_key("exec.place", "bot-04-sniper", payload, scope="t:buy:d")
    again = derive_idempotency_key("exec.place", "bot-04-sniper", payload, scope="t:buy:d")
    assert first == again
    assert len(first) == 32
    assert all(c in "0123456789abcdef" for c in first)
    other_scope = derive_idempotency_key("exec.place", "bot-04-sniper", payload, scope="t:sell:d")
    assert other_scope != first
    retry_same = derive_idempotency_key(
        "exec.place",
        "bot-04-sniper",
        {**payload, "correlation_id": "root.10"},
        scope="t:buy:d",
    )
    assert retry_same == first


def _approval_id() -> str:
    return "apr-01ARYZ6S41TSV4RRFF7Q3V9J6Q"


def _base_approval(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": _approval_id(),
        "kind": "human_buy",
        "ticket_id": "SOL-20260101-001",
        "mint": "7xKXtg2CW87d97TXJSDpbD5HgznomR9rzme8H7Xwq",
        "size_lamports": 1_000_000,
        "max_slippage_bps": 100,
        "approved_by": "human:alice",
        "raw_message": "approve SOL-20260101-001 <mint> 0.001 100",
        "at": datetime.fromtimestamp(1469918176.385, UTC),
    }
    base.update(over)
    return base


def test_approval_record_all_r33_kinds() -> None:
    ApprovalRecord(**_base_approval(kind="human_buy"))
    ApprovalRecord(**_base_approval(kind="human_sell"))
    ApprovalRecord(
        **_base_approval(kind="exit_rule", exit_rule_id="trailing_stop", size_lamports=None)
    )
    ApprovalRecord(
        **_base_approval(
            kind="autonomous_paper",
            approved_by="risk_engine",
            ticket_id=None,
            mint=None,
            size_lamports=None,
            max_slippage_bps=None,
        )
    )
    for kind in ("killswitch_clear", "halt_clear", "live_gate"):
        ApprovalRecord(
            **_base_approval(
                kind=kind,
                ticket_id=None,
                mint=None,
                size_lamports=None,
                max_slippage_bps=None,
            )
        )
    with pytest.raises(Exception):
        ApprovalRecord(**_base_approval(kind="autonomous_paper", approved_by="human:alice"))
    with pytest.raises(Exception):
        ApprovalRecord(**_base_approval(kind="human_buy", approved_by="risk_engine"))


def test_bot_manifest_carries_risk_budget_and_forbidden() -> None:
    bot = BotManifest(
        id="bot-04-sniper",
        display="Sniper",
        channel="DM",
        purpose="paper buys",
        inputs=["signal.verdict"],
        outputs=["exec.place"],
        skills=["momentum-signals"],
        allowed_tools=[
            ToolGrant(name="exec.place", side_effect=SideEffect.PAPER_WRITE),
            ToolGrant(name="market.price", side_effect=SideEffect.READ),
        ],
        risk_budget=NINE_KEYS,
        forbidden=["no live trading", "no wallet keys"],
        fail_safe="halt and escalate",
        schedule=[],
        escalation=["bot-02-risk"],
        owned_paths=["exec/"],
        receipts_dir="var/receipts",
        prompt_source="prompts/bot-04-sniper.xml",
        writes_to_exchange=True,
    )
    assert bot.risk_budget.daily_loss_halt_fraction == Decimal("0.05")
    assert "no live trading" in bot.forbidden
    assert bot.grant_for("exec.place") is not None
    assert bot.grant_for("market.unknown") is None
