"""/healthz reports the operator's autonomy level, never the replay store's.

``state autonomy`` records the human level in the operator ledger at PAPER_LEDGER_PATH. The serve
replay ledger never carries that row, so the health body must read the operator ledger, read-only,
and must not create it when absent. Offline: a temp working directory and the bundled smoke fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.ledger.autonomy import autonomy_rows
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.supervisor.scheduler.serve import _build_serve

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
TS = "2026-01-01T00:01:00Z"


@pytest.fixture
def desk_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _human_autonomous_paper() -> list[dict]:
    return autonomy_rows(
        "autonomous-paper",
        "human:HEALTHZ-TEST",
        previous="manual-ticket",
        ts_utc=TS,
        source="paper",
        correlation_id="healthz-test",
    )


def test_healthz_ignores_a_level_recorded_only_in_the_replay_store(desk_dir: Path) -> None:
    parts = _build_serve(SMOKE, FilterSettings(), seed=SEED, ledger_path=desk_dir / "replay.sqlite")
    try:
        parts.store.append_batch(_human_autonomous_paper())
        assert parts.supervisor.autonomy_level() == "manual-ticket"
        assert parts.supervisor.health_status()["autonomy_level"] == "manual-ticket"
        assert not PAPER_LEDGER_PATH.exists()
    finally:
        parts.store.close()


def test_healthz_reports_the_level_recorded_in_the_operator_ledger(desk_dir: Path) -> None:
    parts = _build_serve(SMOKE, FilterSettings(), seed=SEED, ledger_path=desk_dir / "replay.sqlite")
    try:
        operator = LedgerStore(str(PAPER_LEDGER_PATH))
        try:
            operator.append_batch(_human_autonomous_paper())
        finally:
            operator.close()
        assert parts.supervisor.autonomy_level() == "autonomous-paper"
        assert parts.supervisor.health_status()["autonomy_level"] == "autonomous-paper"
    finally:
        parts.store.close()
