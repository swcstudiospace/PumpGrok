"""Strategy protocol, read-only context, Intent, and the strategy version id (STR-01).

A strategy hook receives exactly one frozen StrategyContext and returns a tuple
of Intent. The context holds immutable snapshots only: no store, no clock, no
ledger handle. Money is integer lamports; floats never carry money.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

from pumpgrok.upgrade.bounds import KeyBound

__all__ = [
    "Intent",
    "Side",
    "Strategy",
    "StrategyContext",
    "TapePoint",
    "TickSnapshot",
    "source_digest",
    "version_id",
]

Side = Literal["buy", "sell"]
_SIDES: frozenset[str] = frozenset({"buy", "sell"})


@dataclass(frozen=True)
class TickSnapshot:
    """Immutable view of one token at one tick, as the runtime observed it."""

    mint: str
    ts: float  # epoch seconds
    launch_ts: float  # epoch seconds of the token's launch
    price_lamports: int  # integer lamports; never a float
    unique_buyers: int
    curve_progress: float  # fraction of the bonding curve filled, 0.0 to 1.0


@dataclass(frozen=True)
class TapePoint:
    """One immutable price point on a strategy's own tape."""

    ts: float  # epoch seconds
    price_lamports: int  # integer lamports; never a float


@dataclass(frozen=True)
class StrategyContext:
    """The only input a strategy hook receives. Snapshots, no handles."""

    now: float  # epoch seconds, injected by the runtime from its clock
    version_id: str  # the strategy's version id, stamped onto every Intent
    tick: TickSnapshot
    tape: tuple[TapePoint, ...]


@dataclass(frozen=True)
class Intent:
    """A strategy's request to trade. It is not an order and carries no approval."""

    strategy_id: str
    mint: str
    side: Side
    size_lamports: int
    decision_id: str
    reason: str
    version_id: str

    def __post_init__(self) -> None:
        if isinstance(self.size_lamports, bool) or not isinstance(self.size_lamports, int):
            raise TypeError("Intent.size_lamports must be an int number of lamports")
        if self.size_lamports <= 0:
            raise ValueError("Intent.size_lamports must be positive")
        if self.side not in _SIDES:
            raise ValueError(f"Intent.side must be one of {sorted(_SIDES)}")


class Strategy(Protocol):
    """A strategy: an identity, its bounded parameters, and one hook.

    BOUNDS maps each parameter key to its inclusive bound; the keys must equal the
    [strategy.<strategy_id>.<key>] sections of upgrade_bounds.toml exactly.
    DEFAULTS are starting values PENDING OWNER APPROVAL, never final pins.
    """

    strategy_id: ClassVar[str]
    BOUNDS: ClassVar[Mapping[str, KeyBound]]
    DEFAULTS: ClassVar[Mapping[str, Any]]

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]: ...


def source_digest(strategy: type[Strategy]) -> str:
    """SHA-256 of the bytes of the module that defines the strategy."""
    module = sys.modules[strategy.__module__]
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        raise ValueError(f"strategy module {strategy.__module__} has no source file")
    return hashlib.sha256(Path(module_file).read_bytes()).hexdigest()


def version_id(strategy: type[Strategy], params: Mapping[str, Any]) -> str:
    """Identity of one strategy at one parameter set.

    Pass the effective parameters (DEFAULTS merged with any overrides). The digest
    covers the strategy id, those parameters, and the defining module's source, so it
    changes when code or parameters change and is stable otherwise.
    """
    payload = {
        "strategy_id": strategy.strategy_id,
        "params": dict(params),
        "source_sha256": source_digest(strategy),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
