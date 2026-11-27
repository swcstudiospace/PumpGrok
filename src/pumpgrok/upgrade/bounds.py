"""Version-controlled bounds for upgrade parameter sets (UPG-01).

Bounds live in src/pumpgrok/config/upgrade_bounds.toml with filter and
exits range tables covering every tunable CandidateParams accepts, and
[strategy.ID.PARAM] tables for each strategy. Values
outside bounds are rejected with OutOfBoundsError naming the key, the
value, and the allowed range; values are never clamped silently.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
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
    """Parsed upgrade bounds: per-key inclusive bounds for filter, exits and strategy."""

    filter: dict[str, KeyBound]
    exits: dict[str, KeyBound]
    strategy: dict[str, dict[str, KeyBound]]


def default_bounds_path() -> Path:
    """In-package upgrade_bounds.toml path."""
    return Path(__file__).resolve().parents[1] / "config" / "upgrade_bounds.toml"


def _is_finite(number: float | int) -> bool:
    """False for NaN and the infinities; every int is finite."""
    return not isinstance(number, float) or math.isfinite(number)


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
    if not _is_finite(minimum) or not _is_finite(maximum):
        raise ValueError(f"bounds {section}.{key}: min and max must be finite numbers")
    if minimum > maximum:
        raise ValueError(f"bounds {section}.{key}: min {minimum!r} is above max {maximum!r}")
    return KeyBound(minimum=minimum, maximum=maximum)


def _parse_section(raw: Any, section: str) -> dict[str, KeyBound]:
    """Parse one range table of per-key bound entries."""
    if not isinstance(raw, dict):
        raise ValueError(f"bounds: missing {section!r} range table")
    return {key: _parse_key_bound(section, key, entry) for key, entry in raw.items()}


def _parse_strategy_section(raw: Any) -> dict[str, dict[str, KeyBound]]:
    """Parse the [strategy.ID.PARAM] tables; an absent strategy table is empty."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("bounds: strategy must be a table of strategy id tables")
    return {
        strategy_id: _parse_section(section, f"strategy.{strategy_id}")
        for strategy_id, section in raw.items()
    }


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
        strategy=_parse_strategy_section(raw.get("strategy")),
    )


def _check_section(
    section: str,
    mapping: dict[str, Any] | None,
    section_bounds: dict[str, KeyBound],
    *,
    echo_value: bool = True,
) -> None:
    """Reject any override in one section that its bound does not admit.

    echo_value False withholds the offending value from the message; the strategy
    sections use it so a rejected override names its key and allowed range only.
    """
    for key, value in (mapping or {}).items():
        shown = repr(value) if echo_value else "<withheld>"
        bound = section_bounds.get(key)
        if bound is None:
            raise OutOfBoundsError(
                f"no bound for {section}.{key}: {shown} cannot be accepted "
                "without a version-controlled bound"
            )
        if isinstance(bound.minimum, bool):
            if not isinstance(value, bool):
                raise OutOfBoundsError(
                    f"out of bounds: {section}.{key}={shown} must be a bool, "
                    "allowed range [False, True]"
                )
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OutOfBoundsError(
                f"out of bounds: {section}.{key}={shown} must be a number, "
                f"allowed range [{bound.minimum}, {bound.maximum}]"
            )
        if not _is_finite(value):
            raise OutOfBoundsError(
                f"out of bounds: {section}.{key}={shown} must be finite, "
                f"allowed range [{bound.minimum}, {bound.maximum}]"
            )
        if value < bound.minimum or value > bound.maximum:
            raise OutOfBoundsError(
                f"out of bounds: {section}.{key}={shown} outside [{bound.minimum}, {bound.maximum}]"
            )


def _check_strategy(
    mapping: dict[str, dict[str, Any]] | None,
    strategy_bounds: dict[str, dict[str, KeyBound]],
) -> None:
    """Refuse a strategy with no bound; each admitted parameter must sit in range."""
    for strategy_id, overrides in (mapping or {}).items():
        if not overrides:
            continue
        section_bounds = strategy_bounds.get(strategy_id)
        if section_bounds is None:
            raise OutOfBoundsError(
                f"no bound for strategy.{strategy_id}: its parameters cannot be accepted "
                "without a version-controlled bound"
            )
        _check_section(f"strategy.{strategy_id}", overrides, section_bounds, echo_value=False)


def validate_against_bounds(params: ParamSet, bounds: Bounds) -> None:
    """Reject any override outside its bound with OutOfBoundsError, never clamp.

    Strategy overrides check each [strategy.<ID>.<PARAM>] bound, so an
    unknown strategy id or param fails with no bound instead of slipping
    through. Absent strategy overrides (None or {}) check nothing.
    """
    _check_section("filter", params.filter, bounds.filter)
    _check_section("exits", params.exits, bounds.exits)
    _check_strategy(params.strategy, bounds.strategy)
