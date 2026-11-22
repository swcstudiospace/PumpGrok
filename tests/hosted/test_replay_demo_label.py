"""HOST-15: every replay health body carries replay_demo true; unforgeable."""

from __future__ import annotations

import asyncio
import inspect
import json
import urllib.request

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.health_server import HostedHealthServer


def _fetch(port: int, path: str) -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))


async def _bodies() -> dict[str, dict]:
    clock = FixtureClock(start=1_700_000_000.0)
    server = HostedHealthServer(
        clock,
        lambda: {"halted": False, "ledger_status": "CONSISTENT"},
        lambda: True,
    )
    port = await server.start("127.0.0.1", 0)
    try:
        return {
            "livez": await asyncio.to_thread(_fetch, port, "/livez"),
            "readyz": await asyncio.to_thread(_fetch, port, "/readyz"),
            "metrics": await asyncio.to_thread(_fetch, port, "/metrics"),
        }
    finally:
        await server.stop()


def test_every_body_carries_replay_label() -> None:
    for name, body in asyncio.run(_bodies()).items():
        assert body["replay_demo"] is True, name
        assert body["ledger_source"] == "replay", name


def test_label_cannot_be_set_false() -> None:
    src = inspect.getsource(HostedHealthServer)
    assert "replay_demo" in src
    # No constructor knob exists: the label is server-set only.
    init_src = inspect.getsource(HostedHealthServer.__init__)
    assert "replay_demo" not in init_src
