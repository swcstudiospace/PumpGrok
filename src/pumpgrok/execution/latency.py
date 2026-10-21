"""Seeded confirmation latency (paper-engine.md 2.5, PAPER-001).

Both draws come from the single injected ``random.Random`` (built by
``replay.rng.make_rng``) so replay is deterministic. The adapter awaits
``clock.sleep(latency_s)`` (virtual in replay, R27), then re-reads the curve
and re-runs the stop checks at CONFIRMING. A dropped order (the paper
analogue of UNKNOWN RESULT) is never resubmitted (single-send rule).
"""

from __future__ import annotations

import math
import random

__all__ = [
    "LATENCY_MAX_S",
    "LATENCY_MIN_S",
    "LATENCY_MU",
    "LATENCY_SIGMA",
    "P_DROP",
    "draw_latency",
]

#: lognormal mu = ln(1.2) (REVIEW).
LATENCY_MU = math.log(1.2)
#: lognormal sigma (REVIEW).
LATENCY_SIGMA = 0.5
#: Clip bounds in seconds (REVIEW).
LATENCY_MIN_S = 0.4
LATENCY_MAX_S = 20.0
#: Probability the transaction never lands (REVIEW).
P_DROP = 0.02


def draw_latency(rng: random.Random, *, p_drop: float = P_DROP) -> tuple[float, bool]:
    """Draw ``(latency_s, dropped)`` from the seeded stream.

    The latency is ``clip(lognormal(mu, sigma), 0.4, 20.0)``; the drop is
    ``rng.random() < p_drop``. Exactly two draws, in this order, so a fixed
    seed replays byte-identically.
    """
    latency_s = rng.lognormvariate(LATENCY_MU, LATENCY_SIGMA)
    latency_s = min(LATENCY_MAX_S, max(LATENCY_MIN_S, latency_s))
    dropped = rng.random() < p_drop
    return (latency_s, dropped)
