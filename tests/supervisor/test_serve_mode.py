"""Serve mode: replay loop serving /healthz and /metrics (Phase 5, plan 05-07).

The serve path replays a recorded dataset in a loop (``ledger_source=replay``,
never live data) while ``HealthServer`` serves the supervisor status and the
Prometheus exposition. The one-shot ``--once --replay`` path stays intact.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import FilterSettings
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.health import HealthServer
from pumpgrok.supervisor.metrics import NINE_FAMILIES
from pumpgrok.supervisor.scheduler import ROSTER, build_serve_replay

SMOKE = Path(__file__).resolve().parent.parent / "fixtures" / "replay" / "smoke"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip PUMPGROK_* so each test sets exactly what it needs."""
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def root_handlers() -> Iterator[None]:
    """main() installs a handler bound to the test's stderr; remove it afterwards."""
    root = logging.getLogger()
    saved = list(root.handlers)
    yield
    for handler in list(root.handlers):
        if handler not in saved:
            root.removeHandler(handler)


def _settings_kwargs() -> dict:
    return {"filter": FilterSettings(), "seed": 20260101}


async def _fetch(url: str) -> tuple[int, bytes, str | None]:
    def _get() -> tuple[int, bytes, str | None]:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type")

    return await asyncio.to_thread(_get)


def test_serve_health_body_is_labelled_replay(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_700_000_000.0)
    supervisor, _metrics, store = build_serve_replay(
        SMOKE,
        _settings_kwargs()["filter"],
        seed=20260101,
        clock=clock,
        ledger_path=tmp_path / "ledger.sqlite",
    )
    try:
        body = supervisor.health_status()
        assert body["ledger_source"] == "replay"
        assert body["mode"] == "paper"
    finally:
        store.close()


def test_serve_tick_runs_all_ten_seats(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_700_000_000.0)
    supervisor, metrics, store = build_serve_replay(
        SMOKE,
        _settings_kwargs()["filter"],
        seed=20260101,
        clock=clock,
        ledger_path=tmp_path / "ledger.sqlite",
    )
    try:
        outcomes = asyncio.run(supervisor.tick_once())
        assert set(outcomes) == set(ROSTER)
        assert supervisor.ready() is True
        assert b"pumpgrok_cycle_seconds" in metrics.exposition()
    finally:
        store.close()


def test_serve_forever_returns_zero_once_stopped(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_700_000_000.0)
    supervisor, _metrics, store = build_serve_replay(
        SMOKE,
        _settings_kwargs()["filter"],
        seed=20260101,
        clock=clock,
        ledger_path=tmp_path / "ledger.sqlite",
    )
    try:
        supervisor.request_stop("test")
        assert asyncio.run(supervisor.serve_forever()) == 0
    finally:
        store.close()


def test_serve_binds_port_and_serves_both_endpoints(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_700_000_000.0)
    supervisor, metrics, store = build_serve_replay(
        SMOKE,
        _settings_kwargs()["filter"],
        seed=20260101,
        clock=clock,
        ledger_path=tmp_path / "ledger.sqlite",
    )
    try:
        asyncio.run(supervisor.tick_once())
        server = HealthServer(
            clock,
            supervisor.health_status,
            supervisor.ready,
            get_metrics=metrics.exposition,
        )

        async def _run() -> tuple[int, bytes, int, bytes, str | None]:
            port = await server.start("127.0.0.1", 0)
            try:
                code, body, _ = await _fetch(f"http://127.0.0.1:{port}/healthz")
                mcode, mbody, mtype = await _fetch(f"http://127.0.0.1:{port}/metrics")
                return code, body, mcode, mbody, mtype
            finally:
                await server.stop()

        code, body, mcode, mbody, mtype = asyncio.run(_run())
        assert code == 200
        assert json.loads(body)["ledger_source"] == "replay"
        assert mcode == 200
        for family in NINE_FAMILIES:
            assert family.encode() in mbody, family
        assert mtype is not None and "text/plain" in mtype
    finally:
        store.close()


def test_serve_cli_needs_a_replay_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--serve"]) == 5
    assert not (tmp_path / "var").exists()


def test_serve_cli_rejects_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--serve", "--once", "--replay", str(SMOKE)]) == 5
    assert not (tmp_path / "var").exists()


def test_serve_cli_needs_a_health_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--serve", "--replay", str(SMOKE)]) == 1
    assert "PUMPGROK_HEALTH__PORT" in capsys.readouterr().err
    assert not (tmp_path / "var").exists()


def test_one_shot_still_exits_zero_without_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 0


def test_serve_snapshot_and_body_reflect_kill_switch(tmp_path: Path) -> None:
    """WR-04: an engaged kill switch trips the gauge and the health body together."""
    clock = FixtureClock(start=1_700_000_000.0)
    supervisor, metrics, store = build_serve_replay(
        SMOKE,
        _settings_kwargs()["filter"],
        seed=20260101,
        clock=clock,
        ledger_path=tmp_path / "ledger.sqlite",
    )
    try:
        assert supervisor.health_status()["kill_switch"] is False
        assert "pumpgrok_kill_switch 0.0" in metrics.exposition().decode("utf-8")
        store.append(
            ts_utc=format_ts_utc(clock.now()),
            source="replay",
            correlation_id="desk",
            idempotency_key="killswitch|test|set",
            type="KillSwitchSet",
            payload={"source": "replay", "origin": "tool", "reason": "test trip"},
        )
        body = supervisor.health_status()
        assert body["kill_switch"] is True
        assert body["status"] == "degraded"
        assert "pumpgrok_kill_switch 1.0" in metrics.exposition().decode("utf-8")
        store.append(
            ts_utc=format_ts_utc(clock.now()),
            source="replay",
            correlation_id="desk",
            idempotency_key="killswitch|test|cleared",
            type="KillSwitchCleared",
            payload={"source": "replay", "cleared_by": "human:tester"},
        )
        assert supervisor.health_status()["kill_switch"] is False
        assert "pumpgrok_kill_switch 0.0" in metrics.exposition().decode("utf-8")
    finally:
        store.close()
