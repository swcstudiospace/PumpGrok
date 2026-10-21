"""Offline guarantee (T-01-52) and degraded-mode injection (plan 01-05, task 2)."""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest
import websockets
import websockets.asyncio.client

from harness import NetworkBlocked
from harness.faults import FaultInjector, FaultMode, InjectedFault, InjectedRateLimit
from pumpgrok.replay import load_dataset

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "pumpgrok"
SMOKE = Path(__file__).resolve().parent / "fixtures" / "replay" / "smoke"


async def test_unmocked_async_httpx_request_is_blocked() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(NetworkBlocked):
            await client.get("https://example.invalid/resource")


def test_unmocked_sync_httpx_request_is_blocked() -> None:
    with httpx.Client() as client, pytest.raises(NetworkBlocked):
        client.get("https://example.invalid/resource")


async def test_mock_transport_still_serves_recorded_responses() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.invalid/resource")
    assert response.json() == {"ok": True}


def test_websocket_connect_is_blocked_on_modern_path() -> None:
    with pytest.raises(NetworkBlocked):
        websockets.asyncio.client.connect("wss://example.invalid/feed")


def test_websocket_connect_is_blocked_on_top_level_alias() -> None:
    with pytest.raises(NetworkBlocked):
        websockets.connect("wss://example.invalid/feed")


def test_no_src_module_imports_legacy_websockets_path() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("websockets.legacy") or (
                    node.module == "websockets" and any(a.name == "connect" for a in node.names)
                ):
                    offenders.append(f"{path}:{node.lineno}: from {node.module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("websockets.legacy"):
                        offenders.append(f"{path}:{node.lineno}: import {alias.name}")
            elif (
                isinstance(node, ast.Attribute)
                and node.attr == "connect"
                and isinstance(node.value, ast.Name)
                and node.value.id == "websockets"
            ):
                offenders.append(f"{path}:{node.lineno}: websockets.connect")
    assert offenders == []


def _events() -> list[dict[str, object]]:
    return list(load_dataset(SMOKE).events)


def test_stale_mode_rewinds_the_event_and_marks_it() -> None:
    original = _events()
    out = list(FaultInjector(FaultMode.STALE, at_index=1).apply(original))
    assert len(out) == len(original)
    assert out[0] == original[0]
    assert out[1]["fault"] == "stale"
    assert out[1]["ts_utc"] < original[1]["ts_utc"]
    assert out[2:] == original[2:]


def test_timeout_mode_raises_builtin_timeout_after_earlier_events() -> None:
    seen: list[dict[str, object]] = []
    with pytest.raises(TimeoutError):
        for event in FaultInjector(FaultMode.TIMEOUT, at_index=2).apply(_events()):
            seen.append(event)
    assert len(seen) == 2


def test_rate_limit_mode_raises_429_with_retry_hint() -> None:
    with pytest.raises(InjectedRateLimit) as excinfo:
        list(FaultInjector(FaultMode.RATE_LIMIT, at_index=0, retry_after_s=2.5).apply(_events()))
    assert excinfo.value.status == 429
    assert excinfo.value.retry_after_s == 2.5


def test_raise_mode_raises_injected_fault() -> None:
    with pytest.raises(InjectedFault):
        list(FaultInjector(FaultMode.RAISE, at_index=3).apply(_events()))


def test_unwritable_mode_leaves_events_and_fails_the_sink(tmp_path: Path) -> None:
    injector = FaultInjector(FaultMode.UNWRITABLE)
    assert list(injector.apply(_events())) == _events()
    target = tmp_path / "sink.jsonl"
    with pytest.raises(PermissionError), injector.open_sink(target):
        pass
    assert not target.exists()


def test_writable_sink_opens_when_not_injected(tmp_path: Path) -> None:
    target = tmp_path / "sink.jsonl"
    with FaultInjector(FaultMode.RAISE).open_sink(target) as fh:
        fh.write("ok\n")
    assert target.read_text() == "ok\n"


def test_negative_index_is_rejected() -> None:
    with pytest.raises(ValueError):
        FaultInjector(FaultMode.RAISE, at_index=-1)
