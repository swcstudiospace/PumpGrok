"""A restored active set drives the paper runtime at startup (UPG-03).

Set X (filter min_unique_buyers 1000, exits take_profit_pct 50.0) is recorded,
set Y is recorded after it, and X is restored by hash. The active set read back
from the operator ledger then opens the replay runtime: its exits and its filter
verdicts come from X, not from the desk defaults. A recorded set whose content is
missing, undecodable, or hashes to something else raises CorruptState. Offline
only: temp ledgers and the bundled smoke fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.errors import CorruptState
from pumpgrok.engine.pipeline import CandidateVerdict, decide_replay, evaluate_candidates
from pumpgrok.ledger.active_set import active_set_rows, read_active_param_set, record_active_set
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.supervisor.scheduler import open_replay_runtime, run_once_replay
from pumpgrok.upgrade.params import ParamSet
from pumpgrok.upgrade.rollback import restore_active_set

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
OPERATOR = "human:STARTUP-TEST"
CORRELATION = "active-set-startup-test"
X = ParamSet(filter={"min_unique_buyers": 1000}, exits={"take_profit_pct": 50.0})
Y = ParamSet(filter={"min_unique_buyers": 7}, exits={"stop_loss_pct": 10.0})
CONTENT_PREFIX = "active_param_set_content:"


def _decisions(verdicts: list[CandidateVerdict]) -> list[tuple[str, str]]:
    return [(item.verdict.decision, item.verdict.reason) for item in verdicts]


def _append_activation(store: LedgerStore, param_set: ParamSet) -> None:
    """Append only the ConfigChanged and JournalNote rows, without recording content."""
    store.append_batch(
        active_set_rows(
            param_set,
            OPERATOR,
            previous="",
            ts_utc="2026-01-01T00:01:00Z",
            source="paper",
            correlation_id=CORRELATION,
        )
    )


def test_restored_set_drives_the_runtime_at_startup(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "operator.sqlite"))
    try:
        record_active_set(
            store,
            X,
            OPERATOR,
            ts_utc="2026-01-01T00:01:00Z",
            source="paper",
            correlation_id=CORRELATION,
        )
        record_active_set(
            store,
            Y,
            OPERATOR,
            ts_utc="2026-01-01T00:02:00Z",
            source="paper",
            correlation_id=CORRELATION,
        )
        restore_active_set(
            store,
            X.content_hash,
            OPERATOR,
            ts_utc="2026-01-01T00:03:00Z",
            source="paper",
            correlation_id=CORRELATION,
        )
        active = read_active_param_set(store)
    finally:
        store.close()
    assert active == X
    assert active is not None
    runtime = open_replay_runtime(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        ledger_path=tmp_path / "replay.sqlite",
        active_set=active,
    )
    try:
        assert runtime.exits.take_profit_pct == 50.0
        expected = evaluate_candidates(runtime.dataset.events, X.candidate().filter_settings())
        assert _decisions(runtime.candidates) == _decisions(expected)
        defaults = evaluate_candidates(runtime.dataset.events, FilterSettings())
        applied_reasons = [item.verdict.reason for item in runtime.candidates]
        default_reasons = [item.verdict.reason for item in defaults]
        assert "few_buyers" in applied_reasons
        assert "few_buyers" not in default_reasons
    finally:
        runtime.store.close()


def test_run_once_replay_checkpoint_uses_the_active_filter(tmp_path: Path) -> None:
    """The checkpoint verdict judges candidates under the active filter, not the default.

    Under the desk default the Beta tick passes (9 buyers, curve near 12%, 1202 s old), so
    the verdict is a BUY. Under X (1000 buyers) no tick can pass; the first tick fails on its
    curve (near 49%), so the verdict is a skip with reason curve_too_full.
    """
    events = load_dataset(SMOKE).events
    default_verdict = decide_replay(events, FilterSettings())
    active_verdict = decide_replay(events, X.candidate().filter_settings())
    assert default_verdict.decision != active_verdict.decision
    result = run_once_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        ledger_path=tmp_path / "replay.sqlite",
        active_set=X,
    )
    assert result.decision == active_verdict.decision
    assert result.reason == active_verdict.reason == "curve_too_full"


def test_no_recorded_set_reads_none(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "operator.sqlite"))
    try:
        assert read_active_param_set(store) is None
    finally:
        store.close()


def test_active_row_without_its_content_raises_corrupt_state(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "operator.sqlite"))
    try:
        _append_activation(store, X)
        with pytest.raises(CorruptState, match="without its content"):
            read_active_param_set(store)
    finally:
        store.close()


def test_undecodable_content_raises_corrupt_state(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "operator.sqlite"))
    try:
        _append_activation(store, X)
        store.set_meta(f"{CONTENT_PREFIX}{X.content_hash}", "{not json")
        with pytest.raises(CorruptState, match="undecodable"):
            read_active_param_set(store)
    finally:
        store.close()


def test_content_hashing_elsewhere_raises_corrupt_state(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "operator.sqlite"))
    try:
        _append_activation(store, X)
        other = json.dumps(Y.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        store.set_meta(f"{CONTENT_PREFIX}{X.content_hash}", other)
        with pytest.raises(CorruptState, match="does not match its hash"):
            read_active_param_set(store)
    finally:
        store.close()
