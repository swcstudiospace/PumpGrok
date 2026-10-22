"""Overlay resolution order and CLI/env/TOML precedence (INV-C-04, INV-C-10).

- TOML ``execution.mode = "live"`` alone never starts live (precondition
  2 unmet); ``PUMPGROK_LIVE_ENABLE=1`` alone with effective paper mode
  never evaluates the gate and starts paper (INV-C-04).
- CLI ``--mode`` beats ``PUMPGROK_MODE`` beats TOML ``execution.mode``
  (R30) (INV-C-04).
- ``PUMPGROK_PROFILE`` (default ``paper``) selects
  ``src/pumpgrok/config/overlays/<profile>.toml``; ``PUMPGROK_CONFIG``
  applies last; ``PUMPGROK_*`` env overrides TOML; no ``config/``
  directory exists at the repo root (INV-C-10, R30).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import (
    OVERLAY_PROFILES,
    current_profile,
    load_settings,
    overlay_path,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def _toml(tmp_path: Path, body: str) -> str:
    path = tmp_path / "operator.toml"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_mode_precedence_cli_env_toml(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """INV-C-04: CLI --mode beats PUMPGROK_MODE beats TOML execution.mode."""
    config = _toml(tmp_path, '[execution]\nmode = "paper"\n')
    monkeypatch.setenv("PUMPGROK_CONFIG", config)
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    assert load_settings(mode="paper").effective_mode == "paper"
    assert load_settings().effective_mode == "live"
    monkeypatch.delenv("PUMPGROK_MODE")
    assert load_settings().effective_mode == "paper"


def test_toml_live_alone_never_starts_live(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """INV-C-04: TOML live alone exits 3 at the gate; env-only never gates."""
    config = _toml(tmp_path, '[execution]\nmode = "live"\n')
    monkeypatch.setenv("PUMPGROK_CONFIG", config)
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0
    capsys.readouterr()
    assert main(["run", "--once", "--replay", SMOKE]) == 3
    assert "LIVE GATE" in capsys.readouterr().err


def test_env_live_enable_alone_starts_paper(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """INV-C-04: PUMPGROK_LIVE_ENABLE=1 with paper mode never evaluates the gate."""
    monkeypatch.setenv("PUMPGROK_LIVE_ENABLE", "1")
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0
    err = capsys.readouterr().err
    assert "LIVE GATE" not in err


def test_profile_then_operator_file_then_env(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """INV-C-10: profile overlay, then PUMPGROK_CONFIG, then env."""
    assert current_profile() == "paper"
    monkeypatch.setenv("PUMPGROK_PROFILE", "dev")
    assert current_profile() == "dev"
    for profile in OVERLAY_PROFILES:
        assert overlay_path(profile).is_file()

    assert load_settings().risk.max_trades_per_day == 20
    config = _toml(tmp_path, "[risk]\nmax_trades_per_day = 7\n")
    monkeypatch.setenv("PUMPGROK_CONFIG", config)
    assert load_settings().risk.max_trades_per_day == 7
    monkeypatch.setenv("PUMPGROK_RISK__MAX_TRADES_PER_DAY", "9")
    assert load_settings().risk.max_trades_per_day == 9


def test_no_root_config_directory() -> None:
    """INV-C-10: there is no config/ directory at the repo root."""
    assert not (REPO_ROOT / "config").exists()
