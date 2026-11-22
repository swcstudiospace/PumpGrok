"""HOST-03: /livez and /readyz probes per D-09."""

from __future__ import annotations

import asyncio
import json
import urllib.request

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.health_server import HostedHealthServer

def _fetch(port: int, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


async def _run(status: dict, ready: bool, live: bool) -> tuple[tuple[int, str], tuple[int, str]]:
    clock = FixtureClock(start=1_700_000_000.0)
    server = HostedHealthServer(clock, lambda: status, lambda: ready, live=lambda: live)
    port = await server.start("127.0.0.1", 0)
    try:
        livez = await asyncio.to_thread(_fetch, port, "/livez")
        readyz = await asyncio.to_thread(_fetch, port, "/readyz")
        return livez, readyz
    finally:
        await server.stop()


def test_livez_200_while_loop_runs() -> None:
    livez, _ = asyncio.run(_run({"halted": False, "ledger_status": "CONSISTENT"}, True, True))
    assert livez[0] == 200


def test_livez_200_under_halt_and_kill() -> None:
    livez, readyz = asyncio.run(_run({"halted": True, "ledger_status": "CONSISTENT"}, True, True))
    assert livez[0] == 200
    assert readyz[0] == 200
    assert json.loads(livez[1])["halted"] is True
    assert json.loads(livez[1])["live"] is True


def test_readyz_503_on_failed_verification() -> None:
    _, readyz = asyncio.run(_run({"halted": False, "ledger_status": "INCONSISTENT"}, False, True))
    assert readyz[0] == 503
    body = json.loads(livez_body(readyz))
    assert body["ready"] is False


def livez_body(resp) -> str:
    return resp[1]
