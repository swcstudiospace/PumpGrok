"""Foundation checkpoint: replay cycle and doctor rows (INV-C-12).

``pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke``
executes one replay cycle (fixture events read, the verdict ``JournalNote`` and the
sniper's order rows appended, exit 0) and ``pumpgrok doctor`` reports one line per subsystem:
``ok`` when the module resolves, ``warn ... not-yet-implemented`` for
subsystems whose owning phase has not landed, and ``warn ... (not served:
health.port=0, ...)`` for the served endpoints when no port is bound (no
network is attempted). Warnings never fail the report (exit 0).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pumpgrok.cli import main
from pumpgrok.config import settings as settings_mod
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
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
        ensure_paper_genesis(store, settings_mod.load_settings(mode="paper").risk)
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


def test_once_skip_only_cycle_and_doctor_rows(tmp_path, monkeypatch, capsys) -> None:
    """INV-C-12: replay cycle exit 0; doctor rows ok, not-yet-implemented, or not-served."""
    monkeypatch.chdir(tmp_path)
    _record_complete_authority()
    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0
    out = capsys.readouterr().out
    assert "engine decision=buy" in out
    assert "trades filled=2 not_filled=1" in out

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
