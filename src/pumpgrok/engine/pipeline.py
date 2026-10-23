"""Replay engine pipeline: fixture ticks to engine candidates and verdicts.

Port of the vendor ``pipeline.py`` stage flow minus everything live: no
monitor stream, no analyzer network fetch, no Grok calls, no executor, no
risk book, no ``LiveGateError`` path (live refusal is Phase 4). The offline
stage is the fail-closed launch filter (``engine/monitor.py``
``passes_filter``), run once per fixture tick at that tick's own time.
Approval and placement happen downstream: the risk engine and PaperAdapter
decide each BUY candidate in the supervisor's sniper seat.

Tick-to-candidate adapter: a tick carries only the evidence it records.
``name`` and ``image_uri`` give metadata, ``created_ts_utc`` gives the age,
``unique_buyers`` gives buyer evidence, and ``S`` (curve reserves, lamports)
gives curve progress. An absent field stays absent and fails closed at the
matching gate: no name is invented, no buyer count is assumed. Nothing is
bypassed, so the note text never has to say which gates were skipped.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pumpgrok.config.settings import FilterSettings
from pumpgrok.engine.models import Token
from pumpgrok.engine.monitor import CURVE_COMPLETION_SOL, passes_filter
from pumpgrok.replay.clock import parse_ts_utc

#: Decisions the replay pipeline can report. ``buy`` means the candidate
#: survived the offline filter; anything else is a skip with a reason.
SKIP = "skip"
BUY = "buy"

#: Reason a candidate carries no buyer evidence; the checkpoint asserts it.
DATA_UNAVAILABLE = "data_unavailable"

LAMPORTS_PER_SOL = 1_000_000_000


@dataclass(frozen=True)
class EngineDecision:
    """One replay verdict: skip or buy, the filter reason, and the mint."""

    decision: str
    reason: str
    mint: str


@dataclass(frozen=True)
class CandidateVerdict:
    """One tick's candidate, the tick time it was judged at, and the filter verdict."""

    ts: float
    token: Token
    verdict: EngineDecision


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _created_epoch(value: object) -> float:
    """Creation epoch from ``created_ts_utc``; absent or malformed is 0.0 (too young)."""
    text = _text(value)
    if text is None:
        return 0.0
    try:
        return parse_ts_utc(text)
    except ValueError:
        return 0.0


def tick_to_candidate(event: Mapping[str, Any]) -> Token:
    """Map one replay tick to a candidate carrying exactly the evidence it records."""
    mint = str(event.get("mint", ""))
    reserves = event.get("S")
    if isinstance(reserves, int) and not isinstance(reserves, bool):
        sol_in_curve = reserves / LAMPORTS_PER_SOL
        curve_progress = min(1.0, sol_in_curve / CURVE_COMPLETION_SOL)
    else:
        # Unknown reserves read as a full curve, so the admission gate fails closed.
        sol_in_curve = 0.0
        curve_progress = 1.0
    return Token(
        mint=mint,
        name=_text(event.get("name")),
        image_uri=_text(event.get("image_uri")),
        created_timestamp=_created_epoch(event.get("created_ts_utc")),
        unique_buyers=_count(event.get("unique_buyers")),
        curve_progress=curve_progress,
        sol_in_curve=sol_in_curve,
    )


def decide_token(token: Token, filter_cfg: FilterSettings, now: float) -> EngineDecision:
    """Run the only offline stage over one candidate."""
    passed, reason = passes_filter(token, filter_cfg, now)
    if passed:
        return EngineDecision(decision=BUY, reason="ok", mint=token.mint)
    return EngineDecision(decision=SKIP, reason=reason, mint=token.mint)


def evaluate_candidates(
    events: Sequence[Mapping[str, Any]], filter_cfg: FilterSettings
) -> list[CandidateVerdict]:
    """Judge every tick as its own candidate, at that tick's own time, in stored order."""
    verdicts: list[CandidateVerdict] = []
    for event in events:
        ts = parse_ts_utc(str(event["ts_utc"]))
        token = tick_to_candidate(event)
        verdicts.append(
            CandidateVerdict(ts=ts, token=token, verdict=decide_token(token, filter_cfg, ts))
        )
    return verdicts


def decide_replay(
    events: Sequence[Mapping[str, Any]], filter_cfg: FilterSettings
) -> EngineDecision:
    """Summarise the candidate verdicts: the first BUY wins, else the first skip.

    No events means a skip with ``no_events``: there is nothing to decide on.
    The per-candidate verdicts, not this summary, drive placement.
    """
    verdicts = evaluate_candidates(events, filter_cfg)
    if not verdicts:
        return EngineDecision(decision=SKIP, reason="no_events", mint="")
    for candidate in verdicts:
        if candidate.verdict.decision == BUY:
            return EngineDecision(decision=BUY, reason="ok", mint=candidate.verdict.mint)
    return verdicts[0].verdict


def format_decision(decision: EngineDecision) -> str:
    """Stdout and note-text rendering of a replay verdict."""
    return f"engine decision={decision.decision} reason={decision.reason}"
