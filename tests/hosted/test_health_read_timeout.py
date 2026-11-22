"""HOST-12: connections that never complete a request are closed within the timeout."""

from __future__ import annotations

import asyncio
import socket
import time

from pumpgrok.replay.clock import WallClock
from pumpgrok.supervisor.health_server import DEFAULT_READ_TIMEOUT_S, HostedHealthServer


def test_default_read_timeout_is_five_seconds() -> None:
    assert DEFAULT_READ_TIMEOUT_S == 5.0


async def _main() -> float:
    clock = WallClock()
    server = HostedHealthServer(
        clock,
        lambda: {"halted": False, "ledger_status": "CONSISTENT"},
        lambda: True,
        read_timeout_s=0.2,
    )
    port = await server.start("127.0.0.1", 0)
    try:
        start = time.monotonic()

        def _probe() -> bytes:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                sock.settimeout(3)
                return sock.recv(65536)

        data = await asyncio.to_thread(_probe)
        assert data == b"", "timed-out connection must close with no response"
        return time.monotonic() - start
    finally:
        await server.stop()


def test_incomplete_request_closed_within_timeout() -> None:
    elapsed = asyncio.run(_main())
    assert elapsed < 3.0
