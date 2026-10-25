"""SOL/lamport unit constants and conversions (INT-04, D-05).

The single SOL-to-lamports implementation (ROUND_HALF_UP). Every module
imports from here; no ``LAMPORTS_PER_SOL`` or ``1_000_000_000`` copy lives
elsewhere in ``src/pumpgrok``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

LAMPORTS_PER_SOL = 1_000_000_000


def sol_to_lamports(value: Decimal) -> int:
    """Decimal SOL to integer lamports, ROUND_HALF_UP (the one rule, R28)."""
    return int((value * LAMPORTS_PER_SOL).to_integral_value(rounding=ROUND_HALF_UP))


def lamports_to_sol(value: Decimal) -> Decimal:
    """Lamport-scaled Decimal to SOL (divide by the one constant; exact)."""
    return value / LAMPORTS_PER_SOL


def split_lamports(lamports: int) -> tuple[int, int]:
    """(whole SOL, remainder lamports) of the absolute amount for 9dp rendering."""
    return divmod(abs(int(lamports)), LAMPORTS_PER_SOL)
