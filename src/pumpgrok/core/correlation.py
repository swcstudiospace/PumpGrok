"""Correlation helpers: ULID roots and child spans (OBS-002).

The root is a plain ULID; children append `.<n>`. The ledger `correlation_id`
column stores the root. Context binding lives in `ids.py`.
"""

from __future__ import annotations

from pumpgrok.core.ids import CorrelationId


def root_of(correlation_id: str) -> str:
    """Return the ULID root of a correlation id or child span."""
    return correlation_id.split(".", 1)[0]


def is_child_span(correlation_id: str) -> bool:
    """True when the id carries a `.<n>` span suffix."""
    head, dot, tail = correlation_id.partition(".")
    return bool(dot) and bool(head) and tail.isdigit()


def child_span(root: str, n: int) -> CorrelationId:
    """Build the n-th child span of a ULID root (1-based)."""
    if n < 1:
        raise ValueError(f"span counter must be >= 1, got {n}")
    return CorrelationId(f"{root_of(root)}.{n}")
