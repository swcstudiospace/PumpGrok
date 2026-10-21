"""Characterization: replay pipeline (STRUCT-003).

Pins ``engine/pipeline.py``: the tick-to-candidate adapter maps smoke ticks
to evidence-less candidates, so the fail-closed filter yields
``data_unavailable`` and the replay decision is skip. No live stages exist
here by design (no monitor stream, no analyzer fetch, no model lookup).
"""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.config.settings import FilterSettings
from pumpgrok.engine.monitor import passes_filter
from pumpgrok.engine.pipeline import (
    DATA_UNAVAILABLE,
    EngineDecision,
    decide_replay,
    decide_token,
    format_decision,
    tick_to_candidate,
)

SMOKE = Path(__file__).resolve().parent.parent / "fixtures" / "replay" / "smoke"


def _smoke_events() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (SMOKE / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _filter() -> FilterSettings:
    return FilterSettings()


def test_tick_maps_to_evidence_less_candidate() -> None:
    events = _smoke_events()
    token = tick_to_candidate(events[0], now=1_767_225_603.0)
    assert token.mint == events[0]["mint"]
    assert token.unique_buyers is None
    assert token.has_metadata


def test_candidate_hits_the_evidence_gate() -> None:
    token = tick_to_candidate(_smoke_events()[0], now=1_767_225_603.0)
    assert passes_filter(token, _filter(), 1_767_225_603.0) == (False, DATA_UNAVAILABLE)


def test_decide_token_reports_skip_with_reason() -> None:
    token = tick_to_candidate(_smoke_events()[1], now=1_767_225_603.0)
    decision = decide_token(token, _filter(), 1_767_225_603.0)
    assert decision == EngineDecision(decision="skip", reason=DATA_UNAVAILABLE, mint=token.mint)


def test_decide_replay_over_smoke_is_one_skip() -> None:
    decision = decide_replay(_smoke_events(), _filter(), 1_767_225_603.0)
    assert decision.decision == "skip"
    assert decision.reason == DATA_UNAVAILABLE


def test_decide_replay_with_no_events_skips() -> None:
    decision = decide_replay([], _filter(), 0.0)
    assert decision.decision == "skip"
    assert decision.reason == "no_events"


def test_format_decision_renders_checkpoint_line() -> None:
    line = format_decision(EngineDecision(decision="skip", reason=DATA_UNAVAILABLE, mint="M"))
    assert line == "engine decision=skip reason=data_unavailable"
