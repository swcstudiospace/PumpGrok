#!/usr/bin/env python3
"""Measure Grok call reduction with and without the gateway (GRK-11).

Given --dataset, run the gateway (prefilter + cache) over the recorded
dataset on FixtureClock and print before/after JSON. calls_before is the
naive every-event-a-call count; calls_after is the gateway transport count.
Exit non-zero when admitted candidates are too few or the ratio is too
high. No network, no secrets in output (counts only).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pumpgrok.grok import GatewayRequest, GrokGateway
from pumpgrok.grok.budget import BudgetExhausted, LayeredBudget
from pumpgrok.replay.clock import FixtureClock


def _load_events(dataset: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (dataset / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _score(event: dict[str, Any]) -> int:
    supply = event.get("S", 0)
    return int(supply) // 1_000_000 % 100


async def _measure(events: list[dict[str, Any]], budget: int) -> tuple[int, int]:
    clock = FixtureClock()
    calls = 0

    async def transport(request: GatewayRequest) -> str:
        nonlocal calls
        calls += 1
        return '{"ok": 1}'

    gateway = GrokGateway(
        clock=clock,
        budget=LayeredBudget(window_cap=budget, agent_cap=budget, global_cap=budget),
        transport=transport,
    )
    admitted = 0
    try:
        for event in events:
            kind = str(event.get("kind", "tick"))
            mint = str(event.get("mint", "x"))
            request = GatewayRequest(
                agent="signal",
                prompt=f"{kind}:{mint}",
                consequence_id=f"{kind}:{mint}",
                score=_score(event),
            )
            result = await gateway.call(request)
            if result is not None:
                admitted += 1
    except BudgetExhausted:
        return -1, admitted
    return calls, admitted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure Grok calls before/after the gateway")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--min-candidates", type=int, default=0)
    parser.add_argument("--max-ratio", type=float, default=0.2)
    parser.add_argument("--budget", type=int, default=10_000)
    args = parser.parse_args(argv)

    dataset = Path(args.dataset)
    events = _load_events(dataset)
    calls_before = len(events)
    calls_after, admitted = asyncio.run(_measure(events, args.budget))
    ratio = calls_after / calls_before if calls_before else 0.0
    print(
        json.dumps(
            {
                "dataset": dataset.name,
                "calls_after": calls_after,
                "calls_before": calls_before,
                "admitted_candidates": admitted,
                "ratio": ratio,
            },
            sort_keys=True,
        )
    )
    if calls_after < 0:
        return 2
    if admitted < args.min_candidates:
        return 1
    if calls_after > args.max_ratio * calls_before:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
