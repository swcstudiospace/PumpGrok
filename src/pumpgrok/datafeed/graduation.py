"""Graduation check: a completed curve refuses entry (MKT-07).

Exit and flatten paths never consult this check; only entries do.
"""

from __future__ import annotations


def entry_refused(*, complete: bool) -> bool:
    """True when a completed curve refuses a new entry."""
    return complete


def graduation_refusal_reason(*, complete: bool) -> str | None:
    """Human-readable refusal reason, or None when entry is allowed."""
    if complete:
        return "graduated: curve is complete"
    return None
