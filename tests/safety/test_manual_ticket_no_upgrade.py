"""PAP-03: manual-ticket never runs an upgrade.

Under manual-ticket no parameter promotion, harness search or autonomy
change is performed or persisted: a paper cycle leaves the level at
manual-ticket, appends no autonomy ConfigChanged row, writes no active-set
record and no promotion evidence, and writes no trial or backtest
artifact. Offline only: recorded fixtures, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pumpgrok.cli import main
from pumpgrok.config.settings import load_settings
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.active_set import read_active_set
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools import ensure_paper_genesis

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")


AUTHORITY_AT = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _record_complete_authority() -> None:
    """Real operator authority for every seat, as the onboarding verbs record it.

    The paper genesis is written first, then the operator key and an HMAC-authenticated
    allow per roster tool, so the paper startup gate reads complete authority inputs.
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


def _autonomy_changes(store: LedgerStore) -> list[dict]:
    return [
        row
        for row in store.read(types=["ConfigChanged"], limit=None)
        if isinstance(row.get("payload"), dict)
        and "autonomy_level" in row["payload"].get("keys_changed", [])
    ]


def _active_set_changes(store: LedgerStore) -> list[dict]:
    return [
        row
        for row in store.read(types=["ConfigChanged"], limit=None)
        if isinstance(row.get("payload"), dict)
        and "active_param_set" in row["payload"].get("keys_changed", [])
    ]


def test_manual_ticket_cycle_performs_no_upgrade(tmp_path, monkeypatch) -> None:
    """PAP-03: a manual-ticket paper cycle persists no promotion, search or level change."""
    monkeypatch.chdir(tmp_path)
    paper_ledger = tmp_path / "var" / "ledger.sqlite"
    paper_ledger.parent.mkdir(parents=True, exist_ok=True)
    store = LedgerStore(str(paper_ledger))
    try:
        assert read_autonomy(store) == "manual-ticket"
    finally:
        store.close()

    _record_complete_authority()

    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0

    assert not (tmp_path / "var" / "backtest").exists()
    assert list((tmp_path / "var").rglob("trials.jsonl")) == []

    check = LedgerStore(str(paper_ledger))
    try:
        assert read_autonomy(check) == "manual-ticket"
        assert _autonomy_changes(check) == []
        assert read_active_set(check) is None
        assert _active_set_changes(check) == []
        assert not (tmp_path / "var" / "upgrade").exists()
    finally:
        check.close()

    replay_ledger = tmp_path / "var" / "replay" / "smoke" / "ledger.sqlite"
    replay_store = LedgerStore(str(replay_ledger))
    try:
        assert _autonomy_changes(replay_store) == []
        assert _active_set_changes(replay_store) == []
    finally:
        replay_store.close()
