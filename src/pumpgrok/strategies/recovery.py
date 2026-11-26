"""Strategy restart-recovery state (RT-04 library half).

:class:`RecoveryStore` persists per-strategy tapes, trailing price peaks,
and probation flags to one JSON file through atomic replacement. A fresh
instance pointing at the same file restores them byte-identically (tape
ticks, peaks, probation all round-trip). Corrupt or half-written state
fails closed with :class:`CorruptRecovery` instead of a silent default.
Library level only: no supervisor composition wiring happens here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pumpgrok.core.atomic_write import atomic_write_json
from pumpgrok.core.errors import PumpgrokError
from pumpgrok.strategies.tape import Tape, Tick

__all__ = ["CorruptRecovery", "RecoverySnapshot", "RecoveryStore"]


class CorruptRecovery(PumpgrokError):
    """Recovery state does not match the saved shape."""

    code = "corrupt_recovery"


@dataclass(frozen=True)
class RecoverySnapshot:
    """Restored per-strategy state: tape, peaks, probation."""

    strategy_id: str
    ticks: tuple[Tick, ...] = ()
    peaks: dict[str, int] = field(default_factory=dict)
    probation: dict[str, bool] = field(default_factory=dict)


@dataclass
class RecoveryStore:
    """File-backed recovery state for every strategy (one JSON file)."""

    path: Path

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CorruptRecovery(f"recovery file is not JSON: {self.path}") from exc
        if not isinstance(raw, dict):
            raise CorruptRecovery(f"recovery file must hold a mapping: {self.path}")
        return raw

    def save(
        self,
        strategy_id: str,
        *,
        tape: Tape,
        peaks: dict[str, int],
        probation: dict[str, bool],
    ) -> None:
        """Persist one strategy's state atomically (peaks integer lamports)."""
        state = self._read()
        state[strategy_id] = {
            "ticks": [
                {
                    "ts": tick.ts,
                    "mint": tick.mint,
                    "price_lamports": tick.price_lamports,
                    "buyers": tick.buyers,
                    "created_ts": tick.created_ts,
                    "curve_progress": tick.curve_progress,
                }
                for tick in tape.ticks
            ],
            "peaks": dict(peaks),
            "probation": dict(probation),
        }
        atomic_write_json(self.path, state)

    def load(self, strategy_id: str) -> RecoverySnapshot:
        """Restore one strategy's state; empty when never saved."""
        state = self._read()
        record = state.get(strategy_id)
        if record is None:
            return RecoverySnapshot(strategy_id=strategy_id)
        if not isinstance(record, dict):
            raise CorruptRecovery(f"recovery entry for {strategy_id!r} is not a mapping")
        ticks: list[Tick] = []
        for item in record.get("ticks", []):
            if not isinstance(item, dict):
                raise CorruptRecovery(f"recovery tick for {strategy_id!r} is not a mapping")
            try:
                ticks.append(
                    Tick(
                        ts=float(item["ts"]),
                        mint=str(item["mint"]),
                        price_lamports=int(item["price_lamports"]),
                        buyers=int(item.get("buyers", 0)),
                        created_ts=(
                            None if item.get("created_ts") is None else float(item["created_ts"])
                        ),
                        curve_progress=float(item.get("curve_progress", 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise CorruptRecovery(
                    f"malformed recovery tick for {strategy_id!r}: {item!r}"
                ) from exc
        peaks = record.get("peaks", {})
        probation = record.get("probation", {})
        if not isinstance(peaks, dict) or not isinstance(probation, dict):
            raise CorruptRecovery(f"recovery peaks/probation for {strategy_id!r} malformed")
        for mint, peak in peaks.items():
            if isinstance(peak, bool) or not isinstance(peak, int):
                raise CorruptRecovery(f"recovery peak for {strategy_id!r}/{mint!r} not int")
        return RecoverySnapshot(
            strategy_id=strategy_id,
            ticks=tuple(ticks),
            peaks={str(mint): int(peak) for mint, peak in peaks.items()},
            probation={str(mint): bool(flag) for mint, flag in probation.items()},
        )
