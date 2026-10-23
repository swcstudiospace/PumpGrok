"""The live gate's paper-ledger precondition reads the shared canonical path.

``PAPER_LEDGER_PATH`` (pumpgrok.ledger.paths) is the one paper ledger. The gate's paper window
must resolve through that constant so the gate and the CLI report can never disagree on which
file holds the paper history. The test swaps the constant in the gate module: a gate that still
hardcodes ``var/ledger.sqlite`` never looks at the swapped path and cannot pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.execution.live import live_gate
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore


def test_gate_module_uses_the_shared_paper_ledger_constant() -> None:
    assert live_gate.PAPER_LEDGER_PATH is PAPER_LEDGER_PATH


def test_gate_paper_window_reads_the_shared_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alt = Path("alt") / "paper.sqlite"
    monkeypatch.setattr(live_gate, "PAPER_LEDGER_PATH", alt)
    (tmp_path / "alt").mkdir()
    store = LedgerStore(str(tmp_path / alt))
    store.close()

    _, reason, _, _ = live_gate._paper_window(tmp_path)

    # An empty ledger at the swapped path is read: the reason names that path and no other.
    assert reason == f"no source=paper events in {alt}"
