"""Doctor probes of the served /healthz and /metrics endpoints (Phase 5, plan 05-07).

Probes use stdlib ``urllib`` (no curl in slim images). A probe is ``ok`` only
for HTTP 200; anything else (refused, 503 degraded, wrong port) is ``warn``.
Warnings never fail the report: ``pumpgrok doctor`` still exits 0.
"""

from __future__ import annotations

import asyncio
import json
import socket
import urllib.request
from pathlib import Path

from pumpgrok.config.settings import Settings
from pumpgrok.doctor import doctor_report, probe_served_endpoints
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.health import HealthServer
from pumpgrok.supervisor.scheduler import build_serve_replay

SMOKE = Path(__file__).resolve().parent / "fixtures" / "replay" / "smoke"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_probe_reports_unreachable_endpoints_as_warn() -> None:
    probes = probe_served_endpoints(_free_port())
    assert [probe.name for probe in probes] == ["/healthz", "/metrics"]
    assert all(probe.ok is False for probe in probes)
    assert all("warn" in probe.line() for probe in probes)


def test_probe_reports_served_endpoints_as_ok(tmp_path) -> None:
    _run_served_probe_test(tmp_path)


def _read_healthz(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as resp:
        return json.loads(resp.read())


def _run_served_probe_test(tmp_path) -> None:
    clock = FixtureClock(start=1_700_000_000.0)
    supervisor, metrics, store = build_serve_replay(
        SMOKE, Settings(mode="paper").filter, seed=20260101, clock=clock,
        ledger_path=tmp_path / "ledger.sqlite",
    )
    try:
        asyncio.run(supervisor.tick_once())
        server = HealthServer(
            clock, supervisor.health_status, supervisor.ready,
            get_metrics=metrics.exposition,
        )

        async def _run() -> tuple[list, int]:
            port = await server.start("127.0.0.1", 0)
            try:
                probes = await asyncio.to_thread(probe_served_endpoints, port)
                body = await asyncio.to_thread(_read_healthz, port)
                return probes, body
            finally:
                await server.stop()

        probes, body = asyncio.run(_run())
        assert all(probe.ok is True for probe in probes)
        assert all("ok " in probe.line() for probe in probes)
        assert body["ledger_source"] == "replay"
    finally:
        store.close()


def test_doctor_report_includes_endpoint_probes_when_unbound(
    capsys,
) -> None:
    lines = doctor_report(Settings(mode="paper"))
    assert any("/healthz" in line for line in lines)
    assert any("/metrics" in line for line in lines)
    assert lines[-1].startswith("doctor:")
