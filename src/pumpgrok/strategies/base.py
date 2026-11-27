"""Frozen strategy surface (STR-01, D-02).

:class:`Strategy` is the frozen protocol every strategy implements: an id,
a version id derived from code plus parameters, declared :data:`BOUNDS`,
and read-only hooks. The version id is a digest over the id, the
canonical parameter overrides and the source of the hooks, so it moves
when code or parameters change and never acts as a score. BOUNDS in each
concrete strategy must equal the [strategy.<ID>.<PARAM>] sections of
upgrade_bounds.toml exactly (asserted in tests/strategies/test_base.py);
the TOML is the version-controlled source of truth, so a bound without a
TOML entry is a refusal, not a warning.

Hooks receive read-only contexts only: a frozen dataclass the runtime
hands over; mutation raises. No hook reaches an LLM client, the network,
or the risk engine. Money is integer lamports throughout.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, runtime_checkable

from pumpgrok.core.idempotency import canonical_json

if TYPE_CHECKING:
    from pumpgrok.upgrade.bounds import KeyBound

__all__ = [
    "LEGACY_STRATEGY_ID",
    "STRATEGY_IDS",
    "Intent",
    "Side",
    "Strategy",
    "StrategyContext",
    "StrategyProtocol",
    "TapePoint",
    "TickSnapshot",
    "bounds_for",
    "code_digest",
    "source_digest",
    "version_id",
]

#: The four D-01 ids. legacy_screening is the legacy arrival path; the
#: other three are the bounded baselines.
STRATEGY_IDS: tuple[str, str, str, str] = (
    "legacy_screening",
    "momentum_breakout",
    "new_launch_sniper",
    "mean_reversion",
)

LEGACY_STRATEGY_ID = "legacy_screening"

#: Declared BOUNDS per baseline id: param -> (inclusive min, inclusive max).
#: Must equal the [strategy.<ID>.<PARAM>] sections of upgrade_bounds.toml.
_BASELINE_BOUNDS: dict[str, dict[str, tuple[int, int]]] = {
    "momentum_breakout": {"breakout_bps": (0, 10000)},
    "new_launch_sniper": {"max_age_seconds": (0, 86400)},
    "mean_reversion": {"deviation_bps": (0, 10000)},
}


def bounds_for(strategy_id: str) -> dict[str, tuple[int, int]]:
    """Declared BOUNDS for one id; legacy_screening declares none."""
    if strategy_id == LEGACY_STRATEGY_ID:
        return {}
    if strategy_id not in _BASELINE_BOUNDS:
        raise ValueError(f"unknown strategy id: {strategy_id!r}")
    return dict(_BASELINE_BOUNDS[strategy_id])


def code_digest(strategy_id: str) -> str:
    """sha256 over the hook source of the named strategy module (best effort).

    A missing module or unreadable source yields the empty digest so the
    version id stays deterministic in every environment; the registry and
    runtime import the modules directly and fail closed there.
    """
    module_names = {
        "momentum_breakout": "pumpgrok.strategies.momentum_breakout",
        "new_launch_sniper": "pumpgrok.strategies.new_launch_sniper",
        "mean_reversion": "pumpgrok.strategies.mean_reversion",
    }
    name = module_names.get(strategy_id)
    if name is None:
        return ""
    try:
        module = importlib.import_module(name)
        source = inspect.getsource(module)
    except (ImportError, OSError, TypeError):
        return ""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Intent:
    """One strategy order wish: side, mint and size in integer lamports."""

    strategy_id: str
    side: str
    mint: str
    size_lamports: int
    reason: str = ""

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"side must be buy or sell, found {self.side!r}")
        if self.strategy_id not in STRATEGY_IDS:
            raise ValueError(f"unknown strategy id: {self.strategy_id!r}")
        if not self.mint:
            raise ValueError("an Intent names a mint")
        if isinstance(self.size_lamports, bool) or not isinstance(self.size_lamports, int):
            raise ValueError("size_lamports must be integer lamports")


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
    """Read-only context handed to hooks: tape snapshot plus parameters."""

    tape: tuple[Any, ...] = field(default_factory=tuple)
    params: dict[str, Any] = field(default_factory=dict)
    now: float = 0.0


@runtime_checkable
class StrategyProtocol(Protocol):
    """Frozen protocol: id, version id, BOUNDS, and read-only hooks."""

    @property
    def id(self) -> str: ...

    @property
    def BOUNDS(self) -> dict[str, tuple[int, int]]: ...

    def version_id(self, params: dict[str, Any]) -> str: ...

    def on_tick(self, tick: Any) -> None: ...

    def decide(self, context: StrategyContext) -> Intent | None: ...


def strategy_version_id(strategy_id: str, params: dict[str, Any], code: str | None = None) -> str:
    """Version id for one (id, params, code) triple (identity only).

    sha256 over the canonical id, params and code digest. The code
    component defaults to :func:`code_digest` for the id; callers may pass
    an explicit digest so a code change between two digests is observable
    without depending on module import.
    """
    payload = {
        "code": code_digest(strategy_id) if code is None else code,
        "id": strategy_id,
        "params": dict(params),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


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
