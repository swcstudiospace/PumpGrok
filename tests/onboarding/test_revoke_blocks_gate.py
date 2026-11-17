"""A revoked roster tool is not authority: paper start refuses and doctor reports it missing.

Every roster tool of every seat first carries a real, bound allow. One tool is then revoked
through the same protected ledger the operator uses. Only the latest decision for a tool counts,
and only an allow is recorded, so the revoked tool must block the paper start gate and show as
missing in the doctor inventory. Nothing is monkeypatched: the operator key, the choices file and
the paper ledger are real files in a temporary working directory.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.cli import verbs_state
from pumpgrok.config.settings import load_settings
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.doctor import PRESENT, input_inventory
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
SEAT_RECORD = "seat_tool_access"


@pytest.fixture(autouse=True)
def operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Own working directory, a PUMPGROK_*-free environment and a fresh operator key."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PUMPGROK_"):
            monkeypatch.delenv(name)
    oc.init_key(Path("var") / "operator")
    yield tmp_path


def _roster() -> list[tuple[str, str]]:
    return [
        (seat, tool)
        for seat in EXPECTED_SEAT_IDS
        for tool in sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat))
    ]


def _record(decision: str, pairs: list[tuple[str, str]]) -> None:
    PAPER_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = LedgerStore(str(PAPER_LEDGER_PATH))
    try:
        for seat, tool in pairs:
            oc.record_tool_choice(store, seat=seat, tool=tool, decision=decision, now=NOW)
    finally:
        store.close()


def _seat_status() -> str:
    records = {record.name: record for record in input_inventory(load_settings(), "paper")}
    return records[SEAT_RECORD].status


def test_revoked_tool_blocks_the_paper_start_gate_and_shows_missing_in_doctor() -> None:
    roster = _roster()
    _record("allow", roster)
    assert _seat_status() == PRESENT
    assert not any("seat" in line for line in verbs_state._paper_start_gate(load_settings()))

    seat, tool = roster[0]
    _record("revoke", [(seat, tool)])

    assert _seat_status() == "missing"
    gate = verbs_state._paper_start_gate(load_settings())
    assert f"  - {SEAT_RECORD}: missing (required for paper)" in gate
    seat_lines = verbs_state._unauthenticated_seat_lines()
    assert any(line.startswith(f"    - seat {seat}: 1 of ") for line in seat_lines)


def test_allow_after_revoke_clears_the_block() -> None:
    roster = _roster()
    _record("allow", roster)
    seat, tool = roster[0]
    _record("revoke", [(seat, tool)])
    assert _seat_status() == "missing"
    _record("allow", [(seat, tool)])
    assert _seat_status() == PRESENT
