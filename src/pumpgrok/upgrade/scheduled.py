"""Scheduled paper promotion: one verdict becomes ledger writes, on a fixed cadence (UPG-05).

apply_candidate turns one gate verdict into ledger writes. A passing verdict
records the promotion evidence and then the active-set row. A blocked verdict
escalates and writes no active-set row. It never reads the autonomy level:
the gate already did, and cli/promotion.py decides whether a check runs at all.

due and mark keep the check on a cadence. They read the injected clock, store
one last-check time in ledger meta, and never sleep.

Imports stay in upgrade/*, ledger/* and core/*. The harness that produces the
verdict lives in cli/promotion.py, so this module never imports backtest,
supervisor or cli at runtime.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

from pumpgrok.ledger.active_set import record_active_set
from pumpgrok.upgrade.escalate import escalate_candidate
from pumpgrok.upgrade.evidence import record_promotion

if TYPE_CHECKING:
    from pumpgrok.backtest.divergence import DivergenceVerdict
    from pumpgrok.core.ids import Clock
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.upgrade.bounds import Bounds
    from pumpgrok.upgrade.gate import GateVerdict
    from pumpgrok.upgrade.params import ParamSet

__all__ = [
    "LAST_CHECK_META_KEY",
    "PROMOTION_CHECK_INTERVAL_S",
    "ApplyOutcome",
    "CheckOutcome",
    "apply_candidate",
    "due",
    "mark",
]

#: Seconds between promotion checks on the injected clock (one hour).
PROMOTION_CHECK_INTERVAL_S = 3600.0

#: Ledger meta key holding the clock time of the last check (derived state only).
LAST_CHECK_META_KEY = "promotion_check_last_s"

#: What apply_candidate can end with: a promotion or an escalation.
ApplyOutcome = Literal["promoted", "escalated"]

#: What one scheduled check can end with. skipped writes nothing; failed promotes nothing.
CheckOutcome = Literal["skipped", "promoted", "escalated", "failed"]


def apply_candidate(
    store: LedgerStore,
    verdict: GateVerdict,
    *,
    candidate_hash: str,
    run_id: str,
    holdout_id: str,
    divergence: DivergenceVerdict,
    trial_count: int,
    bounds: Bounds,
    param_set: ParamSet,
    by: str,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> ApplyOutcome:
    """Promote an eligible verdict, or escalate a blocked one; return the outcome.

    A pass writes the promotion evidence first, so a conflicting manifest stops
    before any activation, then the active-set row. A block writes one Escalation
    and one decision-request note and nothing else. param_set must be the set
    whose hash is candidate_hash, or the call raises ValueError before writing.
    """
    if param_set.content_hash != candidate_hash:
        raise ValueError("param_set does not match candidate_hash: one candidate per check")
    if not verdict.promotion_eligible:
        escalate_candidate(
            store,
            verdict,
            candidate_hash=candidate_hash,
            ts_utc=ts_utc,
            source=source,
            correlation_id=correlation_id,
        )
        return "escalated"
    record_promotion(
        store,
        candidate_hash=candidate_hash,
        run_id=run_id,
        holdout_id=holdout_id,
        divergence=divergence,
        trial_count=trial_count,
        bounds=bounds,
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
    )
    record_active_set(
        store,
        param_set,
        by,
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
    )
    return "promoted"


def due(store: LedgerStore, clock: Clock, interval_s: float) -> bool:
    """True when no check has been marked yet or interval_s has passed since the last mark.

    A malformed or non-finite stored time counts as due: the check still runs
    only when the autonomy level allows it, so a corrupt meta row cannot
    promote anything on its own.
    """
    raw = store.get_meta(LAST_CHECK_META_KEY)
    if raw is None:
        return True
    try:
        last = float(raw)
    except ValueError:
        return True
    if not math.isfinite(last):
        return True
    return clock.now() - last >= interval_s


def mark(store: LedgerStore, clock: Clock) -> None:
    """Record the clock time of this check; the next due() measures from it."""
    store.set_meta(LAST_CHECK_META_KEY, repr(clock.now()))
