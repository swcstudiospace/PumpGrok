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

Body: auth runs before the body is read. Content-Length must be a single
non-negative integer (400) and at most 1 MiB (413).
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import re
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
from pumpgrok.core.binding_key import load_or_create_binding_key
from pumpgrok.core.bot import BotManifest
from pumpgrok.core.errors import NotYetImplemented, OrderRejectedError, PumpgrokError
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.manifests import load_bot_manifests
from pumpgrok.core.registry import ToolRegistry
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.execution import build_adapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import Clock, WallClock
from pumpgrok.risk.alert_channel import AlertChannel, build_alert_channel
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import killswitch_file
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
from pumpgrok.tools.risk.kill_switch import build_kill_switch_tool, flatten_hook_for
from pumpgrok.tools.safety.score_report import build_score_report_tool

log = logging.getLogger("desk_gateway")

#: RISK-004: kill sources (env, file, alert channel) are polled on this fixed cycle.
KILL_POLL_INTERVAL_S = 5.0


class _ClosedNotifier(Notifier):
    """Refusing alert sink: the gateway owns no delivery path (fail-closed)."""

    async def send_telegram(self, chat_id: str, text: str) -> None:
        raise NotYetImplemented("notify.send needs Phase 4 sinks", tool="notify.alert")

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        raise NotYetImplemented("notify.send needs Phase 4 sinks", tool="notify.alert")


class GatewayRefusedError(RuntimeError):
    """The operator configuration is one the gateway refuses to serve."""


def refuse_live(settings: Settings) -> None:
    """Live mode is refused here exactly as the CLI live gate refuses it: paper only."""
    if settings.effective_mode != "paper":
        raise GatewayRefusedError("live mode is refused: the desk gateway serves paper only")


