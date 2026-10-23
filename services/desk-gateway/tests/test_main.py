"""``python -m desk_gateway`` entrypoint behaviour (FOUND-003, TOOL-010, G4).

The three exit cases run the real module in-process with
``runpy.run_module("desk_gateway", run_name="__main__")``. The exit code is the ``SystemExit``
code that the module raises, and the message is read from captured stderr. The environment is
set with ``monkeypatch``, and the working directory and data dir are ``tmp_path``, so the repo
``var/`` is never touched.

The health case does not go through ``__main__``. It starts ``create_server`` on an ephemeral
port in a background thread, reads ``GET /healthz``, and shuts the server down.

This module does not import ``subprocess`` (INV-S-04 allowlist: ``cli.py`` and ``ci/`` only).
"""

from __future__ import annotations

import json
import os
import runpy
import threading
import urllib.request
from pathlib import Path
from typing import Any

import httpx
import pytest

from desk_gateway.config import GatewayConfig
from desk_gateway.server import close_server, create_server
from pumpgrok.config.settings import Settings
from pumpgrok.contracts.projection import default_contracts_dir
from pumpgrok.replay.clock import WallClock

REPO_ROOT = Path(__file__).resolve().parents[3]
EXIT_CONFIG = 1
EXIT_LIVE = 3
HTTP_OK = 200
HEALTH_BODY: dict[str, Any] = {"ok": True, "service": "desk-gateway"}


def _refusing(request: httpx.Request) -> httpx.Response:
    """No test may reach a real network; a request here is a bug."""
    return httpx.Response(500, json={"error": "network disabled in gateway tests"})


def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Drop every PUMPGROK_ and DESK_GATEWAY_ variable, then point the desk at tmp_path."""
    for name in list(os.environ):
        if name.startswith(("PUMPGROK_", "DESK_GATEWAY_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("DESK_GATEWAY_DATA_DIR", str(tmp_path / "desk"))
    monkeypatch.setenv("DESK_GATEWAY_REPO_ROOT", str(REPO_ROOT))
    monkeypatch.chdir(tmp_path)


def _run_entrypoint() -> int:
    """Run ``python -m desk_gateway`` in-process and return the exit code it raises."""
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("desk_gateway", run_name="__main__")
    code = excinfo.value.code
    assert isinstance(code, int), code
    return code


def test_entrypoint_answers_health_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch, tmp_path)
    config = GatewayConfig(
        host="127.0.0.1",
        port=0,
        contracts_dir=default_contracts_dir(),
        data_dir=tmp_path / "desk",
        repo_root=REPO_ROOT,
        tokens={},
        ledger_path=tmp_path / "ledger.sqlite",
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_refusing))
    server = create_server(
        config,
        settings=Settings(mode="paper"),
        clock=WallClock(),
        http_client=http_client,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        with urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=5) as response:
            status = response.status
            body = json.loads(response.read().decode())
        assert status == HTTP_OK
        assert body == HEALTH_BODY
    finally:
        close_server(server)
        thread.join(timeout=5)


def test_bad_port_exits_1_with_config_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clean_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DESK_GATEWAY_PORT", "not-a-port")
    assert _run_entrypoint() == EXIT_CONFIG
    assert "DESK_GATEWAY_PORT" in capsys.readouterr().err


def test_missing_operator_overlay_exits_1_with_config_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clean_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PUMPGROK_CONFIG", str(tmp_path / "absent.toml"))
    assert _run_entrypoint() == EXIT_CONFIG
    assert "operator overlay not found" in capsys.readouterr().err


def test_live_mode_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clean_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    assert _run_entrypoint() == EXIT_LIVE
    assert "live mode is refused" in capsys.readouterr().err
