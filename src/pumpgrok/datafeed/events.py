# Temporary observation shape for the Phase 13 tracer RED.

from dataclasses import dataclass


@dataclass(frozen=True)
class CurveObservation:
    mint: str
    ts_utc: str
    s_lamports: int
    t_units: int
    complete: bool
    source: str
