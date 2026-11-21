"""Version-controlled bounds for upgrade parameter sets (UPG-01).

Bounds live in src/pumpgrok/config/upgrade_bounds.toml with filter and
exits range tables covering every tunable CandidateParams accepts. Values
outside bounds are rejected with OutOfBoundsError naming the key, the
value, and the allowed range; values are never clamped silently.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.upgrade.params import ParamSet

__all__ = [
    "Bounds",
    "KeyBound",
    "OutOfBoundsError",
    "default_bounds_path",
    "load_bounds",
    "validate_against_bounds",
]


class OutOfBoundsError(PumpgrokError):
    """An override value falls outside its version-controlled bound."""

    code = "out_of_bounds"


@dataclass(frozen=True)
class KeyBound:
    """Inclusive bound for one override key.

    Bool bounds admit both values and enforce the bool type itself;
    numeric bounds admit the inclusive [minimum, maximum] range.
    """

    minimum: bool | int | float
    maximum: bool | int | float


@dataclass(frozen=True)
class Bounds:
    """Parsed upgrade bounds: per-key inclusive bounds for filter and exits.

    strategy holds per-strategy per-param inclusive bounds parsed from the
    [strategy.<ID>.<PARAM>] sections; empty means no strategy overrides are
    admitted (any strategy override then fails with no bound).
    """

    filter: dict[str, KeyBound]
    exits: dict[str, KeyBound]
    strategy: dict[str, dict[str, KeyBound]] = field(default_factory=dict)

def default_bounds_path() -> Path:
    """In-package upgrade_bounds.toml path."""
    return Path(__file__).resolve().parents[1] / "config" / "upgrade_bounds.toml"


def _parse_key_bound(section: str, key: str, raw: Any) -> KeyBound:
    """Parse one bound entry table with inclusive min and max."""
    if not isinstance(raw, dict):
        raise ValueError(f"bounds {section}.{key}: entry must be a table with min and max")
    if "min" not in raw or "max" not in raw:
        raise ValueError(f"bounds {section}.{key}: entry must name min and max")
    minimum: Any = raw["min"]
    maximum: Any = raw["max"]
    if isinstance(minimum, bool) or isinstance(maximum, bool):
        if not isinstance(minimum, bool) or not isinstance(maximum, bool):
            raise ValueError(f"bounds {section}.{key}: min and max must match in type")
        return KeyBound(minimum=minimum, maximum=maximum)
    if not isinstance(minimum, (int, float)) or not isinstance(maximum, (int, float)):
        raise ValueError(f"bounds {section}.{key}: min and max must be numbers")
    if minimum > maximum:
        raise ValueError(f"bounds {section}.{key}: min {minimum!r} is above max {maximum!r}")
    return KeyBound(minimum=minimum, maximum=maximum)


def _parse_section(raw: Any, section: str) -> dict[str, KeyBound]:
    """Parse one range table of per-key bound entries."""
    if not isinstance(raw, dict):
        raise ValueError(f"bounds: missing {section!r} range table")
    return {key: _parse_key_bound(section, key, entry) for key, entry in raw.items()}


def _parse_strategy(raw: Any) -> dict[str, dict[str, KeyBound]]:
    """Parse the [strategy.<ID>.<PARAM>] tables; absent means none."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("bounds: 'strategy' must be a table of [strategy.<ID>.<PARAM>]")
    parsed: dict[str, dict[str, KeyBound]] = {}
    for strategy_id, entry in raw.items():
        if not isinstance(strategy_id, str) or not strategy_id:
            raise ValueError("bounds: strategy ids must be non-empty str")
        if not isinstance(entry, dict):
            raise ValueError(f"bounds strategy.{strategy_id}: entry must be a table")
        parsed[strategy_id] = {
            key: _parse_key_bound(f"strategy.{strategy_id}", key, param)
            for key, param in entry.items()
        }
    return parsed


def load_bounds(path: Path | str | None = None) -> Bounds:
    """Read and validate the bounds TOML file, fail closed on any defect."""
    resolved = Path(path) if path is not None else default_bounds_path()
    with open(resolved, "rb") as handle:
        raw = tomllib.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"bounds {resolved}: top level must be a table")
    return Bounds(
        filter=_parse_section(raw.get("filter"), "filter"),
        exits=_parse_section(raw.get("exits"), "exits"),
        strategy=_parse_strategy(raw.get("strategy")),
    )


def _check_value(label: str, key: str, value: Any, bound: KeyBound) -> None:
    """Reject one value that its bound does not admit (bool or number)."""
    if isinstance(bound.minimum, bool):
        if not isinstance(value, bool):
            raise OutOfBoundsError(
                f"out of bounds: {label}.{key}={value!r} must be a bool, "
                "allowed range [False, True]"
            )
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutOfBoundsError(
            f"out of bounds: {label}.{key}={value!r} must be a number, "
            f"allowed range [{bound.minimum}, {bound.maximum}]"
        )
    if value < bound.minimum or value > bound.maximum:
        raise OutOfBoundsError(
            f"out of bounds: {label}.{key}={value!r} outside "
            f"[{bound.minimum}, {bound.maximum}]"
        )


def _check_section(
    section: str,
    mapping: dict[str, Any] | None,
    section_bounds: dict[str, KeyBound],
) -> None:
    """Reject any override in one section that its bound does not admit."""
    for key, value in (mapping or {}).items():
        bound = section_bounds.get(key)
        if bound is None:
            raise OutOfBoundsError(
                f"no bound for {section}.{key}: {value!r} cannot be accepted "
                "without a version-controlled bound"
            )
        _check_value(section, key, value, bound)


def validate_against_bounds(params: ParamSet, bounds: Bounds) -> None:
    """Reject any override outside its bound with OutOfBoundsError, never clamp.

    Strategy overrides check each [strategy.<ID>.<PARAM>] bound, so an
    unknown strategy id or param fails with no bound instead of slipping
    through. Absent strategy overrides (None or {}) check nothing.
    """
    _check_section("filter", params.filter, bounds.filter)
    _check_section("exits", params.exits, bounds.exits)
    for strategy_id, mapping in (params.strategy or {}).items():
        section_bounds = bounds.strategy.get(strategy_id)
        if section_bounds is None:
            raise OutOfBoundsError(
                f"no bound for strategy.{strategy_id}: {dict(mapping)!r} cannot be "
                "accepted without a version-controlled bound"
            )
        _check_section(f"strategy.{strategy_id}", mapping, section_bounds)
