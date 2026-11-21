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
import inspect
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pumpgrok.core.idempotency import canonical_json

__all__ = [
    "Intent",
    "LEGACY_STRATEGY_ID",
    "STRATEGY_IDS",
    "StrategyContext",
    "StrategyProtocol",
    "bounds_for",
    "code_digest",
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
    import importlib

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
    except Exception:  # noqa: BLE001 - best-effort digest only
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


def strategy_version_id(
    strategy_id: str, params: dict[str, Any], code: str | None = None
) -> str:
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
