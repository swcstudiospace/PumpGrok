"""Execution boundary: curve-faithful paper fills plus the live guard."""

from __future__ import annotations

import random
from typing import Literal

from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.latency import P_DROP
from pumpgrok.execution.paper_adapter import PaperAdapter, PriceSource
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.limits import EngineLimits

__all__ = ["PaperAdapter", "PriceSource", "build_adapter"]


def build_adapter(
    settings: object,
    *,
    store: LedgerStore,
    risk: RiskEngine,
    ids: IdFactory,
    clock: Clock,
    rng: random.Random,
    price_source: PriceSource | None = None,
    source: Literal["paper", "replay", "manual"] = "paper",
    curve_origin: str = "fixture",
    p_drop: float = P_DROP,
) -> PaperAdapter:
    """Build the PaperAdapter for live-paper and replay runs.

    Tests construct the adapter through this factory with scripted curves
    and ``p_drop=0.0``. The operator risk budget and engine limits come
    from ``settings`` (``[risk]`` / ``[limits]``); objects without those
    attributes fall back to defaults.
    """
    budget = getattr(settings, "risk", None)
    if budget is None:
        budget = RiskBudget()
    limits = getattr(settings, "limits", None)
    if limits is None:
        limits = EngineLimits()
    return PaperAdapter(
        store=store,
        risk=risk,
        ids=ids,
        clock=clock,
        rng=rng,
        budget=budget,
        limits=limits,
        price_source=price_source,
        source=source,
        curve_origin=curve_origin,
        p_drop=p_drop,
    )
