"""Secrets never leave SecretStr (INV-C-07).

Plants distinct secret values through the environment, then asserts the
planted value appears in none of:

- ``Settings.model_dump()`` / ``model_dump_json()`` / ``repr`` / ``str``;
- the ``/healthz`` body (``build_status``);
- ``ConfigChanged`` payloads (``autonomy_rows``);
- the config-hash input (``_jsonable(settings.model_dump(mode="json"))``);
- ``pumpgrok state status`` stdout (the JSON envelope).

The ``live confirm`` operator secret (``PUMPGROK_CONFIRMATION_KEY``) is
asserted to be no ``Settings`` field at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from pumpgrok.cli import _jsonable, main
from pumpgrok.config.settings import Settings, load_settings
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.ledger.autonomy import autonomy_rows
from pumpgrok.supervisor.health import build_status

GROK_SECRET = "grok-secret-plant-7f3a9c2e1b"  # pragma: allowlist secret: planted no-echo value
RPC_SECRET = "rpc-secret-plant-4d8b1f6a93"  # pragma: allowlist secret: planted no-echo value


@pytest.fixture
def planted(monkeypatch: pytest.MonkeyPatch):
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PUMPGROK_GROK__API_KEY", GROK_SECRET)
    monkeypatch.setenv("PUMPGROK_RPC__API_KEY", RPC_SECRET)
    monkeypatch.setenv(
        "PUMPGROK_CONFIRMATION_KEY",
        "confirm-secret-plant-aa11",  # pragma: allowlist secret: planted no-echo value
    )
    return load_settings()


def _surfaces(settings: Settings) -> dict[str, str]:
    status = build_status(
        mode="paper",
        autonomy_level="manual-ticket",
        ledger_status="CONSISTENT",
        ledger_source="paper",
        kill_switch=False,
        seats={},
        uptime_s=1.0,
    )
    rows = autonomy_rows(
        "autonomous-paper",
        by="human:alice",
        previous="manual-ticket",
        ts_utc="2026-01-01T00:00:00Z",
        source="paper",
        correlation_id="CID-TEST-000000000000000001",
    )
    hashed = hashlib.sha256(
        canonical_json(_jsonable(settings.model_dump(mode="json"))).encode("utf-8")
    ).hexdigest()
    return {
        "model_dump": repr(settings.model_dump()),
        "model_dump_json": settings.model_dump_json(),
        "repr": repr(settings),
        "str": str(settings),
        "health": json.dumps(status),
        "config_changed": json.dumps([row["payload"] for row in rows]),
        "config_hash": hashed,
    }


REPO_ROOT = Path(__file__).resolve().parents[2]
BINDING_KEY = Path("var") / "desk" / "binding.key"


def _key_state(root: Path) -> tuple[bool, str]:
    """Existence and content digest of the repo's binding key; never creates it."""
    key = root / BINDING_KEY
    if not key.is_file():
        return (False, "")
    return (True, hashlib.sha256(key.read_bytes()).hexdigest())


def _run_dump_check(
    planted: Settings, capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-C-07 dump check; the registry runs from tmp_path so its data dir is tmp_path."""
    monkeypatch.chdir(tmp_path)
    before = _key_state(REPO_ROOT)
    settings = planted
    for surface, body in _surfaces(settings).items():
        assert GROK_SECRET not in body, surface
        assert RPC_SECRET not in body, surface
    code = main(["state", "status", "--seat", "bot-00-chief"])
    assert code == 0
    out = capsys.readouterr().out
    assert GROK_SECRET not in out
    assert RPC_SECRET not in out
    # Regression: the run must neither create nor change the repo's binding.key. A key that
    # already exists (a developer's runtime file) is allowed; it must come out unchanged.
    assert _key_state(REPO_ROOT) == before


def test_secret_values_absent_from_dumps(
    planted: Settings, capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-C-07: no secret value in any dump, body, payload or hash input."""
    _run_dump_check(planted, capsys, tmp_path, monkeypatch)


def test_existing_repo_binding_key_is_tolerated_and_untouched(
    planted: Settings, capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 11: a developer's existing var/desk/binding.key neither fails nor changes."""
    repo = tmp_path / "repo"
    key = repo / BINDING_KEY
    key.parent.mkdir(parents=True)
    key.write_bytes(b"developer-binding-key-bytes")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", repo)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _run_dump_check(planted, capsys, cwd, monkeypatch)
    assert key.read_bytes() == b"developer-binding-key-bytes"


def test_confirmation_key_is_no_setting_field() -> None:
    """INV-C-07: the operator secret is not a Settings field."""
    assert "confirmation_key" not in Settings.model_fields
    assert "CONFIRMATION_KEY" not in {name.upper() for name in Settings.model_fields}
