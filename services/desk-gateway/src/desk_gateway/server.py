"""Thin stdlib-HTTP projection over the in-process registry (TOOL-010, B4).

No tool logic lives here: ``tools/list`` projects roster YAML through
``pumpgrok.contracts.projection``; ``tools/call`` maps the transport name
back through the roster dict and resolves through the registry (Phase 3
backends answer ``not_yet_implemented`` where they are unbuilt).

Transport: ``ThreadingHTTPServer`` plus ``asyncio.run`` per request, with
``WallClock``. Only ``POST /mcp/<short>`` serves JSON-RPC; every other
verb answers 405 and every unknown seat answers 404.
"""

from __future__ import annotations

import json
import logging
import os
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

from pumpgrok.config.settings import Settings
from pumpgrok.contracts.projection import (
    default_contracts_dir,
    exposure_entries,
    short_to_seat,
)
from pumpgrok.core.bot import BotManifest
from pumpgrok.core.errors import NotYetImplemented
from pumpgrok.core.registry import GrantAudit, ToolRegistry
from pumpgrok.execution.not_yet_implemented import NotYetImplementedAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import Clock, WallClock
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
from pumpgrok.core.risk_budget import RiskBudget

log = logging.getLogger("desk_gateway")

RPC_ENV_VAR = "DESK_GATEWAY_RPC_ENDPOINTS"
DEFAULT_RPC_ENDPOINTS = ("https://api.mainnet-beta.solana.com",)


class _ClosedNotifier(Notifier):
    """Refusing alert sink: the gateway owns no delivery path (fail-closed)."""

    async def send_telegram(self, chat_id: str, text: str) -> None:
        raise NotYetImplemented(
            "notify.send needs Phase 4 sinks", tool="notify.alert"
        )

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        raise NotYetImplemented(
            "notify.send needs Phase 4 sinks", tool="notify.alert"
        )


def rpc_endpoints() -> list[str]:
    """Ordered RPC endpoints from the environment, with a default fallback."""
    raw = os.environ.get(RPC_ENV_VAR, "")
    endpoints = [part.strip() for part in raw.split(",") if part.strip()]
    return endpoints or list(DEFAULT_RPC_ENDPOINTS)


