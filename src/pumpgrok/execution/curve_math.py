"""Pure integer bonding-curve math (paper-engine.md 2.2, PAPER-001, R28).

Pre-graduation pump.fun is a constant-product curve on virtual reserves.
All inputs and outputs are integers in base units: ``S`` is virtual SOL
reserves in lamports, ``T`` is virtual token reserves in token base units
(6 decimals), ``x`` is lamports in, ``t`` is token units in. Divisions
floor (``//``); the only ``Decimal`` values are the derived price and the
impact ratios. No I/O, no clock, no randomness.
"""

from __future__ import annotations

from decimal import Decimal

__all__ = [
    "buy_out",
    "impact_buy",
    "impact_sell",
    "post_buy",
    "post_sell",
    "sell_out",
    "spot",
]


def spot(s_lamports: int, t_units: int) -> Decimal:
    """Lamports per token base unit at the current reserves."""
    if t_units <= 0:
        raise ValueError("token reserves must be positive")
    return Decimal(s_lamports) / Decimal(t_units)


def buy_out(s_lamports: int, t_units: int, x_lamports: int) -> int:
    """Token base units received for ``x_lamports`` lamports in (ExactIn).

    ``x_lamports`` is net of the venue fee: the caller subtracts the fee
    before calling. Floored; ``k = S * T`` is preserved up to the floor.
    """
    if s_lamports <= 0 or t_units <= 0:
        raise ValueError("reserves must be positive")
    if x_lamports <= 0:
        raise ValueError("lamports in must be positive")
    return t_units * x_lamports // (s_lamports + x_lamports)


def sell_out(s_lamports: int, t_units: int, t_units_in: int) -> int:
    """Lamports received (gross of venue fee) for ``t_units_in`` tokens in."""
    if s_lamports <= 0 or t_units <= 0:
        raise ValueError("reserves must be positive")
    if t_units_in <= 0:
        raise ValueError("token units in must be positive")
    return s_lamports * t_units_in // (t_units + t_units_in)


def impact_buy(s_lamports: int, x_lamports: int) -> Decimal:
    """Fractional price impact of a buy: ``x / S``."""
    if s_lamports <= 0:
        raise ValueError("SOL reserves must be positive")
    return Decimal(x_lamports) / Decimal(s_lamports)


def impact_sell(t_units: int, t_units_in: int) -> Decimal:
    """Fractional price impact of a sell: ``t / (T + t)``."""
    if t_units <= 0:
        raise ValueError("token reserves must be positive")
    return Decimal(t_units_in) / Decimal(t_units + t_units_in)


def post_buy(s_lamports: int, t_units: int, x_lamports: int) -> tuple[int, int]:
    """Reserves after a buy fill of ``x_lamports`` (net of venue fee)."""
    return (s_lamports + x_lamports, t_units - buy_out(s_lamports, t_units, x_lamports))


def post_sell(s_lamports: int, t_units: int, t_units_in: int) -> tuple[int, int]:
    """Reserves after a sell fill of ``t_units_in`` token units."""
    return (s_lamports - sell_out(s_lamports, t_units, t_units_in), t_units + t_units_in)
