"""Execution boundary: curve-faithful paper fills plus the live guard."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Literal

from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.execution.latency import P_DROP
from pumpgrok.execution.paper_adapter import PaperAdapter, PriceSource
from pumpgrok.execution.paper_factory import VerifiedReplay, build_paper_adapter, verify_replay
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.risk.engine import RiskEngine

if TYPE_CHECKING:
    from collections.abc import Callable

    from pumpgrok.datafeed.price import LivePriceSource
    from pumpgrok.execution.paper_adapter.models import CurveSnapshot

__all__ = [
    "PaperAdapter",
    "PriceSource",
    "VerifiedReplay",
    "build_adapter",
    "build_paper_adapter",
    "verify_replay",
]


def build_adapter(
    settings: object,
    *,
    store: LedgerStore,
    risk: RiskEngine,
    ids: IdFactory,
    clock: Clock,
    rng: random.Random,
    price_source: PriceSource | None = None,
    replay: VerifiedReplay | None = None,
    live_source: LivePriceSource | None = None,
    reserves_observer: Callable[[CurveSnapshot], None] | None = None,
    source: Literal["paper", "replay", "manual"] = "paper",
    p_drop: float = P_DROP,
) -> PaperAdapter:
    """Delegate to :func:`build_paper_adapter`; kept for existing callers.

    Entries need ``replay`` (from :func:`verify_replay`). Without it every BUY is
    refused, including reads from injected or scripted curve sources; sells and
    exits still read ``price_source``.
    """
    return build_paper_adapter(
        settings,
        store=store,
        risk=risk,
        ids=ids,
        clock=clock,
        rng=rng,
        price_source=price_source,
        replay=replay,
        live_source=live_source,
        reserves_observer=reserves_observer,
        source=source,
        p_drop=p_drop,
    )
