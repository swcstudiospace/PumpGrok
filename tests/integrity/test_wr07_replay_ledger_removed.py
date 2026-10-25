"""INT-07 (WR-07): a failed replay append or verify leaves no replay ledger behind.

Ports feature-lineage fix 4c19fd9 onto this tree's replay/runner.py: the
pre-append checks (manifest, gap, LLM record) run before any file is created,
and an append/verify failure removes the just-created ledger (sqlite plus
-wal/-shm sidecars) before re-raising, so file-existence checks never mistake
a failed run for a successful replay output. Deterministic, no network.

Pre-fix behaviour (parent 4c19fd9^): the append/verify block ended in a bare
``finally: store.close()`` with no removal, so the half-written ledger file
survived and both tests below failed on ``target.exists()``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.replay.runner import run_replay

SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"


def _assert_no_ledger(target: Path) -> None:
    assert not target.exists()
    assert not Path(str(target) + "-wal").exists()
    assert not Path(str(target) + "-shm").exists()


def test_verify_failure_removes_the_created_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed verify deletes the just-created ledger and re-raises."""
    target = tmp_path / "bad-verify.sqlite"
    monkeypatch.setattr(LedgerStore, "verify", lambda self: False)
    with pytest.raises(LedgerInconsistent, match="replay ledger failed verification"):
        run_replay(SMOKE, FilterSettings(), ledger_path=target)
    _assert_no_ledger(target)


def test_append_failure_removes_the_created_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed append deletes the just-created ledger and re-raises."""
    target = tmp_path / "bad-append.sqlite"

    def _boom(self: LedgerStore, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        raise RuntimeError("injected append failure")

    monkeypatch.setattr(LedgerStore, "append_batch", _boom)
    with pytest.raises(RuntimeError, match="injected append failure"):
        run_replay(SMOKE, FilterSettings(), ledger_path=target)
    _assert_no_ledger(target)
