"""Hosted health server: /livez, /readyz, /metrics only (HOST-03, HOST-05).

Any other path answers 404 with an empty body. /livez is 200 while the loop
runs whatever the halt/kill state; /readyz is 503 when the last per-tick
ledger verification failed or the tick is stale; a halted desk is 200 on
both with the halt in the body (D-09). ledger_status always comes from the
tick verification callback, never a constant.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from pumpgrok.core.ids import Clock

log = logging.getLogger(__name__)


def shutdown_exit_code(failed: bool) -> int:
    """HOST-06: a failed final snapshot/export/health write exits non-zero."""
    return 1 if failed else 0


#: Default read timeout for slow/inscomplete requests (HOST-12).
DEFAULT_READ_TIMEOUT_S = 5.0

#: Hosts considered loopback (HOST-11).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_loopback_bind(host: str) -> bool:
    """True iff the bind host is loopback."""
    return host.strip().lower() in LOOPBACK_HOSTS


class HostedHealthServer:
    """Strict-route asyncio server for the hosted surface."""

    def __init__(
        self,
        clock: Clock,
        get_status: Callable[[], Mapping[str, Any]],
        is_ready: Callable[[], bool],
        live: Callable[[], bool] | None = None,
        *,
        bind_host: str = "127.0.0.1",
        metrics_token: str = "",
        read_timeout_s: float = DEFAULT_READ_TIMEOUT_S,
    ) -> None:
        self._clock = clock
        self._get_status = get_status
        self._is_ready = is_ready
        self._live = live or (lambda: True)
        self._bind_host = bind_host
        self._metrics_token = metrics_token
        self._read_timeout_s = read_timeout_s
        self._server: asyncio.AbstractServer | None = None

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        """Bind and serve; returns the bound port."""
        self._server = await asyncio.start_server(self._handle, host, port)
        bound = self._server.sockets[0].getsockname()[1] if self._server.sockets else port
        log.info("hosted health listening on %s:%d", host, bound)
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
            request = await asyncio.wait_for(reader.read(65536), timeout=self._read_timeout_s)
            path = self._path_of(request)
            status = dict(self._get_status())
            if path == "/livez":
                body = {
                    "live": True,
                    "halted": bool(status.get("halted", False)),
                    "replay_demo": True,
                    "ledger_source": "replay",
                }
                code = 200 if self._live() else 503
                self._respond(writer, code, body)
            elif path == "/readyz":
                ready = bool(self._is_ready())
                body = {
                    "ready": ready,
                    "halted": bool(status.get("halted", False)),
                    "ledger_status": str(status.get("ledger_status", "UNKNOWN")),
                    "replay_demo": True,
                    "ledger_source": "replay",
                }
                self._respond(writer, 200 if ready else 503, body)
            elif path == "/metrics":
                if not is_loopback_bind(self._bind_host) and not self._metrics_token:
                    self._respond(writer, 401, {"metrics": False, "auth": "required"})
                else:
                    self._respond(writer, 503, {"metrics": False, "note": "no exporter", "replay_demo": True, "ledger_source": "replay"})
            else:
                self._respond_empty(writer, 404)
        except TimeoutError:
            log.warning("hosted health read timeout")
        except Exception as exc:
            log.warning("hosted health request failed: %s", exc)
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    @staticmethod
    def _path_of(request: bytes) -> str:
        try:
            line = request.split(b"\r\n", 1)[0].decode("latin-1")
            parts = line.split(" ")
            return parts[1] if len(parts) > 1 else "/"
        except Exception:
            return "/"

    @staticmethod
    def _respond(writer: asyncio.StreamWriter, code: int, body: Mapping[str, Any]) -> None:
        payload = json.dumps(dict(body)).encode("utf-8")
        head = (
            f"HTTP/1.1 {code} {'OK' if code == 200 else 'Service Unavailable'}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")
        writer.write(head + payload)

    @staticmethod
    def _respond_empty(writer: asyncio.StreamWriter, code: int) -> None:
        head = (
            f"HTTP/1.1 {code} Not Found\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: 0\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")
        writer.write(head)
