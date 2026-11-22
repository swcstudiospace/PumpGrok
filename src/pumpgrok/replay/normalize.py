"""Fixture-shape tick normalization into CurveTick (REC-03).

Recorded fixture events (S/T reserves plus optional evidence fields)
map onto CurveTick: virtual reserves take S/T, real reserves mirror
them when unrecorded, supply defaults to zero, and evidence fields are
dropped (they are not tick state). CurveTick-shaped records pass
through validation unchanged.
"""

from __future__ import annotations

from typing import Any

from pumpgrok.datafeed.events import CurveTick

__all__ = ["to_curve_tick"]


def to_curve_tick(record: dict[str, Any]) -> CurveTick:
    """One CurveTick from a CurveTick-shaped or fixture-shaped record."""
    if "virtual_sol_reserves_lamports" in record:
        return CurveTick.model_validate(record)
    s_lamports = record.get("S")
    t_units = record.get("T")
    if not isinstance(s_lamports, int) or not isinstance(t_units, int):
        raise ValueError("tick record carries no integer S/T reserves")
    return CurveTick(
        mint=str(record["mint"]),
        ts_utc=str(record["ts_utc"]),
        virtual_sol_reserves_lamports=s_lamports,
        virtual_token_reserves_units=t_units,
        real_sol_reserves_lamports=s_lamports,
        real_token_reserves_units=t_units,
        total_supply_units=0,
        complete=bool(record.get("complete", False)),
        curve_source="replay",
    )
