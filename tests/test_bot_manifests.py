"""SKILL-003: ten seat manifests load as BotManifest with R35 sizes (SC1 file 2).

Tracer first: ten manifests load with no silent skip, the _core merge is
proven (chief resolves desk.brief through the registry), and negative
resolution is proven (chief cannot resolve exec.place).

SKILL-003 suite: exact R35 effective sizes (core eight included), flag
rules (writes_to_exchange only sniper+exit, kill_switch only risk,
notify.alert absent on risk+rug, ledger_write absent everywhere), nine
explicit R20 risk keys per seat, non-empty forbidden lists.

Loader contract (src/pumpgrok/core/manifests.py): allowed_tools is derived
from each roster's own tools list plus _core.yaml, never written in the
manifest block, so tool names stay in exactly one place. The loader fails
closed: a missing manifest block, an unknown seat file, or a count other
than ten raises instead of skipping.
"""

from __future__ import annotations

import random
import re
import sys
from decimal import Decimal
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from pumpgrok.core.bot import BotManifest
from pumpgrok.core.errors import PermissionDenied
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, load_bot_manifests
from pumpgrok.core.registry import ToolRegistry
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import ToolInput, ToolMeta, ToolOutput, ToolSpec, tool
from pumpgrok.replay.clock import FixtureClock

REPO_ROOT = Path(__file__).resolve().parents[1]
ROSTERS_DIR = REPO_ROOT / "contracts" / "tool-rosters"
SEAT_RE = re.compile(r"^bot-0[0-9]-[a-z-]+$")

# R35 effective sizes (own tools plus the desk.* core eight).
EXPECTED_SIZES = {
    "bot-00-chief": 15,
    "bot-01-scout": 15,
    "bot-02-risk": 15,
    "bot-03-whale": 14,
    "bot-04-sniper": 15,
    "bot-05-rug": 15,
    "bot-06-exit": 15,
    "bot-07-shill": 11,
    "bot-08-signal": 14,
    "bot-09-journal": 15,
}

RISK_KEYS = [
    "max_trade_fraction",
    "max_token_fraction",
    "daily_loss_halt_fraction",
    "drawdown_halt_fraction",
    "max_open_positions",
    "max_trades_per_day",
    "liquidity_floor_multiple",
    "partial_fill_fraction",
    "paper_equity_sol",
]

START = 1469918176.385


def _manifests() -> dict[str, BotManifest]:
    return load_bot_manifests(ROSTERS_DIR)


# -- tracer registry (two inline specs; resolution only, never called) -------


class _In(ToolInput):
    q: str = "x"


class _Out(ToolOutput):
    answer: str = "y"


def _tracer_registry() -> tuple[ToolRegistry, list]:
    audits: list = []
    reg = ToolRegistry(
        clock=FixtureClock(start=START),
        audit_sink=audits.append,
        limits_checker=_refuse_all,
        rng=random.Random(7),
    )

    @tool(
        ToolSpec(
            name="desk.brief",
            description="Start-of-turn brief for the tracer registry.",
            input_model=_In,
            output_model=_Out,
            side_effect=SideEffect.READ,
            timeout_s=10.0,
            rate_limit_key="desk",
            backend="core.brief",
        )
    )
    async def _brief(payload: _In) -> dict:  # pragma: no cover - never called
        raise AssertionError("tracer registry never calls tools")

    @tool(
        ToolSpec(
            name="exec.place",
            description="Paper place for the tracer registry.",
            input_model=_In,
            output_model=_Out,
            side_effect=SideEffect.PAPER_WRITE,
            timeout_s=20.0,
            rate_limit_key="exec",
            requires_approval=True,
            idempotent=True,
            backend="exec.place",
        )
    )
    async def _place(payload: _In) -> dict:  # pragma: no cover - never called
        raise AssertionError("tracer registry never calls tools")

    reg.register_all([_brief, _place])
    return reg, audits


async def _refuse_all(request: object, bot_id: str) -> bool:
    return False


def _cid() -> CorrelationId:
    return CorrelationId.new(IdFactory(FixtureClock(start=START), random.Random(8)))


# -- tracer -----------------------------------------------------------------


def test_ten_manifests_load_with_expected_ids() -> None:
    manifests = _manifests()
    assert set(manifests) == set(EXPECTED_SEAT_IDS), (
        f"loader must return exactly the ten seats, got {sorted(manifests)}"
    )


def test_chief_resolves_desk_brief() -> None:
    reg, _ = _tracer_registry()
    chief = _manifests()["bot-00-chief"]
    with bind_correlation(_cid()):
        resolved = reg.find("desk.brief", max_side_effect=SideEffect.READ, bot=chief)
    assert resolved.spec.name == "desk.brief"


