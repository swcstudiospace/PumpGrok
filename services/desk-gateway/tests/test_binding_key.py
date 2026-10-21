"""Persisted doctor binding key (WR-06).

The key is created once with mode 0600 under the data dir, reused on every
later start, and a loose or malformed key file stops the process (fail
closed). A binding registered before a gateway restart must still verify
after it.
"""

from __future__ import annotations

import json
import stat
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import HTTP_OK, rpc_call

from desk_gateway.config import GatewayConfig
from desk_gateway.server import close_server, create_server
from pumpgrok.contracts.projection import default_contracts_dir, short_to_seat
from pumpgrok.core.binding_key import (
    BINDING_KEY_FILENAME,
    BindingKeyError,
    load_or_create_binding_key,
)
from pumpgrok.replay.clock import WallClock

KEY_BYTES = 32
OWNER_ONLY = 0o600
REPO_ROOT = Path(__file__).resolve().parents[3]


def _key_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_key_is_created_once_with_mode_0600(tmp_path: Path) -> None:
    key = load_or_create_binding_key(tmp_path)
    path = tmp_path / BINDING_KEY_FILENAME
    assert len(key) == KEY_BYTES
    assert _key_mode(path) == OWNER_ONLY
    assert load_or_create_binding_key(tmp_path) == key
    assert sorted(p.name for p in tmp_path.iterdir()) == [BINDING_KEY_FILENAME]


def test_distinct_data_dirs_get_distinct_keys(tmp_path: Path) -> None:
    assert load_or_create_binding_key(tmp_path / "a") != load_or_create_binding_key(tmp_path / "b")


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o660, 0o666])
def test_loose_permissions_refuse_to_start(tmp_path: Path, mode: int) -> None:
    load_or_create_binding_key(tmp_path)
    path = tmp_path / BINDING_KEY_FILENAME
    path.chmod(mode)
    with pytest.raises(BindingKeyError, match="refusing to start"):
        load_or_create_binding_key(tmp_path)


def test_symlinked_key_is_refused(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.key"
    elsewhere.write_text("00" * KEY_BYTES + "\n", encoding="ascii")
    elsewhere.chmod(OWNER_ONLY)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / BINDING_KEY_FILENAME).symlink_to(elsewhere)
    with pytest.raises(BindingKeyError):
        load_or_create_binding_key(data_dir)


@pytest.mark.parametrize("content", ["not-hex-zz\n", "abcd\n", ""])
def test_malformed_key_file_is_refused(tmp_path: Path, content: str) -> None:
    path = tmp_path / BINDING_KEY_FILENAME
    path.write_text(content, encoding="ascii")
    path.chmod(OWNER_ONLY)
    with pytest.raises(BindingKeyError):
        load_or_create_binding_key(tmp_path)


def _no_network(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"error": "network disabled in gateway tests"})


def _serve(data_dir: Path) -> Any:
    contracts_dir = default_contracts_dir()
    tokens = {short: f"fake_token_{short}" for short in short_to_seat(contracts_dir)}
    config = GatewayConfig(
        host="127.0.0.1",
        port=0,
        contracts_dir=contracts_dir,
        data_dir=data_dir,
        repo_root=REPO_ROOT,
        tokens=tokens,
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_no_network))
    server = create_server(config, clock=WallClock(), http_client=http_client)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}", tokens["chief"]


def _register(base_url: str, token: str, agent: str) -> dict[str, Any]:
    status, body = rpc_call(
        base_url,
        "chief",
        "tools/call",
        token,
        {
            "name": "desk_doctor",
            "arguments": {"action": "register", "agent_uuid": agent, "channel_id": "chan-1"},
        },
    )
    assert status == HTTP_OK, body
    assert body["result"]["isError"] is False, body
    decoded: dict[str, Any] = json.loads(body["result"]["content"][0]["text"])
    return decoded


def test_binding_survives_gateway_restart(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    server, base_url, token = _serve(data_dir)
    try:
        first = _register(base_url, token, "agent-restart")
    finally:
        close_server(server)
    assert first["ok"] is True, first

    server, base_url, token = _serve(data_dir)
    try:
        again = _register(base_url, token, "agent-restart")
    finally:
        close_server(server)
    assert again["ok"] is True, again
    assert again["rows"][0]["detail"] == "binding verified"


def test_gateway_refuses_to_start_on_loose_key(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    load_or_create_binding_key(data_dir)
    (data_dir / BINDING_KEY_FILENAME).chmod(0o644)
    with pytest.raises(BindingKeyError):
        _serve(data_dir)
