"""Measure the Grok calls the admission gateway saves on one replay dataset (GRK-11, EVT-12).

Two counts over the same dataset, both from the real stack:

- before_calls: raw candidate rows, i.e. every ``tick`` row. Each would call Grok with no
  prefilter and no cache.
- after_calls: Grok transport calls ``pumpgrok.grok.gateway.GrokGateway`` actually makes when
  the rows are replayed from ``llm.jsonl`` through ``admit_replay``. Prefilter skips, cache
  hits and coalesced answers cost no call.
  Each mint's cooldown starts at its last admitted candidate, as in the live flow.

ratio = after_calls / before_calls. The gate passes only when ratio <= max-ratio and the
number of prefilter-admitted candidates >= min-candidates.

Nothing is skipped or zero-filled. A malformed candidate row, an admitted candidate the gateway
does not answer, a missing recorded outcome, or a dataset that fails manifest verification is an
input error. Nothing is printed on stdout for an input error.

Usage:
    .venv/bin/python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/evidence-50 \
        --max-ratio 0.2

Exit codes: 0 gate pass; 1 gate fail; 2 input error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.config.settings import GrokSettings
from pumpgrok.core.errors import PumpgrokError
from pumpgrok.engine.agents.base import gateway_candidate
from pumpgrok.engine.agents.narrative import NarrativeAgent
from pumpgrok.engine.models import Token
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import GrokGateway, GrokRequest
from pumpgrok.grok.transport import ReplayTransport, admit_replay
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset, read_jsonl
from pumpgrok.replay.recorder import ReplayLlm

CANDIDATE_KIND = "tick"
LLM_NAME = "llm.jsonl"
DEFAULT_MIN_CANDIDATES = 50
_ANSWERED = frozenset({"fresh", "cache_hit", "coalesced"})


class MeasureError(Exception):
    """The dataset cannot be measured. Exit 2; nothing is printed on stdout."""


@dataclass(frozen=True)
class Measurement:
    dataset: str
    provenance: str | None
    raw_candidates: int
    admitted: int
    before_calls: int
    after_calls: int

    @property
    def ratio(self) -> float:
        return self.after_calls / self.before_calls


class _CountingTransport:
    """Counts every call the gateway makes to the transport. The gateway reaches the transport
    only after the prefilter, cache, breaker and budget have all admitted the request."""

    def __init__(self, replay: ReplayTransport) -> None:
        self._replay = replay
        self.calls = 0

    async def __call__(self, request: GrokRequest, text: str) -> str:
        self.calls += 1
        return await self._replay(request, text)


def request_for_row(
    number: int,
    row: dict[str, Any],
    *,
    agent: NarrativeAgent,
    clock: FixtureClock,
    last_admitted: dict[str, float],
) -> GrokRequest:
    """Advance the clock to the row, then rebuild the request ``GrokAgent.run`` would build.

    ``number`` is the 1-based line number of the row in events.jsonl, for error messages.
    ``last_admitted`` maps each mint to the decision time of its last admitted candidate.
    """
    try:
        clock.advance_to(parse_ts_utc(row["ts_utc"]))
        token = Token(
            mint=row["mint"],
            name=row["name"],
            image_uri=row["image_uri"],
            created_timestamp=parse_ts_utc(row["created_ts_utc"]),
            unique_buyers=row["unique_buyers"],
        )
        candidate = gateway_candidate(
            token,
            prerank=Decimal(str(row["prerank"])),
            first_trade_at=parse_ts_utc(row["first_trade_ts_utc"]),
            last_decision_at=last_admitted.get(row["mint"]),
        )
        text = agent.build_user_message(token)
    except KeyError as exc:
        raise MeasureError(
            f"candidate row {number} is malformed: missing field {exc.args[0]!r}"
        ) from None
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise MeasureError(f"candidate row {number} is malformed: {exc}") from None
    return GrokRequest(
        event_id=f"{CANDIDATE_KIND}-{number:06d}",
        agent=agent.name,
        model=agent.model,
        prompt_sha=agent.prompt_sha,
        schema=agent.schema_sha,
        input={},
        text=text,
        candidate=candidate,
    )


def narrative_agent(gateway: GrokGateway, clock: FixtureClock) -> NarrativeAgent:
    """The production narrative agent, which owns the prompt, schema and model constants."""
    return NarrativeAgent(GrokSettings(), gateway=gateway, clock=clock)


async def measure(dataset_dir: Path) -> Measurement:
    """Replay every candidate row through the real gateway and count the calls it makes."""
    if not await asyncio.to_thread(dataset_dir.is_dir):
        raise MeasureError(f"dataset directory not found: {dataset_dir}")
    # Verifies the manifest, every listed digest and stray data files before any row is read.
    dataset = load_dataset(dataset_dir)
    rows = [
        (number, row)
        for number, row in enumerate(dataset.events, 1)
        if row.get("kind") == CANDIDATE_KIND
    ]
    if not rows:
        raise MeasureError(
            f"dataset has no raw candidate rows (kind {CANDIDATE_KIND!r}); the ratio is undefined"
        )
    llm_rows = read_jsonl(dataset_dir / LLM_NAME) if LLM_NAME in dataset.manifest.sha256 else []
    replay = ReplayTransport(ReplayLlm.from_rows(llm_rows))

    admitted = 0
    with tempfile.TemporaryDirectory(prefix="measure-grok-") as scratch:
        clock = FixtureClock(start=parse_ts_utc(rows[0][1]["ts_utc"]))
        transport = _CountingTransport(replay)
        gateway = GrokGateway(
            clock=clock,
            transport=transport,
            cache=ResponseCache(Path(scratch) / "cache.sqlite", clock),
            budget=LayeredBudget(Path(scratch) / "budget.sqlite", clock),
        )
        agent = narrative_agent(gateway, clock)
        last_admitted: dict[str, float] = {}
        for number, row in rows:
            request = request_for_row(
                number, row, agent=agent, clock=clock, last_admitted=last_admitted
            )
            try:
                outcome = await admit_replay(gateway, replay, request, clock=clock)
            except PumpgrokError as exc:
                raise MeasureError(f"candidate row {number}: {exc.code}: {exc}") from None
            if outcome.status == "prefilter_skip":
                continue
            if outcome.status not in _ANSWERED or outcome.response is None:
                raise MeasureError(
                    f"candidate row {number} was admitted but not answered: "
                    f"{outcome.status} ({outcome.reason})"
                )
            # The gateway admitted this candidate: its mint's cooldown starts at this decision.
            last_admitted[row["mint"]] = clock.now()
            admitted += 1

    return Measurement(
        dataset=dataset.manifest.dataset,
        provenance=dataset.manifest.provenance,
        raw_candidates=len(rows),
        admitted=admitted,
        before_calls=len(rows),
        after_calls=transport.calls,
    )


def report(measurement: Measurement, *, max_ratio: float, min_candidates: int) -> dict[str, Any]:
    gate_ok = measurement.ratio <= max_ratio and measurement.admitted >= min_candidates
    return {
        "dataset": measurement.dataset,
        "provenance": measurement.provenance,
        "raw_candidates": measurement.raw_candidates,
        "admitted": measurement.admitted,
        "before_calls": measurement.before_calls,
        "after_calls": measurement.after_calls,
        "ratio": measurement.ratio,
        "gate": "pass" if gate_ok else "fail",
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dataset", type=Path, required=True, help="replay dataset directory")
    parser.add_argument(
        "--min-candidates",
        type=int,
        default=DEFAULT_MIN_CANDIDATES,
        help=f"minimum prefilter-admitted candidates (default {DEFAULT_MIN_CANDIDATES})",
    )
    parser.add_argument(
        "--max-ratio", type=float, required=True, help="maximum after_calls / before_calls"
    )
    args = parser.parse_args(argv)
    if args.min_candidates < 0:
        parser.error("--min-candidates must be >= 0")
    if not math.isfinite(args.max_ratio) or args.max_ratio < 0:
        parser.error("--max-ratio must be a finite number >= 0")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        measurement = asyncio.run(measure(args.dataset))
    except (MeasureError, PumpgrokError, ValueError, OSError) as exc:
        print(f"measure_grok_calls: error: {exc}", file=sys.stderr)
        return 2
    result = report(measurement, max_ratio=args.max_ratio, min_candidates=args.min_candidates)
    print(json.dumps(result))
    return 0 if result["gate"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
