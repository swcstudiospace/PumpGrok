"""Default configuration is paper with the gate untouched (INV-C-01).

``pumpgrok run`` with no ``--mode``, no ``PUMPGROK_MODE`` and the default
``paper`` profile yields ``effective_mode == "paper"``, and a paper
skip-only cycle never evaluates the live gate (the gate object is built
but ``evaluate``/``check`` are only consulted for an effective live
mode).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import load_settings
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.execution.live import live_gate
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools import ensure_paper_genesis

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")


AUTHORITY_AT = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _record_complete_authority() -> None:
    """Real operator authority for every seat, recorded as the onboarding verbs record it.

    The paper genesis is written first, as ``_record_tool`` does, then the operator key and an
    allow per roster tool. Each allow is an HMAC-authenticated protected record bound to a
    ConfigChanged row in the paper ledger, the same records the startup gate reads.
    """
    oc.init_key(oc.OPERATOR_DIR)
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        ensure_paper_genesis(store, load_settings(mode="paper").risk)
        for seat in EXPECTED_SEAT_IDS:
            for tool in sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat)):
                oc.record_tool_choice(
                    store,
                    seat=seat,
                    tool=tool,
                    decision="allow",
                    now=AUTHORITY_AT,
                    operator_dir=oc.OPERATOR_DIR,
                )
    finally:
        store.close()


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
    _record_complete_authority()
    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0
    assert calls == []
    capsys.readouterr()
