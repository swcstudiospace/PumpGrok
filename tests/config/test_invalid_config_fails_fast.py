"""Invalid configuration fails fast with exit 1 (INV-C-05).

Each invalid configuration raises ``ConfigError`` whose problems read
``loc: type`` (inputs dropped, values never echoed), and the CLI maps
that to exit 1 with one ``  - loc: type`` line per problem.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import ConfigError, load_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


SMOKE = str(Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "replay" / "smoke")
CASES = [
    ("PUMPGROK_RISK__MAX_TRADE_FRACTION", "not-a-number", "risk.max_trade_fraction"),
    ("PUMPGROK_RISK__MAX_TRADE_FRACTION", "2.5", "risk.max_trade_fraction"),
    (
        "PUMPGROK_RISK__MAX_TOKEN_FRACTION",
        "-0.1",
        "risk.max_token_fraction",
    ),  # pragma: allowlist secret: long setting name trips entropy
    ("PUMPGROK_RISK__DAILY_LOSS_HALT_FRACTION", "0.06", "risk.daily_loss_halt_fraction"),
    (
        "PUMPGROK_RISK__LIQUIDITY_FLOOR_MULTIPLE",
        "0",
        "risk.liquidity_floor_multiple",
    ),
    (
        "PUMPGROK_RISK__PARTIAL_FILL_FRACTION",
        "1.5",
        "risk.partial_fill_fraction",
    ),
    ("PUMPGROK_EXITS__MAX_HOLD_SECONDS", "soon", "exits.max_hold_seconds"),
    ("PUMPGROK_PROFILE", "staging", "unknown PUMPGROK_PROFILE: staging"),
]


@pytest.mark.parametrize(("env_name", "env_value", "loc"), CASES)
def test_invalid_config_exit_1(
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    env_name: str,
    env_value: str,
    loc: str,
) -> None:
    """INV-C-05: invalid configs fail fast with a loc line and exit 1."""
    monkeypatch.setenv(env_name, env_value)
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert any(loc in problem for problem in excinfo.value.problems), excinfo.value.problems

    code = main(["run", "--mode", "paper", "--once", "--replay", SMOKE])
    assert code == 1
    err = capsys.readouterr().err
    assert loc in err


def test_unknown_key_reports_its_name(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-C-05: unknown keys fail closed naming the key."""
    monkeypatch.setenv("PUMPGROK_BOGUS", "1")
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "PUMPGROK_BOGUS" in str(excinfo.value)
