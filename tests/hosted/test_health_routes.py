"""HOST-05: only /livez, /readyz, /metrics; everything else 404 empty."""

from __future__ import annotations

import asyncio
import urllib.request

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.health_server import HostedHealthServer


def _fetch(port: int, path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


async def _run() -> tuple[tuple[int, bytes], tuple[int, bytes], tuple[int, bytes]]:
    clock = FixtureClock(start=1_700_000_000.0)
    server = HostedHealthServer(
        clock,
        lambda: {"halted": False, "ledger_status": "CONSISTENT"},
        lambda: True,
    )
    port = await server.start("127.0.0.1", 0)
    try:
        livez = await asyncio.to_thread(_fetch, port, "/livez")
        legacy = await asyncio.to_thread(_fetch, port, "/healthz")
        unknown = await asyncio.to_thread(_fetch, port, "/nope")
        return livez, legacy, unknown
    finally:
        await server.stop()


def test_three_routes_exist() -> None:
    livez, _, _ = asyncio.run(_run())
    assert livez[0] == 200


def test_healthz_removed() -> None:
    _, legacy, _ = asyncio.run(_run())
    assert legacy[0] == 404
    assert legacy[1] == b""


def test_unknown_path_404_empty_body() -> None:
    _, _, unknown = asyncio.run(_run())
    assert unknown[0] == 404
    assert unknown[1] == b""
