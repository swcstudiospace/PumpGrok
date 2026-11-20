"""The serve's rule reload applies a promotion recorded in the operator ledger.

apply_candidate records the new active set in the operator ledger at PAPER_LEDGER_PATH, the
ledger startup reads it from. The running serve must pick that set up at its tick boundary.
Reading only the replay ledger missed every promotion. Offline: a temp working directory and
the bundled smoke fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.engine.pipeline import CandidateVerdict, evaluate_candidates
from pumpgrok.ledger.active_set import record_active_set
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.supervisor.scheduler.serve import _build_serve
from pumpgrok.upgrade.params import ParamSet

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
OPERATOR = "human:RELOAD-TEST"
PROMOTED = ParamSet(filter={"min_unique_buyers": 1000}, exits={"take_profit_pct": 50.0})


def _decisions(verdicts: list[CandidateVerdict]) -> list[tuple[str, str]]:
    return [(item.verdict.decision, item.verdict.reason) for item in verdicts]


@pytest.fixture
def desk_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_reload_applies_a_promotion_recorded_in_the_operator_ledger(desk_dir: Path) -> None:
    parts = _build_serve(SMOKE, FilterSettings(), seed=SEED, ledger_path=desk_dir / "replay.sqlite")
    try:
        before = _decisions(parts.rules.trading.candidates)
        operator = LedgerStore(str(PAPER_LEDGER_PATH))
        try:
            record_active_set(
                operator,
                PROMOTED,
                OPERATOR,
                ts_utc="2026-01-01T00:01:00Z",
                source="paper",
                correlation_id="reload-test",
            )
        finally:
            operator.close()
        parts.rules.reload()
        expected = evaluate_candidates(parts.rules.events, PROMOTED.candidate().filter_settings())
        assert parts.rules.loaded == PROMOTED.content_hash
        assert _decisions(parts.rules.trading.candidates) == _decisions(expected)
        assert _decisions(expected) != before
    finally:
        parts.store.close()


def test_reload_creates_no_operator_ledger_when_none_was_recorded(desk_dir: Path) -> None:
    parts = _build_serve(SMOKE, FilterSettings(), seed=SEED, ledger_path=desk_dir / "replay.sqlite")
    try:
        parts.rules.reload()
        assert parts.rules.loaded is None
        assert not PAPER_LEDGER_PATH.exists()
    finally:
        parts.store.close()
