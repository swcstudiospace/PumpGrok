"""Characterization: replay pipeline (STRUCT-003, G1).

Pins ``engine/pipeline.py``: each fixture tick maps to a candidate that carries
only the evidence the tick records (name, image, creation time, buyer count,
curve reserves). The fail-closed filter decides per candidate; a tick with no
evidence still fails closed. No live stages exist here by design (no monitor
stream, no analyzer fetch, no model lookup).
"""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.config.settings import FilterSettings
from pumpgrok.engine.monitor import passes_filter
from pumpgrok.engine.pipeline import (
    BUY,
    DATA_UNAVAILABLE,
    SKIP,
    EngineDecision,
    decide_replay,
    decide_token,
    evaluate_candidates,
    format_decision,
    tick_to_candidate,
)
from pumpgrok.replay.clock import parse_ts_utc

SMOKE = Path(__file__).resolve().parent.parent / "fixtures" / "replay" / "smoke"
ALPHA = "SmokeMintAAAA1111111111111111111111111111111"
BETA = "SmokeMintBBBB2222222222222222222222222222222"


def _smoke_events() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (SMOKE / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _filter() -> FilterSettings:
    return FilterSettings()


def test_tick_maps_to_candidate_with_fixture_evidence() -> None:
    event = _smoke_events()[0]
    token = tick_to_candidate(event)
    assert token.mint == ALPHA
    assert token.has_metadata
    assert token.unique_buyers == 12
    assert token.sol_in_curve == 42_100_000_000
    assert round(token.curve_progress, 3) == round(42.1 / 85.0, 3)
    assert token.created_timestamp == parse_ts_utc("2025-12-31T23:30:00.000Z")


def test_tick_without_evidence_stays_evidence_less() -> None:
    bare = {"ts_utc": "2026-01-01T00:00:00.000Z", "mint": BETA, "S": 9_800_000_000}
    token = tick_to_candidate(bare)
    assert token.unique_buyers is None
    assert not token.has_metadata
    assert token.created_timestamp == 0.0
    assert passes_filter(token, _filter(), 1_767_225_603.0) == (False, "no_metadata")


def test_candidate_without_buyer_evidence_hits_the_evidence_gate() -> None:
    event = dict(_smoke_events()[2])
    del event["unique_buyers"]
    token = tick_to_candidate(event)
    assert passes_filter(token, _filter(), parse_ts_utc(str(event["ts_utc"]))) == (
        False,
        DATA_UNAVAILABLE,
    )


def test_fully_loaded_curve_is_too_full() -> None:
    now = parse_ts_utc("2026-01-01T00:00:00.000Z")
    decision = decide_token(tick_to_candidate(_smoke_events()[0]), _filter(), now)
    assert decision == EngineDecision(decision=SKIP, reason="curve_too_full", mint=ALPHA)


def test_candidate_verdicts_follow_each_tick_time() -> None:
    verdicts = evaluate_candidates(_smoke_events(), _filter())
    assert [v.verdict.decision for v in verdicts] == [SKIP, SKIP, BUY, BUY, SKIP]
    assert [v.verdict.reason for v in verdicts] == [
        "curve_too_full",
        "curve_too_full",
        "ok",
        "ok",
        DATA_UNAVAILABLE,
    ]
    assert verdicts[2].token.mint == BETA


def test_decide_replay_over_smoke_is_a_buy_on_the_second_mint() -> None:
    decision = decide_replay(_smoke_events(), _filter())
    assert decision == EngineDecision(decision=BUY, reason="ok", mint=BETA)


def test_decide_replay_reports_first_skip_when_nothing_buys() -> None:
    only_alpha = [e for e in _smoke_events() if e["mint"] == ALPHA]
    decision = decide_replay(only_alpha, _filter())
    assert decision == EngineDecision(decision=SKIP, reason="curve_too_full", mint=ALPHA)


def test_decide_replay_with_no_events_skips() -> None:
    decision = decide_replay([], _filter())
    assert decision.decision == "skip"
    assert decision.reason == "no_events"


def test_format_decision_renders_checkpoint_line() -> None:
    line = format_decision(EngineDecision(decision="buy", reason="ok", mint="M"))
    assert line == "engine decision=buy reason=ok"
