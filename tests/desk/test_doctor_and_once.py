"""Foundation checkpoint: skip-only cycle and doctor rows (INV-C-12).

``pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke``
executes a skip-only cycle (fixture events read, one ``JournalNote``
appended, exit 0) and ``pumpgrok doctor`` reports one line per subsystem:
``ok`` when the module resolves, ``warn ... not-yet-implemented`` for
subsystems whose owning phase has not landed, and ``warn ... (not served:
health.port=0, ...)`` for the served endpoints when no port is bound (no
network is attempted). Warnings never fail the report (exit 0).
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.cli import main
from pumpgrok.ledger.store import LedgerStore

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")


def test_once_skip_only_cycle_and_doctor_rows(tmp_path, monkeypatch, capsys) -> None:
    """INV-C-12: skip-only cycle exit 0; doctor rows ok, not-yet-implemented, or not-served."""
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0
    out = capsys.readouterr().out
    assert "engine decision=skip" in out

    ledger = LedgerStore(tmp_path / "var" / "replay" / "smoke" / "ledger.sqlite")
    try:
        kinds = [row["type"] for row in ledger.read(limit=None)]
    finally:
        ledger.close()
    assert "JournalNote" in kinds

    assert main(["doctor"]) == 0
    report = capsys.readouterr().out
    lines = [line for line in report.splitlines() if line.strip()]
    assert lines, "doctor printed nothing"
    for line in lines:
        if line.startswith(("ok", "info", "doctor:")):
            continue
        assert line.startswith("warn"), line
        # Two documented warning shapes: absent subsystems and unbound
        # served endpoints (05-07 probes; no network attempted at port 0).
        assert "not-yet-implemented" in line or "(not served: health.port=0" in line, line
