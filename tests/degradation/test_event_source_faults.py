"""Event-source faults stay local. No socket, no client library."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from pumpgrok.events.sources import SourceStatus, SourceSupervisor
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from harness.faults import FaultMode, FaultyEventSource, InjectedFault

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
