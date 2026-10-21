"""TOOL-009 least-privilege suite (interfaces section 4, invariants I1-I5).

Every assertion resolves through the real registry shape (all 37 catalog
tools, see tests/registry_harness.py) against the manifests loaded from
contracts/tool-rosters/*.yaml. The LIVE probe exec.live_place exists in a
test-only registry only: the vault test pins that the real registry holds
no LIVE_WRITE spec at all.
"""

from __future__ import annotations

import json
import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

import pytest
import yaml
from pydantic import ValidationError

from pumpgrok.core.errors import LiveGateError, PermissionDenied
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.execution.not_yet_implemented import NotYetImplementedAdapter
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.desk.event_emit import EventEmitIn
from pumpgrok.tools.exec.place import PlaceIn, build_place_tool
from pumpgrok.tools.journal.append import JournalAppendIn
from pumpgrok.tools.risk.kill_switch import KillSwitchIn
from registry_harness import ROSTERS_DIR, build_full_registry, resolve

MINT = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
DECISION = "01" + "A" * 24
APPROVAL = "apr-" + "C" * 26

EXIT_BUDGET_KWARGS = {
    "max_trade_fraction": Decimal("0"),
    "max_token_fraction": Decimal("0"),
    "max_open_positions": 0,
}


class _ProbeIn(ToolInput):
    q: str = "x"


class _ProbeOut(ToolOutput):
    answer: str = "y"


def _live_probe():
    @tool(
        ToolSpec(
            name="exec.live_place",
            description="Test-only live-write probe, never resolvable.",
            input_model=_ProbeIn,
            output_model=_ProbeOut,
            side_effect=SideEffect.LIVE_WRITE,
            timeout_s=5.0,
            rate_limit_key="exec",
            idempotent=True,
            backend="test.probe",
        )
    )
    async def _probe(payload: _ProbeIn) -> dict:  # pragma: no cover - never runs
        raise AssertionError("live probe must never execute")

    return _probe


def _buy() -> dict:
    return {
        "ticket_id": TICKET,
        "mint": MINT,
        "side": "buy",
        "decision_id": DECISION,
        "size_lamports": 100_000_000,
        "max_slippage_bps": 100,
        "approval_id": APPROVAL,
    }


def test_no_bot_resolves_live_write(tmp_path: Path) -> None:
    reg, audits, manifests = build_full_registry(tmp_path)
    reg.register(_live_probe())  # test-only registry from here on
    for seat_id in EXPECTED_SEAT_IDS:
        with pytest.raises(LiveGateError):
            resolve(reg, manifests[seat_id], "exec.live_place")
    refusals = [a for a in audits if a.reason == "live_write_never_resolvable"]
    assert len(refusals) == 10
    assert all(a.allowed is False for a in refusals)


def test_real_registry_has_no_live_write_tool(tmp_path: Path) -> None:
    reg, _, _ = build_full_registry(tmp_path)
    live = [n for n in reg.names() if reg.spec(n).side_effect is SideEffect.LIVE_WRITE]
    assert live == [], f"real registry must not contain a live tool: {live}"


