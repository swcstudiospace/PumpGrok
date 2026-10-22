"""Health and readiness: /healthz, /readyz, and var/health.json.

Vendor contract (ops.py:299-358, pipeline.py:392-419): ``GET /healthz``
returns JSON, ``200`` iff ``status == "ok"`` else ``503``; the keys are the
vendor ``status()`` keys plus the supervisor additions from
paper-engine.md 6.6 (autonomy level, ledger status/source, kill switch,
breakers, per-seat freshness, equity, drawdown, data age). ``GET /readyz``
returns ``200`` only after the ledger reconciled CONSISTENT and every seat
completed one cycle. ``GET /metrics`` returns the Prometheus exposition bytes
(Phase 5, OBS-003) with the exposition content type; only GET is served.

``var/health.json`` carries the same body, written atomically (tmp +
``os.replace`` via ``atomic_write_json``, R26) every
``health.file_interval_s = 10`` virtual seconds.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from pumpgrok.core.atomic_write import atomic_write_json
from pumpgrok.core.ids import Clock
from pumpgrok.supervisor.metrics import EXPOSITION_CONTENT_TYPE

log = logging.getLogger(__name__)

#: Atomic rewrite cadence for var/health.json (virtual seconds).
HEALTH_FILE_INTERVAL_S = 10.0


def build_status(
    *,
    mode: str,
    autonomy_level: str,
    ledger_status: str,
    ledger_source: str,
    kill_switch: bool,
    seats: Mapping[str, Mapping[str, Any]],
    uptime_s: float,
    open_positions: int = 0,
    halted: bool = False,
    breaker: str = "closed",
    breakers: Mapping[str, str] | None = None,
    equity_lamports: int = 0,
    drawdown_pct: float = 0.0,
    data_age_s: float = 0.0,
    ledger_seq: int = 0,
) -> dict[str, Any]:
    """Build the /healthz body. ``status`` is ok/degraded/stopped."""
    stale = any(bool(info.get("stale", False)) for info in seats.values())
    degraded = ledger_status != "CONSISTENT" or stale or halted or kill_switch or breaker == "open"
    return {
        "status": "degraded" if degraded else "ok",
        "mode": mode,
        "uptime_seconds": round(max(0.0, uptime_s), 3),
        "stalled": stale,
        "open_positions": open_positions,
        "halted": halted,
        "breaker": breaker,
        "breakers": dict(breakers or {}),
        "autonomy_level": autonomy_level,
        "ledger_status": ledger_status,
        "ledger_source": ledger_source,
        "ledger_seq": ledger_seq,
        "kill_switch": kill_switch,
        "seats": {seat: dict(info) for seat, info in seats.items()},
        "equity_lamports": equity_lamports,
        "drawdown_pct": drawdown_pct,
        "data_age_s": round(max(0.0, data_age_s), 3),
    }


def is_ok(status: Mapping[str, Any]) -> bool:
    """Vendor contract: 200 iff status == ok."""
    return status.get("status") == "ok"


def write_health_json(path: str, status: Mapping[str, Any]) -> None:
    """Atomically rewrite the health file (R26); raises OSError loudly."""
    atomic_write_json(path, dict(status))


def _reason(status: int) -> str:
    if status == 200:
        return "OK"
    if status == 405:
        return "Method Not Allowed"
    return "Service Unavailable"


class HealthServer:
    """Minimal asyncio HTTP server for /healthz, /readyz and /metrics."""

    def __init__(
        self,
        clock: Clock,
        get_status: Callable[[], Mapping[str, Any]],
        is_ready: Callable[[], bool],
        get_metrics: Callable[[], bytes] | None = None,
    ) -> None:
        self._clock = clock
        self._get_status = get_status
        self._is_ready = is_ready
        self._get_metrics = get_metrics
        self._server: asyncio.AbstractServer | None = None

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        """Bind and serve; returns the bound port."""
        self._server = await asyncio.start_server(self._handle, host, port)
        bound = self._server.sockets[0].getsockname()[1] if self._server.sockets else port
        log.info("health listening on %s:%d", host, bound)
        return int(bound)

    async def stop(self) -> None:
        """Stop serving; never raises."""
        if self._server is None:
            return
        self._server.close()
        with contextlib.suppress(Exception):
            await self._server.wait_closed()
        self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await reader.read(65536)
            path = self._path_of(request)
            if path == "/metrics":
                if self._method_of(request) != "GET":
                    self._respond(writer, 405, {"error": "method not allowed"})
                elif self._get_metrics is None:
                    self._respond(writer, 503, {"metrics": False})
                else:
                    self._respond_bytes(
                        writer, 200, self._get_metrics(), EXPOSITION_CONTENT_TYPE
                    )
            elif path == "/readyz":
                code = 200 if self._is_ready() else 503
                self._respond(writer, code, {"ready": self._is_ready()})
            else:
                status = dict(self._get_status())
                code = 200 if is_ok(status) else 503
                self._respond(writer, code, status)
        except Exception as exc:
            log.warning("health request failed: %s", exc)
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    @staticmethod
    def _path_of(request: bytes) -> str:
        try:
            line = request.split(b"\r\n", 1)[0].decode("latin-1")
            parts = line.split(" ")
            return parts[1] if len(parts) > 1 else "/healthz"
        except Exception:
            return "/healthz"

    @staticmethod
    def _method_of(request: bytes) -> str:
        """Request method; tolerant default GET mirrors _path_of (never evals bytes)."""
        try:
            line = request.split(b"\r\n", 1)[0].decode("latin-1")
            parts = line.split(" ")
            return parts[0].upper() if parts and parts[0] else "GET"
        except Exception:
            return "GET"

    @staticmethod
    def _respond(writer: asyncio.StreamWriter, code: int, body: Mapping[str, Any]) -> None:
        payload = json.dumps(dict(body)).encode("utf-8")
        head = (
            f"HTTP/1.1 {code} {_reason(code)}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")
        writer.write(head + payload)

    @staticmethod
    def _respond_bytes(
        writer: asyncio.StreamWriter, code: int, payload: bytes, content_type: str
    ) -> None:
        """Serve pre-rendered bytes (the /metrics exposition); never json.dumps them."""
        head = (
            f"HTTP/1.1 {code} {_reason(code)}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")
        writer.write(head + payload)
