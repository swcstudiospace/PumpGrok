"""PRM-06 (criterion 9): only writers write stages, and stored content is verified first.

A stage change or demotion needs a human: or gate: caller. The parameter set must be the active
set, and its stored content must verify before any row is written. A refused call appends nothing.
"""

from __future__ import annotations

import pytest
from promotion_support import CORR, HUMAN, NOW, STRATEGY, activate, advance, paper_history

from pumpgrok.ledger.active_set import is_writer, verify_stored_content
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion import Stage, StageRefused, current_stage
from pumpgrok.promotion import stages as stages_module
from pumpgrok.promotion.demote import demote
from pumpgrok.promotion.stages import stage_rows


@pytest.mark.parametrize(
    ("by", "accepted"),
    [
        ("human:alice", True),
        ("gate:promotion-check", True),
        ("bot-02-risk", False),
        ("seat:bot-02-risk", False),
        ("", False),
        (None, False),
    ],
)
def test_is_writer_accepts_only_human_and_gate(by: object, accepted: bool) -> None:
    assert is_writer(by) is accepted


@pytest.mark.parametrize("by", ["bot-02-risk", "", None])
def test_non_writer_cannot_advance_a_stage(store: LedgerStore, by: object) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    with pytest.raises(StageRefused, match="human: or gate: writer"):
        advance(store, params, by=by)  # type: ignore[arg-type]
    assert stage_rows(store, STRATEGY) == []


def test_non_writer_cannot_demote(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    advance(store, params)
    with pytest.raises(StageRefused, match="human: or gate: writer"):
        demote(store, STRATEGY, by="bot-02-risk", reason="x", ts_utc=NOW)
    assert current_stage(store, STRATEGY) is Stage.PAPER


def test_stored_content_is_verified_before_the_row_is_written(
    store: LedgerStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)

    def _tampered(_store: LedgerStore, content_hash: str) -> None:
        raise ValueError(f"active param set {content_hash} content does not match its hash")

    monkeypatch.setattr(stages_module, "verify_stored_content", _tampered)
    with pytest.raises(ValueError, match="does not match its hash"):
        advance(store, params)
    assert stage_rows(store, STRATEGY) == []


def test_recorded_content_verifies_and_advances(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    verify_stored_content(store, params.content_hash)

    row = advance(store, params, by="gate:promotion-check")

    assert row["payload"]["by"] == "gate:promotion-check"
    assert current_stage(store, STRATEGY) is Stage.PAPER


def test_forged_stage_row_from_a_seat_does_not_fold(store: LedgerStore) -> None:
    """A PromotionStageSet row whose by is a seat never changes the folded stage."""
    store.append_batch(
        [
            {
                "ts_utc": NOW,
                "source": "paper",
                "correlation_id": CORR,
                "idempotency_key": "forged-stage-row",
                "type": "PromotionStageSet",
                "payload": {
                    "source": "paper",
                    "strategy_id": STRATEGY,
                    "from_stage": "BACKTEST",
                    "to_stage": "LIVE_ELIGIBLE",
                    "decision": "forged by a seat",
                    "by": "bot-02-risk",
                    "params_hash": "",
                    "paper_window_start": "",
                    "evidence_hash": "",
                },
            }
        ]
    )
    assert current_stage(store, STRATEGY) is Stage.BACKTEST

    params = activate(store)
    paper_history(store, wins=1, losses=1)
    row = advance(store, params)

    assert row["payload"]["from_stage"] == "BACKTEST"
    assert row["payload"]["to_stage"] == "PAPER"
    assert HUMAN.startswith("human:")
