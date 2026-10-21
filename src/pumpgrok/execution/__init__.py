"""Execution boundary: curve-faithful paper fills plus the live guard."""

from __future__ import annotations

import random
from typing import Literal

from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.risk_budget import RiskBudget
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
) -> PaperAdapter:
    """Build the PaperAdapter for live-paper and replay runs.

    The ToolRegistry factory swap stays in plan 04-07; until then callers
    (and tests) construct the adapter directly through this factory.
    ``settings`` is accepted for the future registry signature and ignored.
    """
    del settings
    return PaperAdapter(
        store=store,
        risk=risk,
        ids=ids,
        clock=clock,
        rng=rng,
        budget=RiskBudget(),
        limits=EngineLimits(),
        price_source=price_source,
        source=source,
        curve_origin=curve_origin,
    )
