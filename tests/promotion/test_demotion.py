"""PRM-04 (criterion 7): a parameter hash change resets to BACKTEST; one operation rolls back.

A change of the active parameter set resets every stage granted under the old set to BACKTEST,
in one ledger row. demote() moves a strategy down one stage in one row and refuses at BACKTEST.
"""

from __future__ import annotations

import pytest
from promotion_support import HUMAN, LATER_TS, STRATEGY, activate, advance, paper_history

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion import Stage, StageRefused, current_stage
from pumpgrok.promotion.demote import RESET_BY, demote, reset_on_hash_change
from pumpgrok.promotion.stages import stage_rows


def _live(store: LedgerStore):
    """Reach LIVE_ELIGIBLE under one active set; return that set."""
    params = activate(store)
    paper_history(store, wins=30, losses=20)
    advance(store, params)
    advance(store, params)
    assert current_stage(store, STRATEGY) is Stage.LIVE_ELIGIBLE
    return params


def test_hash_change_resets_to_backtest_in_one_row(store: LedgerStore) -> None:
    _live(store)
    before = len(stage_rows(store, STRATEGY))

    activate(store, min_unique_buyers=6, ts_utc=LATER_TS)
    row = reset_on_hash_change(store, STRATEGY, ts_utc=LATER_TS)

    assert row is not None
    assert row["payload"]["to_stage"] == "BACKTEST"
    assert row["payload"]["by"] == RESET_BY
    assert "parameter hash changed" in row["payload"]["decision"]
    assert len(stage_rows(store, STRATEGY)) == before + 1
    assert current_stage(store, STRATEGY) is Stage.BACKTEST


def test_unchanged_hash_does_not_reset(store: LedgerStore) -> None:
    _live(store)
    assert reset_on_hash_change(store, STRATEGY, ts_utc=LATER_TS) is None
    assert current_stage(store, STRATEGY) is Stage.LIVE_ELIGIBLE


def test_reset_is_a_no_op_at_backtest(store: LedgerStore) -> None:
    activate(store)
    assert reset_on_hash_change(store, STRATEGY, ts_utc=LATER_TS) is None
    assert stage_rows(store, STRATEGY) == []


def test_candidate_after_reset_is_refused_until_it_is_active(store: LedgerStore) -> None:
    old = _live(store)
    new = activate(store, min_unique_buyers=6, ts_utc=LATER_TS)
    reset_on_hash_change(store, STRATEGY, ts_utc=LATER_TS)

    with pytest.raises(StageRefused, match="not the active parameter set"):
        advance(store, old, now_ts=LATER_TS)
    assert new.content_hash != old.content_hash
    assert current_stage(store, STRATEGY) is Stage.BACKTEST


def test_demote_rolls_back_one_stage_in_one_row(store: LedgerStore) -> None:
    _live(store)
    before = len(stage_rows(store, STRATEGY))

    row = demote(store, STRATEGY, by=HUMAN, reason="manual review", ts_utc=LATER_TS)

    assert row["payload"]["from_stage"] == "LIVE_ELIGIBLE"
    assert row["payload"]["to_stage"] == "PAPER"
    assert row["payload"]["by"] == HUMAN
    assert len(stage_rows(store, STRATEGY)) == before + 1
    assert current_stage(store, STRATEGY) is Stage.PAPER


def test_demote_twice_reaches_backtest_then_refuses(store: LedgerStore) -> None:
    _live(store)
    demote(store, STRATEGY, by=HUMAN, reason="first", ts_utc=LATER_TS)
    demote(store, STRATEGY, by=HUMAN, reason="second", ts_utc=LATER_TS)
    assert current_stage(store, STRATEGY) is Stage.BACKTEST

    with pytest.raises(StageRefused, match="nothing to demote"):
        demote(store, STRATEGY, by=HUMAN, reason="third", ts_utc=LATER_TS)


def test_demote_refuses_without_a_reason(store: LedgerStore) -> None:
    _live(store)
    with pytest.raises(StageRefused, match="needs a reason"):
        demote(store, STRATEGY, by=HUMAN, reason="   ", ts_utc=LATER_TS)
    assert current_stage(store, STRATEGY) is Stage.LIVE_ELIGIBLE
