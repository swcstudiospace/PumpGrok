"""Read-only curve observations consumed by the event bridge."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from pumpgrok.replay.clock import parse_ts_utc


@dataclass(frozen=True)
class CurveObservation:
    mint: str
    ts_utc: str
    s_lamports: int
    t_units: int
    complete: bool
    source: str

    def validate(self) -> float:
        """Validate without coercion and return the UTC observation time."""
        if not isinstance(self.mint, str) or not self.mint.strip():
            raise ValueError("mint must be a nonempty string")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a nonempty string")
        if not isinstance(self.ts_utc, str):
            raise ValueError("timestamp must be a UTC string")
        try:
            stamp = datetime.fromisoformat(self.ts_utc)
            if stamp.utcoffset() != timedelta(0):
                raise ValueError("timestamp must use UTC")
            epoch = parse_ts_utc(self.ts_utc)
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError("timestamp must be a valid UTC timestamp") from exc
        if type(self.s_lamports) is not int or self.s_lamports <= 0:
            raise ValueError("SOL reserves must be a positive integer")
        if type(self.t_units) is not int or self.t_units <= 0:
            raise ValueError("token reserves must be a positive integer")
        if type(self.complete) is not bool:
            raise ValueError("complete must be a boolean")
        return epoch

    def replay_tick(self) -> dict[str, str | int | bool]:
        """Map base-unit observation fields to the existing replay tick format."""
        return {
            "kind": "tick",
            "mint": self.mint,
            "ts_utc": self.ts_utc,
            "S": self.s_lamports,
            "T": self.t_units,
            "complete": self.complete,
            "source": self.source,
        }
