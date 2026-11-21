"""Journal rollup on journal wakes (RT-01).

Counts delivered events by kind into a deterministic rollup record. Runs
only for journal wakes; other seats never see journal state.
"""

from __future__ import annotations

from dataclasses import dataclass

from pumpgrok.supervisor.scheduler.wake import Wake


@dataclass(frozen=True)
class Rollup:
    journal_wakes: int
    kinds: dict[str, int]


def rollup(wakes: list[Wake]) -> Rollup:
    journal = [wake for wake in wakes if wake.seat == "bot-09-journal"]
    by_kind: dict[str, int] = {}
    for wake in journal:
        key = str(wake.event.kind)
        by_kind[key] = by_kind.get(key, 0) + 1
    return Rollup(journal_wakes=len(journal), kinds=by_kind)
