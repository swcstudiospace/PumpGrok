"""Typed tool layer composition root (STRUCT-002, TOOL-001..008).

`build_registry()` is the single place the CLI and the desk gateway obtain a
`ToolRegistry`: an injected clock (`FixtureClock` for replays, `WallClock` in
production), a list-backed audit sink owned by the caller, a fail-closed
limits checker that refuses every approval-gated call until RiskEngine lands
(Phase 4), and one `RateLimiter` per `rate_limit_key` held inside the
registry. `build_operator_registry()` composes the full 37-tool Phase 3
catalog over the same root for operator verbs (TOOL-011).
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.errors import NotYetImplemented
from pumpgrok.core.ids import Clock
from pumpgrok.core.manifests import load_bot_manifests
from pumpgrok.core.registry import GrantAudit, ToolRegistry
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.not_yet_implemented import NotYetImplementedAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import WallClock
from pumpgrok.replay.rng import make_rng
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
from pumpgrok.tools.market.holders_snapshot import build_holders_snapshot_tool
from pumpgrok.tools.market.liquidity import build_liquidity_tool
from pumpgrok.tools.market.ohlcv import build_ohlcv_tool
from pumpgrok.tools.market.price import build_price_tool
from pumpgrok.tools.market.trades import build_trades_tool
from pumpgrok.tools.notify.alert import build_alert_tool
from pumpgrok.tools.notify.notifier import Notifier
from pumpgrok.tools.onchain.authorities_tool import build_authorities_tool
from pumpgrok.tools.onchain.deployer_history import build_deployer_history_tool
from pumpgrok.tools.onchain.large_transfers import build_large_transfers_tool
from pumpgrok.tools.onchain.lp_status import build_lp_status_tool
from pumpgrok.tools.onchain.priority_fee_tool import build_priority_fee_tool
from pumpgrok.tools.onchain.rpc import RpcClient
from pumpgrok.tools.onchain.token_metadata import build_token_metadata_tool
from pumpgrok.tools.onchain.top_holders import build_top_holders_tool
from pumpgrok.tools.portfolio.exposure import build_exposure_tool
from pumpgrok.tools.portfolio.ledger_read import build_ledger_read_tool
from pumpgrok.tools.portfolio.ledger_write import build_ledger_write_tool
from pumpgrok.tools.portfolio.pnl import build_pnl_tool
from pumpgrok.tools.risk.check_limits import build_check_limits_tool
from pumpgrok.tools.risk.drawdown import build_drawdown_tool
from pumpgrok.tools.risk.halt_status import build_halt_status_tool
from pumpgrok.tools.risk.kill_switch import build_kill_switch_tool
from pumpgrok.tools.safety.score_report import build_score_report_tool

if TYPE_CHECKING:
    from pumpgrok.config.settings import Settings
    from pumpgrok.core.bot import BotManifest


__all__ = ["build_operator_registry", "build_registry", "register_read_tools"]


async def _refuse_all(request: OrderRequest, bot_id: str) -> bool:
    """Fail-closed limits checker (skeleton): refuse until RiskEngine lands."""
    return False


class _NeverSendNotifier(Notifier):
    """Registration-only notifier: the Phase 3 CLI never calls notify.alert."""

    async def send_telegram(self, chat_id: str, text: str) -> None:
        raise NotYetImplemented("notify.alert needs the Phase 4 supervisor relay")

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        raise NotYetImplemented("notify.alert needs the Phase 4 supervisor relay")


def build_registry(
    clock: Clock | None = None,
    rng: random.Random | None = None,
) -> tuple[ToolRegistry, list[GrantAudit]]:
    """Build an empty registry with replay-safe defaults.

    Returns the registry plus the audit list backing its sink, so tests and
    the gateway can assert one row per resolution attempt (I4).
    """
    audits: list[GrantAudit] = []
    registry = ToolRegistry(
        clock=clock if clock is not None else WallClock(),
        audit_sink=audits.append,
        limits_checker=_refuse_all,
        rng=rng,
    )
    return registry, audits


def register_read_tools(registry: ToolRegistry, rpc: RpcClient) -> ToolRegistry:
    """Register the twelve wave-2 READ tools bound to one RPC client.

    Market (TOOL-001) and onchain (TOOL-002) tools share the single
    ``RpcClient`` with ordered failover and a header-only key (T-03-02-02).
    Returns the registry for chaining.
    """
    registry.register_all(
        [
            build_price_tool(rpc),
            build_ohlcv_tool(rpc),
            build_liquidity_tool(rpc),
            build_trades_tool(rpc),
            build_holders_snapshot_tool(rpc),
            build_token_metadata_tool(rpc),
            build_authorities_tool(rpc),
            build_lp_status_tool(rpc),
            build_top_holders_tool(rpc),
            build_deployer_history_tool(rpc),
            build_large_transfers_tool(rpc),
            build_priority_fee_tool(rpc),
        ]
    )
    return registry


def _register_trading(
    reg: ToolRegistry,
    rpc: RpcClient,
    adapter: NotYetImplementedAdapter,
    budget: RiskBudget,
    clock: Clock,
) -> None:
    """Scoring, quote/simulate/place/cancel and position tools (refusing adapter)."""
    reg.register(build_score_report_tool(rpc))
    reg.register(build_quote_tool(adapter, clock))
    reg.register(build_simulate_tool())
    reg.register(build_place_tool(adapter, lambda: budget, clock))
    reg.register(build_cancel_tool())
    reg.register(build_positions_tool(adapter, clock))


def _register_ledger_and_risk(
    reg: ToolRegistry, store: LedgerStore, clock: Clock, data_dir: Path, budget: RiskBudget
) -> None:
    """Ledger, portfolio, risk, journal and report tools over the one ledger store."""
    kill_switch_file = data_dir / "KILLSWITCH"
    reg.register(build_ledger_read_tool(store, clock))
    reg.register(build_ledger_write_tool(store, clock))
    reg.register(build_exposure_tool(store, clock))
    reg.register(build_pnl_tool(store, clock))
    reg.register(build_check_limits_tool(store, budget, clock))
    reg.register(build_drawdown_tool(store, budget, clock))
    reg.register(build_halt_status_tool(store, kill_switch_file, clock, "paper"))
    reg.register(build_kill_switch_tool(store, clock, kill_switch_file))
    reg.register(build_journal_append_tool(store, clock, data_dir / "journal"))
    reg.register(build_render_report_tool(store, clock, data_dir / "reports"))


def _register_desk(
    reg: ToolRegistry,
    *,
    store: LedgerStore,
    bank: MemoryBank,
    clock: Clock,
    settings: Settings,
    data_dir: Path,
    repo_root: Path,
) -> None:
    """Alert, brief, docs, memory, ownership, receipt, event and doctor tools."""
    reg.register(
        build_alert_tool(
            _NeverSendNotifier(allowlist=(), clock=clock, alert_file=data_dir / "alerts.jsonl"),
            clock,
        )
    )
    reg.register(build_brief_tool(store, bank, clock, None, "paper"))
    reg.register(build_docs_search_tool(repo_root, clock))
    reg.register(build_memory_retain_tool(bank, clock))
    reg.register(build_memory_recall_tool(bank, clock))
    reg.register(build_ownership_resolve_tool(repo_root / "ownership.yaml", clock))
    reg.register(build_receipt_check_tool(repo_root / "ci" / "gates", repo_root, clock))
    reg.register(build_event_emit_tool(store, clock, data_dir / "journal"))
    reg.register(build_doctor_tool(settings, data_dir / "bindings", os.urandom(32), clock))


def build_operator_registry(
    *,
    data_dir: Path,
    repo_root: Path,
    settings: Settings,
    clock: Clock | None = None,
) -> tuple[ToolRegistry, dict[str, BotManifest], httpx.AsyncClient]:
    """Compose the full 37-tool operator registry (TOOL-011, R63).

    Same wiring as the desk gateway and the least-privilege harness: every
    catalog tool registers through its production factory with the refusing
    execution adapter (Phase 3 backends land in Phase 4), so the CLI resolves
    through ``registry.find`` and I1 holds on every verb. Returns the registry,
    the ten seat manifests, and the HTTP client the caller must close.
    """
    active_clock = clock if clock is not None else WallClock()
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(repo_root)
    reg, _audits = build_registry(clock=active_clock, rng=make_rng())
    client = httpx.AsyncClient()
    rpc = RpcClient(list(settings.rpc.endpoints), client, active_clock, make_rng())
    store = LedgerStore(data_dir / "ledger.sqlite")
    adapter = NotYetImplementedAdapter()
    budget = RiskBudget()
    bank = MemoryBank(data_dir / "memory.jsonl")

    register_read_tools(reg, rpc)
    _register_trading(reg, rpc, adapter, budget, active_clock)
    _register_ledger_and_risk(reg, store, active_clock, data_dir, budget)
    _register_desk(
        reg,
        store=store,
        bank=bank,
        clock=active_clock,
        settings=settings,
        data_dir=data_dir,
        repo_root=repo_root,
    )
    manifests = load_bot_manifests(repo_root / "contracts" / "tool-rosters")
    return reg, manifests, client
