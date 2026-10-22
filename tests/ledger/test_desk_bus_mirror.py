"""INV-R-21: halt mirror to desk.md; CLI and supervisor appends serialise.

Owning test for SAFETY_INVARIANTS.md section 3.3 row INV-R-21. Every
append from the supervisor or a CLI process goes through
``ledger/store.py`` with BEGIN IMMEDIATE and the chain computed inside
the transaction; a CLI ``pumpgrok killswitch set`` interleaved with
supervisor appends still verifies CONSISTENT. Every HaltSet row is
mirrored to ``$PUMPGROK_DESK/desk.md`` (``Halt: true`` plus the
``FLOOR HALTED`` line, exactly as ``tools/desk_state.py`` formats it)
through tmp-file plus fsync plus os.replace, so readers never see a
partial file and ``desk_state.py status`` reports halt true.

Harness: FixtureClock plus seeded IdFactory; no wall clock, no network.
The desk_state check loads tools/desk_state.py from its file path, the
same way tests/test_tools_cli.py loads root tools.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from pumpgrok.ledger.desk_bus import mirror_halt, mirror_killswitch
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc

BASE = 1767225600.0
DAY = "2026-01-01"
CID = "01JAAAAAAAAAAAAAAAAAAAAAAAAA"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _desk_state() -> ModuleType:
    path = REPO_ROOT / "tools" / "desk_state.py"
    spec = importlib.util.spec_from_file_location("desk_state_mirror", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _halt_row(clock: FixtureClock, key: str, reason: str) -> dict:
    return {
        "ts_utc": format_ts_utc(clock.now()),
        "source": "paper",
        "correlation_id": CID,
        "idempotency_key": key,
        "type": "HaltSet",
        "payload": {
            "source": "paper",
            "reason": reason,
            "detail": f"{reason} for mirror proof",
            "equity_lamports": 9_500_000_000,
            "day_start_equity_lamports": 10_000_000_000,
            "set_by": "risk_engine",
        },
    }


def _kill_row(clock: FixtureClock, key: str) -> dict:
    return {
        "ts_utc": format_ts_utc(clock.now()),
        "source": "paper",
        "correlation_id": CID,
        "idempotency_key": key,
        "type": "KillSwitchSet",
        "payload": {
            "source": "paper",
            "origin": "file",
            "reason": "operator engaged the kill switch",
            "flatten_requested": False,
            "set_by": "human:alice",
        },
    }


def test_halt_mirrors_to_desk_md_and_cli_append_is_serialised(
    tmp_path: Path,
) -> None:
    """INV-R-21: desk.md mirror plus serialised interleaved appends."""
    db_path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(db_path)
    clock = FixtureClock(start=BASE)
    desk_dir = tmp_path / "desk"
    supervisor = LedgerStore(str(db_path))
    cli = LedgerStore(str(db_path))
    try:
        supervisor.append(**_halt_row(clock, "halt-manual-1", "manual"))
        mirror_path = mirror_halt(
            desk_dir, reason="manual", ts_utc=format_ts_utc(clock.now())
        )
        assert mirror_path == desk_dir / "desk.md"
        body = mirror_path.read_text(encoding="utf-8")
        assert "Halt: true" in body
        assert "FLOOR HALTED" in body
        status = _desk_state().status_payload(desk_dir)
        assert status["halt"] is True
        # A CLI killswitch set while the supervisor runs: serialised appends.
        clock.advance_to(BASE + 30.0)
        cli.append(**_kill_row(clock, "kill-file-1"))
        mirror_killswitch(
            desk_dir, source="file", reason="kill", ts_utc=format_ts_utc(clock.now())
        )
        for index in range(5):
            clock.advance_to(clock.now() + 1.0)
            supervisor.append(**_halt_row(clock, f"halt-manual-{index + 2}", "manual"))
            cli.append(**_kill_row(clock, f"kill-file-{index + 2}"))
        assert supervisor.verify() is True
        assert cli.verify() is True
        seqs = [row["seq"] for row in supervisor.read(limit=None)]
        assert seqs == list(range(1, len(seqs) + 1))
        keys = [row["idempotency_key"] for row in supervisor.read(limit=None)]
        assert len(set(keys)) == len(keys)
        # The kill-switch mirror keeps the halt flag set for the cron gate.
        assert _desk_state().status_payload(desk_dir)["halt"] is True
        assert "KILL SWITCH" in mirror_path.read_text(encoding="utf-8")
    finally:
        supervisor.close()
        cli.close()
