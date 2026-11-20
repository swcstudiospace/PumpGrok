"""Forbidden key names abort startup (INV-C-08).

R-30 scopes ``refuse_forbidden_env`` to ``PUMPGROK_*`` names: bare
``PRIVATE_KEY``-style variables are ignored, not refused. Only
``PUMPGROK_*`` env var names containing ``PRIVATE_KEY``, ``SECRET_KEY``,
``SEED``, ``MNEMONIC``, ``PHANTOM``, ``WALLET_SECRET`` or ``KEYPAIR``
abort startup with exit 1 naming the key; the value is never printed.
``PUMPGROK_REPLAY__SEED`` is the one exemption.
"""

from __future__ import annotations

import os

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import ConfigError, load_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


NAMES = [
    "PUMPGROK_PRIVATE_KEY",
    "PUMPGROK_WALLET_PRIVATE_KEY",
    "PUMPGROK_SOLANA__SECRET_KEY",
    "PUMPGROK_MY_SEED_BACKUP",
    "PUMPGROK_MNEMONIC",
    "PUMPGROK_PHANTOM_AUTH",
    "PUMPGROK_WALLET_SECRET",  # pragma: allowlist secret: forbidden env-name fixture
    "PUMPGROK_KEYPAIR_PATH",  # pragma: allowlist secret: forbidden env-name fixture
    "PUMPGROK_DEPLOYER_KEYPAIR",
]


@pytest.mark.parametrize("name", NAMES)
def test_forbidden_key_names_abort_startup(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, capsys, name: str
) -> None:
    """INV-C-08: forbidden names abort startup naming the key, hiding the value."""
    planted = "PLANTED-VALUE-9f3k7z-no-echo"  # pragma: allowlist secret: planted no-echo value
    monkeypatch.setenv(name, planted)
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    assert name in message
    assert planted not in message

    code = main(["run", "--mode", "paper", "--once", "--replay", "tests/fixtures/replay/smoke"])
    assert code == 1
    err = capsys.readouterr().err
    assert name in err
    assert planted not in err


def test_replay_seed_stays_exempt(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-C-08: PUMPGROK_REPLAY__SEED is the one exemption."""
    monkeypatch.setenv("PUMPGROK_REPLAY__SEED", "7")
    assert load_settings().replay.seed == 7


def test_bare_forbidden_name_is_ignored(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """R-30: refuse_forbidden_env only scans PUMPGROK_* names; bare names load."""
    monkeypatch.setenv("PRIVATE_KEY", "PLANTED-VALUE-9f3k7z-no-echo")
    assert load_settings() is not None
