"""HOST-11: loopback bind default; /metrics 401 without token beyond loopback."""

from __future__ import annotations

import asyncio
import json
import urllib.request

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.health_server import HostedHealthServer, is_loopback_bind


def _fetch(port: int) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


async def _run(bind_host: str, token: str) -> tuple[int, dict]:
    clock = FixtureClock(start=1_700_000_000.0)
    server = HostedHealthServer(
        clock,
        lambda: {"halted": False, "ledger_status": "CONSISTENT"},
        lambda: True,
        bind_host=bind_host,
        metrics_token=token,
    )
    port = await server.start("127.0.0.1", 0)
    try:
        return await asyncio.to_thread(_fetch, port)
    finally:
        await server.stop()


def test_loopback_bind_helper() -> None:
    assert is_loopback_bind("127.0.0.1")
    assert not is_loopback_bind("0.0.0.0")


def test_metrics_401_without_token_beyond_loopback() -> None:
    code, body = asyncio.run(_run("0.0.0.0", ""))
    assert code == 401
    assert body["metrics"] is False


def test_metrics_not_401_with_token() -> None:
    code, _ = asyncio.run(_run("0.0.0.0", "tok"))
    assert code != 401


def test_metrics_loopback_not_401() -> None:
    code, _ = asyncio.run(_run("127.0.0.1", ""))
    assert code != 401
