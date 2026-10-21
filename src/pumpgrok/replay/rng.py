"""Seeded randomness (paper-engine.md 4.2).

`make_rng` is the only `random.Random` constructor in src/pumpgrok, and the only
ambient-randomness-free path: `random.random()` and unseeded `Random()` are rejected by
tests/safety/test_static_guards.py.
"""

from __future__ import annotations

import random

DEFAULT_SEED = 20260101


def make_rng(seed: int = DEFAULT_SEED) -> random.Random:
    return random.Random(seed)
