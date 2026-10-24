"""Typed tool layer composition root (STRUCT-002, TOOL-001..008).

``build_registry()`` is the single place the CLI and the desk gateway obtain a
``ToolRegistry``: an injected clock (``FixtureClock`` for replays, ``WallClock`` in
production), a list-backed audit sink owned by the caller, a permitting limits
checker (the PaperAdapter enforces approvals itself through its RiskEngine),
and one ``RateLimiter`` per ``rate_limit_key`` held inside the
registry. ``build_operator_registry()`` composes the full 37-tool Phase 4
catalog over the same root for operator verbs (TOOL-011).
"""

from __future__ import annotations

import logging
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

import pumpgrok.execution
from pumpgrok.core.adapter import ExecutionAdapter, OrderRequest
from pumpgrok.core.binding_key import load_or_create_binding_key
from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.manifests import load_bot_manifests
from pumpgrok.core.registry import GrantAudit, ToolRegistry
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.engine.reputation import ReputationBook
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import WallClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.alert_channel import build_alert_channel
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import InflightBarrier, killswitch_file
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
from pumpgrok.tools.notify.notifier import HttpxNotifier
from pumpgrok.tools.notify.telegram import TelegramSender, read_telegram_token
from pumpgrok.tools.notify.webhook import WebhookSender
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
from pumpgrok.tools.risk.kill_switch import ClosePosition, build_kill_switch_tool, flatten_hook_for
from pumpgrok.tools.safety.score_report import build_score_report_tool

if TYPE_CHECKING:
    from pumpgrok.config.settings import SafetyThresholds, Settings
    from pumpgrok.core.bot import BotManifest
    from pumpgrok.execution.paper_adapter import CurveSnapshot, PriceSource


__all__ = ["build_operator_registry", "build_registry", "register_read_tools"]


log = logging.getLogger(__name__)

# Telegram bot tokens live in the request path: /bot<digits>:<secret>/sendMessage.
# httpx logs that URL at INFO. The value-based redaction pattern needs a word
# boundary before the digits, and "bot" is a word character, so it never matches.
_TELEGRAM_PATH_TOKEN = re.compile(r"/bot\d+:[A-Za-z0-9_-]+")
_HTTP_CLIENT_LOGGERS: tuple[str, ...] = ("httpx", "httpcore")


