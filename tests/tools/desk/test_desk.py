"""Desk core-eight tests (TOOL-007): specs, search, memory, ownership, doctor."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest
from pydantic import ValidationError

from pumpgrok.config.settings import NotifySettings, Settings
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.doctor import doctor_report
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, WallClock
from pumpgrok.tools.desk._memory import MemoryBank
from pumpgrok.tools.desk._tokens import digest_compare, digest_token
from pumpgrok.tools.desk.brief import BRIEF_SPEC, BriefIn, build_brief_tool
from pumpgrok.tools.desk.docs_search import (
    DOCS_SEARCH_SPEC,
    DocsSearchIn,
    build_docs_search_tool,
)
from pumpgrok.tools.desk.doctor import DOCTOR_SPEC, DoctorIn, build_doctor_tool
from pumpgrok.tools.desk.event_emit import (
    EVENT_EMIT_SPEC,
    EventEmitIn,
    build_event_emit_tool,
    event_emit_key,
    scrub_payload,
)
from pumpgrok.tools.desk.memory_recall import (
    MEMORY_RECALL_SPEC,
    MemoryRecallIn,
    build_memory_recall_tool,
)
from pumpgrok.tools.desk.memory_retain import (
    MEMORY_RETAIN_SPEC,
    MemoryRetainIn,
    build_memory_retain_tool,
    memory_retain_key,
)
from pumpgrok.tools.desk.ownership_resolve import (
    OWNERSHIP_RESOLVE_SPEC,
    OwnershipResolveIn,
    build_ownership_resolve_tool,
)
from pumpgrok.tools.desk.receipt_check import (
    RECEIPT_CHECK_SPEC,
    ReceiptCheckIn,
    build_receipt_check_tool,
)

START = 1469918176.385
REPO_ROOT = Path(__file__).resolve().parents[3]


def _bank(tmp_path: Path) -> MemoryBank:
    return MemoryBank(tmp_path / "memory.jsonl")


def _store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_desk_specs_match_catalog() -> None:
    assert (BRIEF_SPEC.side_effect, BRIEF_SPEC.timeout_s) == (SideEffect.READ, 10.0)
    assert (DOCS_SEARCH_SPEC.side_effect, DOCS_SEARCH_SPEC.timeout_s) == (
        SideEffect.READ,
        10.0,
    )
    assert (MEMORY_RETAIN_SPEC.side_effect, MEMORY_RETAIN_SPEC.timeout_s) == (
        SideEffect.PAPER_WRITE,
        5.0,
    )
    assert (MEMORY_RECALL_SPEC.side_effect, MEMORY_RECALL_SPEC.timeout_s) == (
        SideEffect.READ,
        5.0,
    )
    assert (OWNERSHIP_RESOLVE_SPEC.side_effect, OWNERSHIP_RESOLVE_SPEC.timeout_s) == (
        SideEffect.READ,
        5.0,
    )
    assert (RECEIPT_CHECK_SPEC.side_effect, RECEIPT_CHECK_SPEC.timeout_s) == (
        SideEffect.READ,
        60.0,
    )
    assert (EVENT_EMIT_SPEC.side_effect, EVENT_EMIT_SPEC.timeout_s) == (
        SideEffect.PAPER_WRITE,
        5.0,
    )
    assert (DOCTOR_SPEC.side_effect, DOCTOR_SPEC.timeout_s) == (
        SideEffect.PAPER_WRITE,
        60.0,
    )
    for spec in (
        BRIEF_SPEC,
        DOCS_SEARCH_SPEC,
        MEMORY_RETAIN_SPEC,
        MEMORY_RECALL_SPEC,
        OWNERSHIP_RESOLVE_SPEC,
        RECEIPT_CHECK_SPEC,
        EVENT_EMIT_SPEC,
        DOCTOR_SPEC,
    ):
        assert spec.rate_limit_key == "desk"


def test_digest_helpers() -> None:
    token = digest_token("agent-1", "chan-1", key=b"test-key")
    assert len(token) == 64
    assert digest_token("agent-1", "chan-1", key=b"test-key") == token
    assert digest_token("agent-1", "chan-2", key=b"test-key") != token
    assert digest_compare(token, token) is True
    assert digest_compare(token, "0" * 64) is False
    with pytest.raises(ValueError):
        digest_token(key=b"test-key")


async def test_docs_search_finds_catalog_chunk() -> None:
    tool = build_docs_search_tool(REPO_ROOT)
    out = await tool(DocsSearchIn(query="TOOL_CATALOG", limit=5))
    assert out.chunks, "search over a non-empty tree must hit"
    assert {"path", "line", "text"} <= set(out.chunks[0])


async def test_memory_retain_recall_round_trip(tmp_path: Path) -> None:
    bank = _bank(tmp_path)
    retain = build_memory_retain_tool(bank)
    with pytest.raises(ValidationError):
        MemoryRetainIn(content="no provenance")
    first = await retain(MemoryRetainIn(content="exit rule verified", receipt_path="r/1.json"))
    again = await retain(MemoryRetainIn(content="exit rule verified", receipt_path="r/1.json"))
    assert first.id == again.id
    recall = build_memory_recall_tool(bank)
    out = await recall(MemoryRecallIn(query="exit rule"))
    assert len(out.items) == 1 and out.items[0]["content"] == "exit rule verified"
    assert bank.path.is_file()
    key = memory_retain_key("shared", "exit rule verified")
    assert len(key) == 32


async def test_ownership_last_match_wins() -> None:
    tool = build_ownership_resolve_tool(REPO_ROOT / "ownership.yaml")
    out = await tool(
        OwnershipResolveIn(
            paths=["docs/desk-operating-model.md", "contracts/tool-rosters/bot-02-risk.yaml"]
        )
    )
    by_path = {r["path"]: r for r in out.resolved}
    assert by_path["docs/desk-operating-model.md"]["owner"] == "bot-00-chief"
    assert by_path["contracts/tool-rosters/bot-02-risk.yaml"]["owner"] == "bot-02-risk"
    assert by_path["contracts/tool-rosters/bot-02-risk.yaml"]["contract_surface"] is True
    out = await tool(OwnershipResolveIn(paths=["x"]))
    assert out.unowned == ["x"]


async def test_receipt_check_reports_gate_rows() -> None:
    tool = build_receipt_check_tool(REPO_ROOT / "ci" / "gates", REPO_ROOT, WallClock())
    with pytest.raises(ValidationError):
        ReceiptCheckIn(bot="not-a-seat", receipt={})
    out = await tool(ReceiptCheckIn(bot="bot-04-sniper", receipt={"commands": []}, strict=False))
    names = [g["gate"] for g in out.gates]
    assert names == ["G-2", "G-3", "G-5/G-6"]
    assert all(isinstance(g["exit_code"], int) for g in out.gates)
    assert all(isinstance(g["output_tail"], str) for g in out.gates)


async def test_event_emit_scrubs_and_caps(tmp_path: Path) -> None:
    store = _store(tmp_path)
    clock = FixtureClock(start=START)
    tool = build_event_emit_tool(store, clock, tmp_path / "journal", "bot-01-scout")
    out = await tool(
        EventEmitIn(
            kind="journal_note",
            note_kind="lead",
            task_id="t-1",
            payload={"api_token": "secret-abc", "note": "hi"},
        )
    )
    assert out.seq == 1
    event = store.read()[0]
    assert event["payload"]["seat"] == "bot-01-scout"
    assert "***" in event["payload"]["text"]
    assert "secret-abc" not in event["payload"]["text"]
    big = await tool(
        EventEmitIn(
            kind="escalation",
            task_id="t-2",
            payload={"kind": "rug_alert", "detail": "y" * 9000},
        )
    )
    assert big.seq == 2
    stored = store.read()[1]
    assert stored["type"] == "Escalation"
    assert len(stored["payload"]["detail"]) < 9000
    key = event_emit_key("bot-01-scout", "journal_note", "t-1", {"a": 1})
    assert len(key) == 32
    assert event_emit_key("bot-02-risk", "journal_note", "t-1", {"a": 1}) != key
    assert scrub_payload({"k": "v"}) == {"k": "v"}
    store.close()


async def test_doctor_check_shares_cli_path(tmp_path: Path) -> None:
    settings = Settings(mode="paper")
    tool = build_doctor_tool(settings, tmp_path / "bindings", b"test-key")
    out = await tool(DoctorIn(action="check"))
    assert out.ok is True
    rows = {r["check"]: r for r in out.rows}
    assert rows["effective_mode"]["status"] == "ok"
    cli_lines = doctor_report(settings)
    assert rows["doctor_report"]["detail"] == cli_lines[-1]


async def test_doctor_register_and_fail_closed_prompt(tmp_path: Path) -> None:
    settings = Settings(mode="paper")
    tool = build_doctor_tool(settings, tmp_path / "bindings", b"test-key")
    first = await tool(DoctorIn(action="register", agent_uuid="a-1", channel_id="c-1"))
    assert first.ok is True
    again = await tool(DoctorIn(action="register", agent_uuid="a-1", channel_id="c-1"))
    assert again.ok is True
    other = build_doctor_tool(settings, tmp_path / "bindings", b"other-key")
    mismatch = await other(DoctorIn(action="register", agent_uuid="a-1", channel_id="c-1"))
    assert mismatch.ok is False
    prompt = await tool(DoctorIn(action="install_prompt"))
    assert prompt.ok is False and "Phase 4" in prompt.rows[0]["detail"]

async def test_doctor_register_rejects_traversal(tmp_path: Path) -> None:
    settings = Settings(mode="paper")
    tool = build_doctor_tool(settings, tmp_path / "bindings", b"test-key")
    for bad in ("../evil", "a/b", "x" * 65, ""):
        out = await tool(DoctorIn(action="register", agent_uuid=bad, channel_id="c-1"))
        assert out.ok is False
        assert "agent_uuid" in out.rows[0]["detail"]
    assert list((tmp_path / "bindings").glob("*.json")) == []


async def test_brief_folds_halt_and_recall(tmp_path: Path) -> None:
    store = _store(tmp_path)
    bank = _bank(tmp_path)
    bank.retain(key="k1", record={"content": "task t-9 remembered"})
    tool = build_brief_tool(store, bank, FixtureClock(start=START), None, mode="paper")
    out = await tool(BriefIn(task_id="t-9"))
    assert out.halt["halted"] is False
    assert out.tickets == []
    assert len(out.etag) == 16
    store.close()


def test_notify_settings_section() -> None:
    assert NotifySettings().allowlist == []
    assert Settings.model_fields["notify"].is_required() is False

    overlay = tomllib.loads((REPO_ROOT / "src/pumpgrok/config/overlays/paper.toml").read_text())
    assert overlay["notify"]["allowlist"] == []
