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

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config import settings as settings_mod
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.doctor import SUBSYSTEMS
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools import ensure_paper_genesis

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")


AUTHORITY_AT = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


#: Subsystem lines: ``ok`` for a resolved module, or ``warn`` for one whose phase has not landed.
_SUBSYSTEM_OK = re.compile(r"ok    ([\w.]+) \(([\w.]+)\)")
_SUBSYSTEM_WARN = re.compile(r"warn  ([\w.]+) \(([\w.]+)\): not-yet-implemented")
#: Every other report line in its one documented shape. Anything outside these fails the report.
_REPORT_SHAPES = tuple(
    re.compile(shape)
    for shape in (
        r"info  mode=\S+ profile=\S+",
        r"info  bus depth=\d+ lanes=\S+ sidecar=\S+ enabled=(True|False)",
        r"info  source \S+ status=(ok|unknown)",
        r"info  time-sync: read-only probe, offset not adjusted",
        r"info  clock-sync \((not NTP-synchronized; wall clock may drift"
        r"|unknown: timedatectl unavailable)\)",
        r"info  hermes-jobs: (store unreadable for profile .+|superseded enabled: .+)"
        r" \(cadence; event mode refused\)",
        r"ok    clock-sync \(NTP synchronized\)",
        r"ok    ONB-08 rpc=default \((no operator key; )?no (operator )?"
        r"endpoint choice recorded\)",
        r"ok    ONB-08 rpc=explicit endpoint=.+ \(operator-authenticated\)",
        r"ok    hermes-jobs: (no installed jobs found \(default profile\)"
        r"|\d+ installed, no superseded job enabled)",
        r"warn  /(healthz|metrics) \(not served: health\.port=0, only `run --serve` binds"
        r" a port\)",
        r"doctor: \d+ present, \d+ not-yet-implemented \(warnings\), exit 0",
        r"info  grok-budget \S+ state=\S+",
        r"info  stages none|info  stage \S+ stage=\S+",
        r"info  kills none|info  kill \S+|warn  kills unreadable",
        r"info  signer attestation=\S+ source=settings",
        r"warn  source \S+ status=unknown",
    )
)


def _malformed_report_lines(report: str) -> list[str]:
    """Report lines in no documented shape, or naming a subsystem or module SUBSYSTEMS lacks."""
    modules = dict(SUBSYSTEMS)
    malformed: list[str] = []
    for line in report.splitlines():
        if not line.strip():
            continue
        subsystem = _SUBSYSTEM_OK.fullmatch(line) or _SUBSYSTEM_WARN.fullmatch(line)
        if subsystem is not None:
            if modules.get(subsystem.group(1)) != subsystem.group(2):
                malformed.append(line)
        elif not any(shape.fullmatch(line) for shape in _REPORT_SHAPES):
            malformed.append(line)
    return malformed


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
    assert report.strip(), "doctor printed nothing"
    assert _malformed_report_lines(report) == []


@pytest.mark.parametrize(
    "line",
    [
        "ok   ledger broken",
        "ok    ledger (pumpgrok.ledger) extra",
        "ok    ledger (pumpgrok.core)",
        "warn  ledger (pumpgrok.ledger): broken",
    ],
)
def test_report_checker_rejects_malformed_lines(line: str) -> None:
    assert _malformed_report_lines(line) == [line]
