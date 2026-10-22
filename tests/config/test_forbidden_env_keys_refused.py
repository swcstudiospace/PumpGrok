"""Forbidden key names abort startup (INV-C-08).

Any env var or TOML key whose name contains ``PRIVATE_KEY``,
``SECRET_KEY``, ``SEED``, ``MNEMONIC``, ``PHANTOM``, ``WALLET_SECRET``
or ``KEYPAIR`` aborts startup with exit 1 naming the key; the value is
never printed. ``PUMPGROK_REPLAY__SEED`` is the one exemption.
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
    "PRIVATE_KEY",
    "WALLET_PRIVATE_KEY",
    "SOLANA_SECRET_KEY",
    "MY_SEED_BACKUP",
    "PUMPGROK_MNEMONIC",
    "PHANTOM_AUTH",
    "PUMPGROK_WALLET_SECRET",  # pragma: allowlist secret: forbidden env-name fixture
    "PUMPGROK_KEYPAIR_PATH",  # pragma: allowlist secret: forbidden env-name fixture
    "DEPLOYER_KEYPAIR",
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