def build_gateway_registry(  # noqa: PLR0913 - keyword-only wiring inputs, one call site each
    *,
    settings: Settings,
    data_dir: Path,
    repo_root: Path,
    ledger_path: Path,
    telegram_token: str,
    alert_channel: AlertChannel | None = None,
    clock: Clock | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[ToolRegistry, dict[str, BotManifest], RiskEngine]:
    """Compose the full catalog registry the gateway projects (no tool logic).

    Every collaborator reads its configuration from the operator ``settings``, loaded by
    the same path the CLI uses (``PUMPGROK_CONFIG`` and profile overlays), so an overlay
    reaches the gateway risk budget, limits, adapter, doctor and safety thresholds.
    Wiring only: every catalog tool is registered exactly as the root least-privilege
    harness builds it, so ``registry.find`` enforces the same roster grants over HTTP as
    in-process. Returns the registry plus the ten seat manifests for ``find``.
    """
    refuse_live(settings)
    active_clock = clock if clock is not None else WallClock()
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    reg, _audits = build_registry(clock=active_clock, rng=secrets.SystemRandom())
    client = http_client if http_client is not None else httpx.AsyncClient()
    rpc = RpcClient(
        list(settings.rpc.endpoints),
        client,
        active_clock,
        secrets.SystemRandom(),
        api_key=settings.rpc.api_key,
    )
    store = LedgerStore(ledger_path)
    budget = settings.risk
    latch = killswitch_file(data_dir)
    engine = RiskEngine(
        store=store,
        budget=budget,
        ids=IdFactory(active_clock, secrets.SystemRandom()),
        clock=active_clock,
        limits=settings.limits,
        mode="paper",
        killswitch_path=latch,
        alert_channel=(
            alert_channel
            if alert_channel is not None
            else build_alert_channel(
                token=telegram_token, allowlist=settings.notify.allowlist, state_dir=data_dir
            )
        ),
    )
    adapter = build_adapter(
        settings,
        store=store,
        risk=engine,
        ids=IdFactory(active_clock, secrets.SystemRandom()),
        clock=active_clock,
        rng=secrets.SystemRandom(),
    )
    engine.attach_flatten_hook(
        flatten_hook_for(store, adapter.inflight_barrier, adapter.close_position)
    )
    bank = MemoryBank(data_dir / "memory.jsonl")
    mode = settings.effective_mode

    register_read_tools(reg, rpc)
    reg.register(build_score_report_tool(rpc, settings.safety.thresholds))
    reg.register(build_quote_tool(adapter, active_clock))
    reg.register(build_simulate_tool(adapter, active_clock))
    reg.register(build_place_tool(adapter, lambda: budget, active_clock))
    reg.register(build_cancel_tool(adapter, store, active_clock))
    reg.register(build_positions_tool(adapter, active_clock))
    reg.register(build_ledger_read_tool(store, active_clock))
    reg.register(build_ledger_write_tool(store, active_clock))
    reg.register(build_exposure_tool(store, active_clock))
    reg.register(build_pnl_tool(store, active_clock))
    reg.register(build_check_limits_tool(store, budget, active_clock))
    reg.register(build_drawdown_tool(store, budget, active_clock))
    reg.register(build_halt_status_tool(store, latch, active_clock, mode))
    reg.register(build_kill_switch_tool(store, active_clock, latch))
    reg.register(build_journal_append_tool(store, active_clock, data_dir / "journal"))
    reg.register(build_render_report_tool(store, active_clock, data_dir / "reports"))
    reg.register(
        build_alert_tool(
            _ClosedNotifier(allowlist=(), clock=active_clock, alert_file=data_dir / "alerts.jsonl"),
            active_clock,
        )
    )
    reg.register(build_brief_tool(store, bank, active_clock, None, mode))
    reg.register(build_docs_search_tool(repo_root, active_clock))
    reg.register(build_memory_retain_tool(bank, active_clock))
    reg.register(build_memory_recall_tool(bank, active_clock))
    reg.register(build_ownership_resolve_tool(repo_root / "ownership.yaml", active_clock))
    reg.register(build_receipt_check_tool(repo_root / "ci" / "gates", repo_root, active_clock))
    reg.register(build_event_emit_tool(store, active_clock, data_dir / "journal"))
    binding_key = load_or_create_binding_key(data_dir)
    reg.register(build_doctor_tool(settings, data_dir / "bindings", binding_key, active_clock))
    manifests = load_bot_manifests(default_contracts_dir())
    return reg, manifests, engine


async def _poll_kill_sources(engine: RiskEngine, interval_s: float) -> None:
    """RISK-004: poll the env, file and alert kill sources on a fixed cycle until cancelled.

    A failing cycle is logged and retried on the next tick; only cancellation (shutdown) stops it.
    """
    while True:
        try:
            await engine.poll_kill_sources()
        except Exception:
            log.exception("kill source poll failed; retrying next cycle")
        await asyncio.sleep(interval_s)


async def _cancel_and_wait(task: asyncio.Task[Any]) -> None:
    """Cancel one task on its own loop and wait for it to finish."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


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

_MAX_BODY_BYTES = 1 << 20  # 1 MiB; tool arguments are small JSON
_MAX_CONTENT_LENGTH_DIGITS = 7  # len(str(_MAX_BODY_BYTES)); longer can only be 400
_CONTENT_LENGTH_RE = re.compile(r"[0-9]+")

_REQUEST_TIMEOUT_S = 10.0  # per-socket-operation bound on every client connection


class _Handler(BaseHTTPRequestHandler):
    """JSON-RPC over POST with per-seat compare_digest auth."""

    # Socket timeout for every read and write on the connection: a stalled client is
    # closed within this bound instead of pinning a handler thread.
    timeout = _REQUEST_TIMEOUT_S

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

    def do_GET(self) -> None:
        # Liveness only: no tool, seat or ledger detail, and no token required.
        if self.path.split("?", 1)[0] == "/healthz":
            self._send_json(200, {"ok": True, "service": "desk-gateway"})
            return
        self._method_not_allowed()

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
        # Compare as bytes: hmac.compare_digest raises TypeError on non-ASCII str.
        presented_bytes = presented.encode() if presented is not None else None
        matched: str | None = None
        for seat_short, expected in tokens.items():
            if presented_bytes is not None and hmac.compare_digest(
                presented_bytes, expected.encode()
            ):
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

    def _declared_length(self) -> int | None:
        """Return the single declared body length, or None when it is malformed."""
        values = self.headers.get_all("Content-Length")
        if not values:
            return 0
        value = values[0].strip()
        if len(values) != 1 or len(value) > _MAX_CONTENT_LENGTH_DIGITS:
            return None
        if _CONTENT_LENGTH_RE.fullmatch(value) is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def do_POST(self) -> None:
        state = self.server.gateway_state  # type: ignore[attr-defined]
        short = _short_from_path(self.path)
        seat_id = state["shorts"].get(short) if short else None
        if seat_id is None:
            self._send_json(404, {"error": {"code": "unknown_seat", "message": "unknown seat"}})
            log.info("seat=%s status=%s", short, 404)
            return
        denied = self._authenticate(short, state["tokens"])
        if denied is not None:
            self._send_json(denied, self._auth_error_body(denied))
            log.info("seat=%s status=%s", short, denied)
            return
        length = self._declared_length()
        if length is None:
            self._send_json(
                400,
                {
                    "error": {
                        "code": "bad_length",
                        "message": "Content-Length must be a non-negative integer",
                    }
                },
            )
            log.info("seat=%s status=%s", short, 400)
            return
        if length > _MAX_BODY_BYTES:
            self._send_json(
                413,
                {
                    "error": {
                        "code": "body_too_large",
                        "message": f"body exceeds {_MAX_BODY_BYTES} bytes",
                    }
                },
            )
            log.info("seat=%s status=%s", short, 413)
            return
        raw = self.rfile.read(length) if length > 0 else b""
        self._handle_rpc(state, short, seat_id, raw)

    def _handle_rpc(
        self, state: dict[str, Any], short: str | None, seat_id: str, raw: bytes
    ) -> None:
        """Parse one JSON-RPC envelope and answer the supported methods."""
        try:
            envelope = json.loads(raw.decode() or "null")
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
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
                except OrderRejectedError as exc:
                    return None, _error_result(exc.reason, exc.detail)

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
        # A refused order (exec.place status "rejected") is an error on the wire, never a
        # success envelope; the refusal reason is the MCP code (TOOL-004).
        rejected = dumped.get("status") == "rejected"
        envelope: dict[str, Any] = {
            "content": [{"type": "text", "text": json.dumps(dumped)}],
            "isError": rejected,
        }
        if rejected:
            envelope["code"] = str(dumped.get("reason") or "rejected")
        return envelope


_CALL_TIMEOUT_S = 120.0
_CLOSE_TIMEOUT_S = 10.0


def _start_owner_loop(  # noqa: PLR0913 - keyword-only wiring inputs, one call site
    *,
    settings: Settings,
    data_dir: Path,
    repo_root: Path,
    ledger_path: Path,
    telegram_token: str,
    alert_channel: AlertChannel | None,
    kill_poll_interval_s: float,
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
            cell["registry"], cell["manifests"], cell["engine"] = build_gateway_registry(
                settings=settings,
                data_dir=data_dir,
                repo_root=repo_root,
                ledger_path=ledger_path,
                telegram_token=telegram_token,
                alert_channel=alert_channel,
                clock=clock,
                http_client=http_client,
            )
            names = cell["registry"].names()
            cell["global_map"] = {transport_name(name): name for name in names}
            # RISK-004: an idle gateway must still read KILL lines, so the poll runs on this loop.
            cell["kill_poll_task"] = loop.create_task(
                _poll_kill_sources(cell["engine"], kill_poll_interval_s)
            )
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


def create_server(  # noqa: PLR0913 - keyword-only wiring inputs, one call site
    config: GatewayConfig,
    *,
    settings: Settings,
    clock: Clock | None = None,
    http_client: httpx.AsyncClient | None = None,
    alert_channel: AlertChannel | None = None,
    kill_poll_interval_s: float = KILL_POLL_INTERVAL_S,
) -> ThreadingHTTPServer:
    """Bind a threaded JSON-RPC server over an owner-thread registry built from ``settings``."""
    active_clock = clock if clock is not None else WallClock()
    owner_loop, cell = _start_owner_loop(
        settings=settings,
        data_dir=config.data_dir,
        repo_root=config.repo_root,
        ledger_path=config.ledger_path,
        telegram_token=config.telegram_token,
        alert_channel=alert_channel,
        kill_poll_interval_s=kill_poll_interval_s,
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
        "kill_poll_task": cell["kill_poll_task"],
        "clock": active_clock,
        "shorts": short_to_seat(config.contracts_dir),
    }
    server.daemon_threads = True
    return server


def close_server(server: ThreadingHTTPServer) -> None:
    """Stop the kill poll, HTTP serving and the owner tool loop, in that order."""
    state = server.gateway_state  # type: ignore[attr-defined]
    loop = state.get("owner_loop")
    poll_task = state.get("kill_poll_task")
    if loop is not None and poll_task is not None:
        future = asyncio.run_coroutine_threadsafe(_cancel_and_wait(poll_task), loop)
        future.result(timeout=_CLOSE_TIMEOUT_S)
    server.shutdown()
    server.server_close()
    if loop is not None:
        loop.call_soon_threadsafe(loop.stop)
