"""Event-source faults stay local. No socket, no client library."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from harness.faults import FaultMode, FaultyEventSource, InjectedFault
from pumpgrok.events.constants import BACKOFF_JITTER_S, BACKOFF_MAX_S
from pumpgrok.events.sources import SourceStatus, SourceSupervisor
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng

_REPO = Path(__file__).resolve().parents[2]
_SOURCES = _REPO / "src" / "pumpgrok" / "events" / "sources.py"


def test_faulty_disconnect_opens_no_socket(tmp_path: Path) -> None:
    source = FaultyEventSource(FaultMode.TIMEOUT)
    with pytest.raises(InjectedFault):
        asyncio.run(source.read())
    assert not hasattr(source, "socket")

    tree = ast.parse(_SOURCES.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".")[0])
    assert "httpx" not in roots
    assert "websockets" not in roots
    assert "socket" not in roots
    assert "tenacity" not in roots

    clock = FixtureClock(0.0)
    supervisor = SourceSupervisor(clock, make_rng(2), path=tmp_path / "events.sqlite")
    try:
        asyncio.run(source.read())
    except InjectedFault:
        supervisor.note_failure()
    assert supervisor.status_at(clock.now()) == SourceStatus.disconnected
    supervisor.close()


def test_long_outage_reconnect_stays_capped(tmp_path: Path) -> None:
    supervisor = SourceSupervisor(FixtureClock(0.0), make_rng(5), path=tmp_path / "events.sqlite")
    delays: list[float] = []
    try:
        for _ in range(2000):
            supervisor.note_failure()
            delays.append(supervisor.next_delay_s())
    finally:
        supervisor.close()
    assert len(delays) == 2000
    assert all(BACKOFF_MAX_S <= delay < BACKOFF_MAX_S + BACKOFF_JITTER_S for delay in delays[4:])