def test_chief_cannot_resolve_exec_place() -> None:
    reg, _ = _tracer_registry()
    chief = _manifests()["bot-00-chief"]
    with bind_correlation(_cid()), pytest.raises(PermissionDenied):
        reg.find("exec.place", max_side_effect=SideEffect.PAPER_WRITE, bot=chief)


# -- SKILL-003 suite ----------------------------------------------------------


def test_ten_manifests_validate() -> None:
    manifests = _manifests()
    assert len(manifests) == 10
    for seat_id, manifest in manifests.items():
        assert SEAT_RE.match(seat_id), f"{seat_id} must match SEAT_RE"
        assert manifest.id == seat_id


def test_writes_to_exchange_only_sniper_and_exit() -> None:
    manifests = _manifests()
    writers = {sid for sid, m in manifests.items() if m.writes_to_exchange}
    assert writers == {"bot-04-sniper", "bot-06-exit"}


def test_roster_tool_count_8_to_15_r35_sizes() -> None:
    manifests = _manifests()
    for seat_id, expected in EXPECTED_SIZES.items():
        actual = len(manifests[seat_id].allowed_tools)
        assert actual == expected, f"{seat_id}: {actual} != R35 {expected}"


def test_kill_switch_only_risk() -> None:
    manifests = _manifests()
    holders = [sid for sid, m in manifests.items() if m.grant_for("risk.kill_switch")]
    assert holders == ["bot-02-risk"]


def test_notify_alert_absent_risk_rug() -> None:
    manifests = _manifests()
    for seat_id in ("bot-02-risk", "bot-05-rug"):
        assert manifests[seat_id].grant_for("notify.alert") is None, (
            f"{seat_id} must escalate via desk.event_emit, never notify.alert"
        )
    assert manifests["bot-00-chief"].grant_for("notify.alert") is not None
    assert manifests["bot-09-journal"].grant_for("notify.alert") is not None


def test_ledger_write_absent_everywhere() -> None:
    manifests = _manifests()
    for seat_id, manifest in manifests.items():
        assert manifest.grant_for("portfolio.ledger_write") is None, (
            f"{seat_id} must never hold portfolio.ledger_write (adapter-only)"
        )


def test_nine_risk_budget_keys_explicit_per_seat() -> None:
    for seat_id in EXPECTED_SEAT_IDS:
        doc = yaml.safe_load((ROSTERS_DIR / f"{seat_id}.yaml").read_text(encoding="utf-8"))
        block = doc.get("manifest") or {}
        budget = block.get("risk_budget") or {}
        missing = [k for k in RISK_KEYS if k not in budget]
        assert not missing, f"{seat_id} manifest must list all nine R20 keys, missing {missing}"
    manifests = _manifests()
    assert manifests["bot-04-sniper"].risk_budget.max_trade_fraction == Decimal("0.02")
    assert manifests["bot-04-sniper"].risk_budget.max_open_positions == 3
    assert manifests["bot-06-exit"].risk_budget.max_trade_fraction == Decimal("0")
    assert manifests["bot-06-exit"].risk_budget.max_trades_per_day == 20
    assert manifests["bot-02-risk"].risk_budget.max_open_positions == 0


def test_non_trading_seats_carry_zero_trade_keys() -> None:
    manifests = _manifests()
    for seat_id, manifest in manifests.items():
        if seat_id in ("bot-04-sniper", "bot-06-exit"):
            continue
        budget = manifest.risk_budget
        assert budget.max_trade_fraction == Decimal("0"), seat_id
        assert budget.max_token_fraction == Decimal("0"), seat_id
        assert budget.max_open_positions == 0, seat_id
        assert budget.max_trades_per_day == 0, seat_id
        assert budget.paper_equity_sol == Decimal("10"), seat_id


def test_forbidden_non_empty_everywhere() -> None:
    manifests = _manifests()
    for seat_id, manifest in manifests.items():
        assert manifest.forbidden, f"{seat_id} must name at least one forbidden action"


def test_core_merge_matches_core_yaml() -> None:
    core_doc = yaml.safe_load((ROSTERS_DIR / "_core.yaml").read_text(encoding="utf-8"))
    core_names = [t["name"] for t in core_doc["tools"]]
    assert len(core_names) == 8
    manifests = _manifests()
    for seat_id, manifest in manifests.items():
        granted = {g.name for g in manifest.allowed_tools}
        assert set(core_names) <= granted, f"{seat_id} must merge all eight core tools"


def test_manifest_id_matches_roster_seat() -> None:
    manifests = _manifests()
    for seat_id in EXPECTED_SEAT_IDS:
        doc = yaml.safe_load((ROSTERS_DIR / f"{seat_id}.yaml").read_text(encoding="utf-8"))
        assert doc["seat"] == seat_id
        assert manifests[seat_id].id == doc["seat"]