def test_sniper_cannot_resolve_kill_switch(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    with pytest.raises(PermissionDenied) as excinfo:
        resolve(reg, manifests["bot-04-sniper"], "risk.kill_switch")
    assert excinfo.value.fields["reason"] == "not_in_roster"


def test_only_sniper_and_exit_resolve_exec_place(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    for seat_id in ("bot-04-sniper", "bot-06-exit"):
        resolved = resolve(reg, manifests[seat_id], "exec.place")
        assert resolved.spec.name == "exec.place"
    for seat_id in EXPECTED_SEAT_IDS:
        if seat_id in ("bot-04-sniper", "bot-06-exit"):
            continue
        with pytest.raises(PermissionDenied):
            resolve(reg, manifests[seat_id], "exec.place")


async def test_exit_cannot_place_buy() -> None:
    class _CountingAdapter(NotYetImplementedAdapter):
        def __init__(self) -> None:
            self.place_calls = 0

        async def place(self, request):  # type: ignore[override]
            self.place_calls += 1
            return await super().place(request)

    adapter = _CountingAdapter()
    exit_tool = build_place_tool(adapter, lambda: RiskBudget(**EXIT_BUDGET_KWARGS))
    out = await exit_tool(PlaceIn.model_validate(_buy()))
    assert out.status == "rejected"
    assert out.reason == "seat_may_trade"
    assert adapter.place_calls == 0


def test_chief_has_no_exposure_tools(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    chief = manifests["bot-00-chief"]
    for name in (
        "exec.place",
        "exec.cancel",
        "market.price",
        "market.ohlcv",
        "market.liquidity",
        "market.trades",
        "market.holders_snapshot",
    ):
        with pytest.raises(PermissionDenied):
            resolve(reg, chief, name)


def test_shill_has_no_write_except_journal(tmp_path: Path) -> None:
    _, _, manifests = build_full_registry(tmp_path)
    core_doc = yaml.safe_load((ROSTERS_DIR / "_core.yaml").read_text(encoding="utf-8"))
    core_names = {t["name"] for t in core_doc["tools"]}
    shill_writes = {
        g.name
        for g in manifests["bot-07-shill"].allowed_tools
        if g.side_effect is SideEffect.PAPER_WRITE
    }
    # desk.* core paper-writes (memory_retain, event_emit, doctor) are granted
    # to every seat by design; outside the shared core, shill writes journal only.
    assert shill_writes - core_names == {"journal.append"}


def test_nobody_resolves_ledger_write(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    for seat_id in EXPECTED_SEAT_IDS:
        with pytest.raises(PermissionDenied) as excinfo:
            resolve(reg, manifests[seat_id], "portfolio.ledger_write")
        assert excinfo.value.fields["reason"] == "not_in_roster", seat_id


def test_kill_switch_tool_has_no_clear_action() -> None:
    with pytest.raises(ValidationError):
        KillSwitchIn.model_validate({"action": "clear", "reason": "x"})
    KillSwitchIn.model_validate({"action": "set", "reason": "x"})
    KillSwitchIn.model_validate({"action": "flatten_request", "reason": "x"})


def test_manifest_tools_subset_of_registry(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    names = set(reg.names())
    for seat_id, manifest in manifests.items():
        for grant in manifest.allowed_tools:
            assert grant.name in names, f"{seat_id} grants {grant.name} (unregistered)"


def test_grant_side_effect_never_exceeds_spec(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    for seat_id, manifest in manifests.items():
        for grant in manifest.allowed_tools:
            spec = reg.spec(grant.name)
            assert grant.side_effect == spec.side_effect, (
                f"{seat_id} grants {grant.name} as {grant.side_effect}, "
                f"spec says {spec.side_effect}"
            )


def test_live_write_audited_and_alerted(tmp_path: Path) -> None:
    reg, audits, manifests = build_full_registry(tmp_path)
    reg.register(_live_probe())
    before = len(audits)
    with pytest.raises(LiveGateError):
        resolve(reg, manifests["bot-02-risk"], "exec.live_place")
    assert len(audits) == before + 1
    row = audits[-1]
    assert (row.bot, row.tool, row.allowed, row.reason) == (
        "bot-02-risk",
        "exec.live_place",
        False,
        "live_write_never_resolvable",
    )
    assert row.correlation_id


def test_every_roster_name_exists_in_registry(tmp_path: Path) -> None:
    reg, _, _ = build_full_registry(tmp_path)
    names = set(reg.names())
    core_doc = yaml.safe_load((ROSTERS_DIR / "_core.yaml").read_text(encoding="utf-8"))
    core_names = {t["name"] for t in core_doc["tools"]}
    for seat_id in EXPECTED_SEAT_IDS:
        doc = yaml.safe_load((ROSTERS_DIR / f"{seat_id}.yaml").read_text(encoding="utf-8"))
        for entry in doc["tools"]:
            assert entry["name"] in names, f"{seat_id} lists {entry['name']} (unregistered)"
            if doc.get("core") is True:
                assert core_names <= names


def test_seats_write_only_journal_note_and_escalation() -> None:
    JournalAppendIn.model_validate(
        {"kind": "journal_note", "note_kind": "note", "body": {}, "bot": "bot-01-scout"}
    )
    EventEmitIn.model_validate({"kind": "escalation", "payload": {}})
    with pytest.raises(ValidationError):
        JournalAppendIn.model_validate(
            {"kind": "order_placed", "note_kind": "note", "body": {}, "bot": "bot-01-scout"}
        )
    with pytest.raises(ValidationError):
        EventEmitIn.model_validate({"kind": "order_placed", "payload": {}})


async def test_journal_append_binds_calling_seat(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    scout = manifests["bot-01-scout"]
    factory = IdFactory(FixtureClock(start=1469918176.385), random.Random(41))
    with bind_correlation(CorrelationId.new(factory)):
        append = reg.find(
            "journal.append", max_side_effect=SideEffect.PAPER_WRITE, bot=scout
        )
        out = await append(
            JournalAppendIn(
                kind="journal_note",
                note_kind="lead",
                ticket_id=TICKET,
                body={"text": "scout saw a launch"},
                bot="bot-01-scout",
            )
        )
        assert out.seq == 1
        with pytest.raises(PermissionDenied):
            await append(
                JournalAppendIn(
                    kind="journal_note",
                    note_kind="lead",
                    ticket_id=TICKET,
                    body={"text": "forged as chief"},
                    bot="bot-00-chief",
                )
            )
    files = list((tmp_path / "journal").glob("*.jsonl"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8").splitlines()[-1])["payload"]
    assert payload["seat"] == "bot-01-scout"


async def test_event_emit_uses_calling_seat_not_chief(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    scout = manifests["bot-01-scout"]
    factory = IdFactory(FixtureClock(start=1469918176.385), random.Random(43))
    with bind_correlation(CorrelationId.new(factory)):
        emit = reg.find(
            "desk.event_emit", max_side_effect=SideEffect.PAPER_WRITE, bot=scout
        )
        out = await emit(
            EventEmitIn(kind="escalation", task_id="t-9", payload={"kind": "rug_alert"})
        )
    files = list((tmp_path / "journal").glob("*.jsonl"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8").splitlines()[-1])["payload"]
    assert payload["seat"] == "bot-01-scout"
