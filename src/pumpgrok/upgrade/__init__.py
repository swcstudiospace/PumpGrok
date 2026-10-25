"""Bounded paper self-upgrade package (UPG-01).

Content-hashed parameter sets validated against version-controlled
bounds. Paper only: this package exposes no CLI verb and imports nothing
from pumpgrok.execution.live (proven by tests/upgrade/test_no_live_imports.py).
"""

from __future__ import annotations

from pumpgrok.upgrade.bounds import (
    Bounds,
    KeyBound,
    OutOfBoundsError,
    default_bounds_path,
    load_bounds,
    validate_against_bounds,
)
from pumpgrok.upgrade.params import ParamSet

__all__ = [
    "Bounds",
    "KeyBound",
    "OutOfBoundsError",
    "ParamSet",
    "default_bounds_path",
    "load_bounds",
    "validate_against_bounds",
]
