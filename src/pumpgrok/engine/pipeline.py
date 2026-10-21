"""Replay engine pipeline: fixture ticks to one engine decision.

Port of the vendor ``pipeline.py`` stage flow minus everything live: no
monitor stream, no analyzer network fetch, no Grok calls, no executor, no
risk book, no ``LiveGateError`` path (live refusal is Phase 4). The only
stage that can run offline is the fail-closed launch filter
(``engine/monitor.py`` ``passes_filter``), so the replay decision is the
filter verdict over evidence-less candidates. The CLI calls only the pure
functions here, never ``LaunchMonitor.stream`` and never a startup
``GET /v1/models`` (the skipped model resolution is recorded in the
``JournalNote`` text instead).

Tick-to-candidate adapter: smoke ticks carry bonding-curve snapshots
(``mint``, ``S``, ``T``, ``complete``), never buyer evidence. Each tick
becomes a candidate with ``unique_buyers=None``. The metadata and age gates
are satisfied by construction (a replay name plus image and a mature
timestamp) so the checkpoint exercises the fail-closed evidence gate, not
the age gate over a three-second fixture; the curve snapshot is likewise
not re-filtered. This is a documented replay convention, not hidden
fabrication: the note text says exactly which gates were bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pumpgrok.config.settings import FilterSettings
from pumpgrok.engine.models import Token
from pumpgrok.engine.monitor import passes_filter

#: Decisions the replay pipeline can report. ``buy`` means the candidate
#: survived the only offline stage; anything else is a skip with a reason.
SKIP = "skip"
BUY = "buy"

#: Replay candidates are evidence-less by construction, so this is the
#: reason the checkpoint asserts.
DATA_UNAVAILABLE = "data_unavailable"

#: Placeholder identity that satisfies the metadata gate by construction.
#: The smoke dataset carries no metadata fields, so the adapter marks the
#: candidate present and says so in the note text.
REPLAY_NAME_PREFIX = "replay"
REPLAY_IMAGE_URI = "replay:evidence-less"

#: Mature age (seconds) assigned to replay candidates so the age gate, which
#: a three-second fixture could never satisfy, does not mask the evidence gate.
REPLAY_AGE_SECONDS = 3600.0


@dataclass(frozen=True)
class EngineDecision:
    """One replay verdict: skip or buy, the filter reason, and the mint."""

    decision: str
    reason: str
    mint: str


def tick_to_candidate(event: dict[str, Any], now: float) -> Token:
    """Map one replay tick to an evidence-less candidate.

    The tick contributes only the mint. Buyer evidence is never present in
    ticks, so ``unique_buyers`` stays ``None`` and ``passes_filter`` fails
    closed with ``data_unavailable``. Metadata and age are satisfied by
    construction (see module docstring) so the evidence gate is reached.
    """
    mint = str(event.get("mint", ""))
    return Token(
        mint=mint,
        name=f"{REPLAY_NAME_PREFIX}-{mint[:8]}" if mint else REPLAY_NAME_PREFIX,
        image_uri=REPLAY_IMAGE_URI,
        created_timestamp=now - REPLAY_AGE_SECONDS,
        unique_buyers=None,
        curve_progress=0.0,
    )


def decide_token(token: Token, filter_cfg: FilterSettings, now: float) -> EngineDecision:
    """Run the only offline stage over one candidate."""
    passed, reason = passes_filter(token, filter_cfg, now)
    if passed:
        return EngineDecision(decision=BUY, reason="ok", mint=token.mint)
    return EngineDecision(decision=SKIP, reason=reason, mint=token.mint)


def decide_replay(
    events: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    filter_cfg: FilterSettings,
    now: float,
) -> EngineDecision:
    """Fold fixture events into one engine decision.

    Every event becomes an evidence-less candidate; the first terminal
    verdict wins. No events means a skip with ``no_events``: there is
    nothing to decide on.
    """
    if not events:
        return EngineDecision(decision=SKIP, reason="no_events", mint="")
    first = decide_token(tick_to_candidate(events[0], now), filter_cfg, now)
    if first.decision == SKIP:
        return first
    for event in events[1:]:
        verdict = decide_token(tick_to_candidate(event, now), filter_cfg, now)
        if verdict.decision == SKIP:
            return verdict
    return EngineDecision(decision=BUY, reason="ok", mint=first.mint)


def format_decision(decision: EngineDecision) -> str:
    """Stdout and note-text rendering of a replay verdict."""
    return f"engine decision={decision.decision} reason={decision.reason}"