class _TelegramPathFilter(logging.Filter):
    """Mask Telegram bot tokens in a rendered request URL before any handler sees it."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = _TELEGRAM_PATH_TOKEN.sub("/bot[redacted]", message)
        if masked != message:
            record.msg = masked
            record.args = ()
        return True


def _install_telegram_path_filter() -> None:
    """Attach the token mask to each HTTP client logger once (idempotent)."""
    for name in _HTTP_CLIENT_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, _TelegramPathFilter) for f in logger.filters):
            logger.addFilter(_TelegramPathFilter())


async def _permit_exec(request: OrderRequest, bot_id: str) -> bool:
    """Permitting limits checker: the PaperAdapter enforces approvals itself."""
    del request, bot_id
    return True


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
        limits_checker=_permit_exec,
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
    *,
    rpc: RpcClient,
    adapter: ExecutionAdapter,
    budget: RiskBudget,
    thresholds: SafetyThresholds,
    store: LedgerStore,
    clock: Clock,
) -> None:
    """Scoring, quote/simulate/place/cancel and position tools (real adapter)."""
    reg.register(build_score_report_tool(rpc, thresholds))
    reg.register(build_quote_tool(adapter, clock))
    reg.register(build_simulate_tool(adapter, clock))
    reg.register(build_place_tool(adapter, lambda: budget, clock))
    reg.register(build_cancel_tool(adapter, store, clock))
    reg.register(build_positions_tool(adapter, clock))


def _register_ledger_and_risk(
    reg: ToolRegistry,
    store: LedgerStore,
    clock: Clock,
    data_dir: Path,
    budget: RiskBudget,
    *,
    close_position: ClosePosition,
    barrier: InflightBarrier,
) -> None:
    """Ledger, portfolio, risk, journal and report tools over the one ledger store."""
    kill_switch_file = killswitch_file(data_dir)
    reg.register(build_ledger_read_tool(store, clock))
    reg.register(build_ledger_write_tool(store, clock))
    reg.register(build_exposure_tool(store, clock))
    reg.register(build_pnl_tool(store, clock))
    reg.register(build_check_limits_tool(store, budget, clock))
    reg.register(build_drawdown_tool(store, budget, clock))
    reg.register(build_halt_status_tool(store, kill_switch_file, clock, "paper"))
    reg.register(
        build_kill_switch_tool(
            store,
            clock,
            kill_switch_file,
            close_position=close_position,
            barrier=barrier,
        )
    )
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
    client: httpx.AsyncClient,
) -> None:
    """Alert, brief, docs, memory, ownership, receipt, event and doctor tools."""
    _install_telegram_path_filter()
    notifier = HttpxNotifier(
        telegram=TelegramSender(client),
        webhook=WebhookSender(client, clock),
        allowlist=tuple(settings.notify.allowlist),
        clock=clock,
        alert_file=data_dir / "alerts.jsonl",
    )
    reg.register(build_alert_tool(notifier, clock))
    reg.register(build_brief_tool(store, bank, clock, None, "paper"))
    reg.register(build_docs_search_tool(repo_root, clock))
    reg.register(build_memory_retain_tool(bank, clock))
    reg.register(build_memory_recall_tool(bank, clock))
    reg.register(build_ownership_resolve_tool(repo_root / "ownership.yaml", clock))
    reg.register(build_receipt_check_tool(repo_root / "ci" / "gates", repo_root, clock))
    reg.register(build_event_emit_tool(store, clock, data_dir / "journal"))
    binding_key = load_or_create_binding_key(data_dir)
    reg.register(build_doctor_tool(settings, data_dir / "bindings", binding_key, clock))


class _CachingPriceSource:
    """Price source that records every observed curve for the sync risk check.

    The PaperAdapter reads curves asynchronously, but RiskEngine's
    liquidity-floor step needs a synchronous ``(sol, units)`` lookup. This
    wrapper delegates to the injected source and caches the latest snapshot
    per mint; ``last.get`` feeds ``RiskEngine(get_reserves=...)``. The cache
    warms on any adapter read (the CLI paper flow simulates before placing),
    and a cold mint fails closed with ``no curve reserves``.
    """

    def __init__(self, inner: PriceSource | None) -> None:
        self._inner = inner
        self.last: dict[str, tuple[int, int]] = {}

    async def curve(self, mint: str) -> CurveSnapshot | None:
        """Delegate the read and cache the observed reserves."""
        if self._inner is None:
            return None
        snapshot = await self._inner.curve(mint)
        if snapshot is not None:
            self.last[mint] = (snapshot.s_lamports, snapshot.t_units)
        return snapshot


def build_operator_registry(
    *,
    data_dir: Path,
    repo_root: Path,
    settings: Settings,
    clock: Clock | None = None,
    ledger_path: Path | None = None,
    price_source: PriceSource | None = None,
    p_drop: float = 0.0,  # CLI default: deterministic confirms; replay passes seeded curves
) -> tuple[ToolRegistry, dict[str, BotManifest], httpx.AsyncClient]:
    """Compose the full 37-tool operator registry (TOOL-011, R63).

    Same wiring as the desk gateway and the least-privilege harness: every
    catalog tool registers through its production factory with the real
    paper adapter (TOOL-004, R64), so the CLI resolves
    through ``registry.find`` and I1 holds on every verb. ``ledger_path``
    overrides the store location: the CLI passes the canonical paper ledger.
    ``price_source`` injects curve reads (tests pass scripted curves;
    production paper trading binds the RPC curve reader in Phase 4).
    ``p_drop`` fixes the confirmation-drop rate with a seeded stream
    (the CLI default ``0.0`` gives deterministic confirms; replay passes
    seeded curves with an explicit rate). The seeded ``make_rng`` stream
    keeps replay deterministic (paper-engine 4.2).
    Returns the registry,
    the ten seat manifests, and the HTTP client the caller must close.
    """
    active_clock = clock if clock is not None else WallClock()
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(repo_root)
    reg, _audits = build_registry(clock=active_clock, rng=make_rng())
    client = httpx.AsyncClient()
    rpc = RpcClient(
        list(settings.rpc.endpoints),
        client,
        active_clock,
        make_rng(),
        api_key=settings.rpc.api_key,
    )
    store = LedgerStore(ledger_path if ledger_path is not None else data_dir / "ledger.sqlite")
    live = settings.effective_mode == "live"
    curves = _CachingPriceSource(price_source)
    budget = settings.risk
    engine = RiskEngine(
        store=store,
        budget=budget,
        ids=IdFactory(active_clock, make_rng()),
        clock=active_clock,
        limits=settings.limits,
        mode="live" if live else "paper",
        autonomy="manual-ticket" if live else read_autonomy(store),  # type: ignore[arg-type]
        killswitch_path=killswitch_file(data_dir),
        alert_channel=build_alert_channel(
            token=read_telegram_token(),
            allowlist=settings.notify.allowlist,
            state_dir=data_dir,
        ),
        get_reserves=curves.last.get,
    )
    # R62: a missing file is an empty healthy book; a corrupt file quarantines
    # to a degraded book, which refuses buys with reputation_degraded.
    engine.set_reputation(ReputationBook.load(settings.ops.reputation_path, clock=active_clock))
    log.info(
        "operator registry effective budget=%s limits=%s",
        budget.model_dump(mode="json"),
        settings.limits.model_dump(mode="json"),
    )
    adapter = pumpgrok.execution.build_adapter(
        settings,
        store=store,
        risk=engine,
        ids=IdFactory(active_clock, make_rng()),
        clock=active_clock,
        rng=make_rng(),
        price_source=curves,
        p_drop=p_drop,
    )
    engine.attach_flatten_hook(
        flatten_hook_for(store, adapter.inflight_barrier, adapter.close_position)
    )
    bank = MemoryBank(data_dir / "memory.jsonl")

    register_read_tools(reg, rpc)
    _register_trading(
        reg,
        rpc=rpc,
        adapter=adapter,
        budget=budget,
        thresholds=settings.safety.thresholds,
        store=store,
        clock=active_clock,
    )
    _register_ledger_and_risk(
        reg,
        store,
        active_clock,
        data_dir,
        budget,
        close_position=adapter.close_position,
        barrier=adapter.inflight_barrier,
    )
    _register_desk(
        reg,
        store=store,
        bank=bank,
        clock=active_clock,
        settings=settings,
        data_dir=data_dir,
        repo_root=repo_root,
        client=client,
    )
    manifests = load_bot_manifests(repo_root / "contracts" / "tool-rosters")
    return reg, manifests, client
