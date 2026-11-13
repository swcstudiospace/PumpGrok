"""Verified-replay curve timeline shared by the PaperAdapter characterization pins.

A scenario states its curve as ``(offset_s, S, T, complete)`` ticks measured from
the scenario start. The ticks are written as a manifest-checked dataset and bound
through :func:`verify_replay`; the adapter composes that one curve source with
:func:`build_paper_adapter` and ``source="replay"``. No fixture curve is injected.

The fixture curve reads the latest tick at or before the virtual clock, so a tick
that appears stays visible for the rest of the scenario.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from tests.execution.replay_support import replay_authority, tick

from pumpgrok.execution import build_paper_adapter
from pumpgrok.execution.latency import P_DROP

if TYPE_CHECKING:
    import random
    from pathlib import Path

    from pumpgrok.core.ids import Clock, IdFactory
    from pumpgrok.core.risk_budget import RiskBudget
    from pumpgrok.execution.paper_adapter import PaperAdapter
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.risk.engine import RiskEngine
    from pumpgrok.risk.limits import EngineLimits

__all__ = ["Tick", "build_replay_adapter"]

#: ``(offset_s, S_lamports, T_units, complete)``: a curve tick ``offset_s`` after START.
Tick = tuple[float, int, int, bool]


def replay_events(start: float, mint: str, timeline: tuple[Tick, ...]) -> list[dict[str, Any]]:
    """Ticks for ``mint`` at ``start + offset``, in the order given (ts_utc-sorted)."""
    return [
        tick(start + offset, mint, s_lamports, t_units, complete=complete)
        for offset, s_lamports, t_units, complete in timeline
    ]


def build_replay_adapter(
    root: Path,
    clock: Clock,
    store: LedgerStore,
    risk: RiskEngine,
    ids: IdFactory,
    rng: random.Random,
    budget: RiskBudget,
    *,
    mint: str,
    start: float,
    timeline: tuple[Tick, ...],
    limits: EngineLimits | None = None,
    p_drop: float = P_DROP,
) -> PaperAdapter:
    """Adapter whose curve reads come from a verified replay of ``timeline``.

    The ledger must carry ``source == "replay"`` (set by the caller), since the
    factory composes the replay source only under the replay ledger label.
    """
    replay = replay_authority(root, clock, replay_events(start, mint, timeline))
    return build_paper_adapter(
        SimpleNamespace(risk=budget, limits=limits),
        store=store,
        risk=risk,
        ids=ids,
        clock=clock,
        rng=rng,
        replay=replay,
        source="replay",
        p_drop=p_drop,
    )
