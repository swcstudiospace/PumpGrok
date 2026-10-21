"""Shared full-registry builder for the 03-04 least-privilege suites.

Builds every one of the 37 catalog tools through its production factory
with test doubles: an ``httpx.MockTransport`` RPC client that refuses any
real call, a tmp ``LedgerStore``, the refusing adapter, an empty-allowlist
notifier, and a tmp memory bank. One helper keeps the least-privilege, the
cron-seat, and the gateway-projection suites on the same registry shape.
The LIVE probe is not built here: it lives in the test module that needs
it and is registered into a test-only registry, never the real one.

Resolution helper binds a fresh correlation id per find (registry I4).
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx

from pumpgrok.config.settings import Settings
from pumpgrok.core.bot import BotManifest
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, load_bot_manifests
from pumpgrok.core.registry import GrantAudit, ToolRegistry
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.execution.not_yet_implemented import NotYetImplementedAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools import build_registry, register_read_tools
from pumpgrok.tools.desk._memory import MemoryBank
from pumpgrok.tools.desk.brief import build_brief_tool
from pumpgrok.tools.desk.docs_search import build_docs_search_tool
from pumpgrok.tools.desk.doctor import build_doctor_tool
from pumpgrok.tools.desk.event_emit import build_event_emit_tool
from pumpgrok.tools.desk.memory_recall import build_memory_recall_tool
from pumpgrok.tools.desk.memory_retain import build_memory_retain_tool
from pumpgrok.tools.desk.ownership_resolve import build_ownership_resolve_tool
from pumpgrok.tools.desk.receipt_check import build_receipt_check_tool
from pumpgrok.tools.exec.cancel import build_cancel_tool
from pumpgrok.tools.exec.place import build_place_tool
from pumpgrok.tools.exec.positions import build_positions_tool
from pumpgrok.tools.exec.quote import build_quote_tool
from pumpgrok.tools.exec.simulate import build_simulate_tool
from pumpgrok.tools.journal.append import build_journal_append_tool
from pumpgrok.tools.journal.render_report import build_render_report_tool
from pumpgrok.tools.notify.alert import build_alert_tool
from pumpgrok.tools.notify.notifier import Notifier
from pumpgrok.tools.onchain.rpc import RpcClient
from pumpgrok.tools.portfolio.exposure import build_exposure_tool
from pumpgrok.tools.portfolio.ledger_read import build_ledger_read_tool
from pumpgrok.tools.portfolio.ledger_write import build_ledger_write_tool
from pumpgrok.tools.portfolio.pnl import build_pnl_tool
from pumpgrok.tools.risk.check_limits import build_check_limits_tool
from pumpgrok.tools.risk.drawdown import build_drawdown_tool
from pumpgrok.tools.risk.halt_status import build_halt_status_tool
from pumpgrok.tools.risk.kill_switch import build_kill_switch_tool
from pumpgrok.tools.safety.score_report import build_score_report_tool

REPO_ROOT = Path(__file__).resolve().parents[1]
ROSTERS_DIR = REPO_ROOT / "contracts" / "tool-rosters"
START = 1469918176.385


class _NullNotifier(Notifier):
    """Notifier double that refuses any send: resolution only, never called."""

    async def send_telegram(self, chat_id: str, text: str) -> None:
        raise AssertionError("least-privilege suites never send alerts")

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        raise AssertionError("least-privilege suites never send alerts")


def _rpc(clock: FixtureClock) -> RpcClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("least-privilege suites never call the RPC")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return RpcClient(["https://rpc.invalid"], client, clock, random.Random(31))


def build_full_registry(
    tmp_path: Path,
) -> tuple[ToolRegistry, list[GrantAudit], dict[str, BotManifest]]:
    """Build the real registry shape: all 37 catalog tools, no LIVE probe."""
    clock = FixtureClock(start=START)
    reg, audits = build_registry(clock=clock, rng=random.Random(33))
    rpc = _rpc(clock)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    adapter = NotYetImplementedAdapter()
    budget = RiskBudget()
    bank = MemoryBank(tmp_path / "memory.jsonl")

    register_read_tools(reg, rpc)
    reg.register(build_score_report_tool(rpc))
    reg.register(build_quote_tool(adapter, clock))
    reg.register(build_simulate_tool())
    reg.register(build_place_tool(adapter, lambda: budget, clock))
    reg.register(build_cancel_tool())
    reg.register(build_positions_tool(adapter, clock))
    reg.register(build_ledger_read_tool(store, clock))
    reg.register(build_ledger_write_tool(store, clock))
    reg.register(build_exposure_tool(store, clock))
    reg.register(build_pnl_tool(store, clock))
    reg.register(build_check_limits_tool(store, budget, clock))
    reg.register(build_drawdown_tool(store, budget, clock))
    reg.register(build_halt_status_tool(store, tmp_path / "KILLSWITCH", clock, "paper"))
    reg.register(build_kill_switch_tool(store, clock, tmp_path / "KILLSWITCH"))
    reg.register(build_journal_append_tool(store, clock, tmp_path / "journal"))
    reg.register(build_render_report_tool(store, clock, tmp_path / "reports"))
    reg.register(
        build_alert_tool(
            _NullNotifier(allowlist=(), clock=clock, alert_file=tmp_path / "alerts.jsonl"),
            clock,
        )
    )
    reg.register(build_brief_tool(store, bank, clock, None, "paper"))
    reg.register(build_docs_search_tool(REPO_ROOT, clock))
    reg.register(build_memory_retain_tool(bank, clock))
    reg.register(build_memory_recall_tool(bank, clock))
    reg.register(build_ownership_resolve_tool(REPO_ROOT / "ownership.yaml", clock))
    reg.register(build_receipt_check_tool(REPO_ROOT / "ci" / "gates", REPO_ROOT, clock))
    reg.register(build_event_emit_tool(store, clock, tmp_path / "journal"))
    reg.register(
        build_doctor_tool(Settings(mode="paper"), tmp_path / "bindings", b"03-04-doc-key", clock)
    )

    manifests = load_bot_manifests(ROSTERS_DIR)
    assert set(manifests) == set(EXPECTED_SEAT_IDS)
    return reg, audits, manifests


def resolve(
    reg: ToolRegistry,
    bot: BotManifest,
    capability: str,
    max_side_effect: SideEffect = SideEffect.PAPER_WRITE,
) -> Any:
    """find() under a fresh bound correlation id (registry I4)."""
    factory = IdFactory(FixtureClock(start=START), random.Random(37))
    with bind_correlation(CorrelationId.new(factory)):
        return reg.find(capability, max_side_effect=max_side_effect, bot=bot)
