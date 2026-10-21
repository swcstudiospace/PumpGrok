"""Thin stdlib-HTTP projection over the in-process registry (TOOL-010, B4).

No tool logic lives here: ``tools/list`` projects roster YAML through
``pumpgrok.contracts.projection``; ``tools/call`` maps the transport name
back through the roster dict and resolves through the registry (Phase 3
backends answer ``not_yet_implemented`` where they are unbuilt).

Transport: ``ThreadingHTTPServer`` plus ``asyncio.run`` per request, with
``WallClock``. Only ``POST /mcp/<short>`` serves JSON-RPC; every other
verb answers 405 and every unknown seat answers 404.

Auth (T-03-05-01/02): per-seat bearer tokens from ``DESK_GATEWAY_TOKEN_*``
only, compared with ``hmac.compare_digest`` in a loop over every seat.
No match is 401, a match for another seat is 403, and a path seat with
no configured token fails closed with 503 and no token detail. Only the
seat short name and the status code are ever logged.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from desk_gateway.config import GatewayConfig
from pumpgrok.config.settings import Settings
from pumpgrok.contracts.projection import (
    default_contracts_dir,
    exposure_entries,
    short_to_seat,
    transport_map,
    transport_name,
)
from pumpgrok.core.bot import BotManifest
from pumpgrok.core.errors import NotYetImplemented, PumpgrokError
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.manifests import load_bot_manifests
from pumpgrok.core.registry import ToolRegistry
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.side_effect import SideEffect
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

log = logging.getLogger("desk_gateway")

RPC_ENV_VAR = "DESK_GATEWAY_RPC_ENDPOINTS"
DEFAULT_RPC_ENDPOINTS = ("https://api.mainnet-beta.solana.com",)


class _ClosedNotifier(Notifier):
    """Refusing alert sink: the gateway owns no delivery path (fail-closed)."""

    async def send_telegram(self, chat_id: str, text: str) -> None:
        raise NotYetImplemented("notify.send needs Phase 4 sinks", tool="notify.alert")

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        raise NotYetImplemented("notify.send needs Phase 4 sinks", tool="notify.alert")


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

    active_clock = clock if clock is not None else WallClock()
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    reg, _audits = build_registry(clock=active_clock, rng=secrets.SystemRandom())
    client = http_client if http_client is not None else httpx.AsyncClient()
    rpc = RpcClient(rpc_endpoints(), client, active_clock, secrets.SystemRandom())
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
            _ClosedNotifier(allowlist=(), clock=active_clock, alert_file=data_dir / "alerts.jsonl"),
            active_clock,
        )
    )
    reg.register(build_brief_tool(store, bank, active_clock, None, "paper"))
    reg.register(build_docs_search_tool(repo_root))
    reg.register(build_memory_retain_tool(bank))
    reg.register(build_memory_recall_tool(bank))
    reg.register(build_ownership_resolve_tool(repo_root / "ownership.yaml"))
    reg.register(build_receipt_check_tool(repo_root / "ci" / "gates", repo_root, active_clock))
    reg.register(build_event_emit_tool(store, active_clock, data_dir / "journal", "bot-00-chief"))
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


def _presented_token(headers: Any) -> str | None:
    value = headers.get("Authorization")
    if not isinstance(value, str):
        return None
    scheme, sep, token = value.partition(" ")
    if not sep or scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _error_result(code: str, message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
        "code": code,
    }


HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403


class _Handler(BaseHTTPRequestHandler):
    """JSON-RPC over POST with per-seat compare_digest auth."""

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _method_not_allowed(self) -> None:
        self._send_json(405, {"error": {"code": "method_not_allowed", "message": "use POST"}})

    do_GET = _method_not_allowed
    do_PUT = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_HEAD = _method_not_allowed
    do_OPTIONS = _method_not_allowed

    def _authenticate(self, short: str, tokens: dict[str, str]) -> int | None:
        """Return an HTTP error status, or None when the request may proceed.

        The presented bearer token is compared against every configured
        seat with ``hmac.compare_digest`` so the matched seat does not leak
        through timing; the path seat must equal the matched seat.
        """
        if short not in tokens:
            return 503
        presented = _presented_token(self.headers)
        matched: str | None = None
        for seat_short, expected in tokens.items():
            if presented is not None and hmac.compare_digest(presented, expected):
                matched = seat_short
        if matched is None:
            return HTTP_UNAUTHORIZED
        if matched != short:
            return HTTP_FORBIDDEN
        return None

    def _auth_error_body(self, status: int) -> dict[str, Any]:
        if status == HTTP_UNAUTHORIZED:
            return {
                "error": {
                    "code": "unauthorized",
                    "message": "missing or unknown bearer token",
                }
            }
        if status == HTTP_FORBIDDEN:
            return {
                "error": {
                    "code": "forbidden",
                    "message": "token belongs to another seat",
                }
            }
        return {
            "error": {
                "code": "seat_unconfigured",
                "message": "seat has no token configured",
            }
        }

    def do_POST(self) -> None:
        state = self.server.gateway_state  # type: ignore[attr-defined]
        short = _short_from_path(self.path)
        seat_id = state["shorts"].get(short) if short else None
        if seat_id is None:
            self._send_json(404, {"error": {"code": "unknown_seat", "message": "unknown seat"}})
            log.info("seat=%s status=%s", short, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        denied = self._authenticate(short, state["tokens"])
        if denied is not None:
            self._send_json(denied, self._auth_error_body(denied))
            log.info("seat=%s status=%s", short, denied)
            return
        self._handle_rpc(state, short, seat_id, raw)

    def _handle_rpc(
        self, state: dict[str, Any], short: str | None, seat_id: str, raw: bytes
    ) -> None:
        """Parse one JSON-RPC envelope and answer the supported methods."""
        try:
            envelope = json.loads(raw.decode() or "null")
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
        if method == "notifications/initialized":
            self._send_empty(202)
            log.info("seat=%s status=%s", short, 202)
            return
        if method == "initialize":
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "desk-gateway", "version": "0.1.0"},
                    },
                },
            )
            log.info("seat=%s status=%s", short, 200)
            return
        if method == "tools/list":
            result: dict[str, Any] = {"tools": exposure_entries(seat_id, state["contracts_dir"])}
            self._send_json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})
            log.info("seat=%s status=%s", short, 200)
            return
        if method == "tools/call":
            result = self._tools_call(state, seat_id, envelope.get("params"))
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

    def _tools_call(self, state: dict[str, Any], seat_id: str, params: Any) -> dict[str, Any]:
        """Map the transport name back through the roster dict and dispatch.

        The seat roster decides first; a name another seat exposes still
        resolves so ``registry.find`` refuses it with ``permission_denied``
        under this seat's manifest instead of a vaguer unknown-tool error.
        """
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _error_result("invalid_arguments", "tools/call needs a name")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _error_result("invalid_arguments", "tools/call arguments must pair")
        dotted = transport_map(seat_id, state["contracts_dir"]).get(params["name"])
        if dotted is None:
            dotted = state["global_map"].get(params["name"])
        if dotted is None:
            return _error_result("unknown_tool", f"unknown tool: {params['name']}")
        registry: ToolRegistry = state["registry"]
        manifests: dict[str, BotManifest] = state["manifests"]
        clock: Clock = state["clock"]
        factory = IdFactory(clock, secrets.SystemRandom())
        cid = CorrelationId.new(factory)

        async def _dispatch() -> tuple[Any | None, dict[str, Any] | None]:
            with bind_correlation(cid):
                try:
                    tool_obj = registry.find(
                        dotted,
                        max_side_effect=SideEffect.PAPER_WRITE,
                        bot=manifests[seat_id],
                    )
                except PumpgrokError as exc:
                    return None, _error_result(exc.code, exc.message)
                try:
                    payload = tool_obj.spec.input_model(**arguments)
                except ValidationError as exc:
                    return None, _error_result(
                        "invalid_arguments",
                        f"invalid arguments for {dotted}: {exc.errors()[0]['msg']}",
                    )
                try:
                    return await tool_obj(payload), None
                except PumpgrokError as exc:
                    return None, _error_result(exc.code, exc.message)

        future = asyncio.run_coroutine_threadsafe(_dispatch(), state["owner_loop"])
        try:
            output, error = future.result(timeout=_CALL_TIMEOUT_S)
        except Exception:
            # Envelope must never leak internals; the traceback stays server-side.
            log.exception("tools/call failed")
            return _error_result("internal_error", "internal error")
        if error is not None:
            return error
        assert output is not None
        dumped = output.model_dump(mode="json")
        return {
            "content": [{"type": "text", "text": json.dumps(dumped)}],
            "isError": False,
        }


_CALL_TIMEOUT_S = 120.0


def _start_owner_loop(
    *,
    data_dir: Path,
    repo_root: Path,
    clock: Clock,
    http_client: httpx.AsyncClient | None,
) -> tuple[Any, dict[str, Any]]:
    """Run the tool loop in its own thread and build the registry inside it.

    ``LedgerStore`` holds a sqlite connection bound to its creating thread,
    so the registry must be both built and used in one owner thread while
    ``ThreadingHTTPServer`` serves requests from worker threads.
    """
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    cell: dict[str, Any] = {}

    def _serve_tools() -> None:
        asyncio.set_event_loop(loop)
        try:
            cell["registry"], cell["manifests"] = build_gateway_registry(
                data_dir=data_dir,
                repo_root=repo_root,
                clock=clock,
                http_client=http_client,
            )
            names = cell["registry"].names()
            cell["global_map"] = {transport_name(name): name for name in names}
        except Exception as exc:  # fail fast: never leave ready unset
            cell["error"] = exc
        finally:
            ready.set()
        if "error" not in cell:
            loop.run_forever()

    thread = threading.Thread(target=_serve_tools, name="desk-gateway-tools")
    thread.daemon = True
    thread.start()
    if not ready.wait(timeout=120):
        raise RuntimeError("gateway tool loop did not start")
    if "error" in cell:
        raise cell["error"]
    return loop, cell


def create_server(
    config: GatewayConfig,
    *,
    clock: Clock | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> ThreadingHTTPServer:
    """Bind a threaded JSON-RPC server over an owner-thread registry."""
    active_clock = clock if clock is not None else WallClock()
    owner_loop, cell = _start_owner_loop(
        data_dir=config.data_dir,
        repo_root=config.repo_root,
        clock=active_clock,
        http_client=http_client,
    )
    server = ThreadingHTTPServer((config.host, config.port), _Handler)
    server.gateway_state = {  # type: ignore[attr-defined]
        "contracts_dir": Path(config.contracts_dir),
        "tokens": dict(config.tokens),
        "registry": cell["registry"],
        "manifests": cell["manifests"],
        "global_map": cell["global_map"],
        "owner_loop": owner_loop,
        "clock": active_clock,
        "shorts": short_to_seat(config.contracts_dir),
    }
    server.daemon_threads = True
    return server


def close_server(server: ThreadingHTTPServer) -> None:
    """Stop HTTP serving and the owner tool loop."""
    loop = server.gateway_state.get("owner_loop")  # type: ignore[attr-defined]
    server.shutdown()
    server.server_close()
    if loop is not None:
        loop.call_soon_threadsafe(loop.stop)
