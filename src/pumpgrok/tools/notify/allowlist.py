"""notify.allowlist: destination gating (TOOL-006, R39).

A destination outside ``notify.allowlist`` is refused, never sent. An empty
allowlist means stdout and file only: every network destination is refused.
"""

from __future__ import annotations

__all__ = ["is_allowlisted", "partition_destinations"]


def is_allowlisted(destination: str, allowlist: tuple[str, ...] | list[str]) -> bool:
    """True only for an exact allowlist member (no prefix or pattern match)."""
    return destination in allowlist


def partition_destinations(
    destinations: tuple[str, ...] | list[str], allowlist: tuple[str, ...] | list[str]
) -> tuple[list[str], list[str]]:
    """Split into (allowed, refused), preserving order; refused are never sent."""
    allowed = [d for d in destinations if d in allowlist]
    refused = [d for d in destinations if d not in allowlist]
    return allowed, refused