def build_gateway_registry(
    *,
    data_dir: Path,
    repo_root: Path,
    clock: Clock | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[ToolRegistry, dict[str, BotManifest]]:
    """Compose the full 37-tool registry the gateway projects (no tool logic).

    Wiring only: every catalog tool is registered exactly as the root
    least-privilege harness builds it, so ``registry.find`` enforces the
    same roster grants over HTTP as in-process. Returns the registry plus
    the ten seat manifests for ``find``.
    """
    from pumpgrok.core.manifests import load_bot_manifests

    active_clock = clock if clock is not None else WallClock()
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    reg, _audits = build_registry(clock=active_clock, rng=random.Random())
    client = http_client if http_client is not None else httpx.AsyncClient()
    rpc = RpcClient(rpc_endpoints(), client, active_clock, random.Random())
    store = LedgerStore(data_dir / "ledger.sqlite")
    adapter = NotYetImplementedAdapter()
    budget = RiskBudget()
    bank = MemoryBank(data_dir / "memory.jsonl")

    register_read_tools(reg, rpc)
    reg.register(build_score_report_tool(rpc))
    reg.register(build_quote_tool(adapter))
    reg.register(build_simulate_tool())
    reg.register(build_place_tool(adapter, lambda: budget))
    reg.register(build_cancel_tool())
    reg.register(build_positions_tool(adapter))
    reg.register(build_ledger_read_tool(store))
    reg.register(build_ledger_write_tool(store, active_clock))
    reg.register(build_exposure_tool(store, active_clock))
    reg.register(build_pnl_tool(store, active_clock))
    reg.register(build_check_limits_tool(store, budget))
    reg.register(build_drawdown_tool(store, budget))
    reg.register(build_halt_status_tool(store, data_dir / "KILLSWITCH", "paper"))
    reg.register(build_kill_switch_tool(store, active_clock, data_dir / "KILLSWITCH"))
    reg.register(build_journal_append_tool(store, active_clock, data_dir / "journal"))
    reg.register(build_render_report_tool(store, active_clock, data_dir / "reports"))
    reg.register(
        build_alert_tool(
            _ClosedNotifier(
                allowlist=(), clock=active_clock, alert_file=data_dir / "alerts.jsonl"
            ),
            active_clock,
        )
    )
    reg.register(build_brief_tool(store, bank, active_clock, None, "paper"))
    reg.register(build_docs_search_tool(repo_root))
    reg.register(build_memory_retain_tool(bank))
    reg.register(build_memory_recall_tool(bank))
    reg.register(build_ownership_resolve_tool(repo_root / "ownership.yaml"))
    reg.register(build_receipt_check_tool(repo_root / "ci" / "gates", repo_root))
    reg.register(
        build_event_emit_tool(store, active_clock, data_dir / "journal", "bot-00-chief")
    )
    reg.register(
        build_doctor_tool(
            Settings(mode="paper"),
            data_dir / "bindings",
            os.urandom(32),
        )
    )
    manifests = load_bot_manifests(default_contracts_dir())
    return reg, manifests


def _short_from_path(path: str) -> str | None:
    stem = path.split("?", 1)[0].rstrip("/")
    prefix, sep, short = stem.rpartition("/mcp/")
    if not sep or "/" in short or not short:
        return None
    if prefix not in ("",):
        return None
    return short


class _Handler(BaseHTTPRequestHandler):
    """JSON-RPC over POST only; auth and tools/call land in plan task 2."""

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _method_not_allowed(self) -> None:
        self._send_json(
            405, {"error": {"code": "method_not_allowed", "message": "use POST"}}
        )

    do_GET = _method_not_allowed
    do_PUT = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_HEAD = _method_not_allowed
    do_OPTIONS = _method_not_allowed

    def do_POST(self) -> None:
        state = self.server.gateway_state  # type: ignore[attr-defined]
        short = _short_from_path(self.path)
        seat_id = state["shorts"].get(short) if short else None
        if seat_id is None:
            self._send_json(
                404, {"error": {"code": "unknown_seat", "message": "unknown seat"}}
            )
            log.info("seat=%s status=%s", short, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            envelope = json.loads(self.rfile.read(length).decode() or "null")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(
                400,
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "parse error"},
                },
            )
            log.info("seat=%s status=%s", short, 400)
            return
        if (
            not isinstance(envelope, dict)
            or envelope.get("jsonrpc") != "2.0"
            or not isinstance(envelope.get("method"), str)
        ):
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": envelope.get("id") if isinstance(envelope, dict) else None,
                    "error": {"code": -32600, "message": "invalid request"},
                },
            )
            log.info("seat=%s status=%s", short, 200)
            return
        request_id = envelope.get("id")
        method = envelope["method"]
        if method == "tools/list":
            result: dict[str, Any] = {
                "tools": exposure_entries(seat_id, state["contracts_dir"])
            }
            self._send_json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})
            log.info("seat=%s status=%s", short, 200)
            return
        self._send_json(
            200,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown method: {method}"},
            },
        )
        log.info("seat=%s status=%s", short, 200)


def create_server(
    *,
    host: str,
    port: int,
    contracts_dir: Path,
    tokens: dict[str, str],
    registry: ToolRegistry,
    manifests: dict[str, BotManifest],
    clock: Clock,
) -> ThreadingHTTPServer:
    """Bind a threaded JSON-RPC server over the given registry and manifests."""
    server = ThreadingHTTPServer((host, port), _Handler)
    server.gateway_state = {  # type: ignore[attr-defined]
        "contracts_dir": Path(contracts_dir),
        "tokens": dict(tokens),
        "registry": registry,
        "manifests": manifests,
        "clock": clock,
        "shorts": short_to_seat(contracts_dir),
    }
    server.daemon_threads = True
    return server
