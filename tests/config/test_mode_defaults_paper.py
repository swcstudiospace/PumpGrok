"""Default configuration is paper with the gate untouched (INV-C-01).

``pumpgrok run`` with no ``--mode``, no ``PUMPGROK_MODE`` and the default
``paper`` profile yields ``effective_mode == "paper"``, and a paper
skip-only cycle never evaluates the live gate (the gate object is built
but ``evaluate``/``check`` are only consulted for an effective live
mode).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import load_settings
from pumpgrok.execution.live import live_gate

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_mode_defaults_paper(clean_env: None) -> None:
    """INV-C-01: defaults resolve to paper."""
    settings = load_settings()
    assert settings.effective_mode == "paper"
    assert settings.execution.mode == "paper"


def test_paper_cycle_never_evaluates_gate(
    clean_env: None, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """INV-C-01: a paper run leaves LiveGate.evaluate uncalled."""
    calls: list[str] = []
    real_evaluate = live_gate.LiveGate.evaluate

    def spy(self: live_gate.LiveGate) -> tuple[live_gate.Precondition, ...]:
        calls.append("evaluate")
        return real_evaluate(self)

    monkeypatch.setattr(live_gate.LiveGate, "evaluate", spy)
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0
    assert calls == []
    capsys.readouterr()
