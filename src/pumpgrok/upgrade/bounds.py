"""Version-controlled bounds for upgrade parameter sets (UPG-01).

Bounds live in src/pumpgrok/config/upgrade_bounds.toml with filter and
exits range tables covering every tunable CandidateParams accepts. Values
outside bounds are rejected with OutOfBoundsError naming the key, the
value, and the allowed range; values are never clamped silently.
"""

from __future__ import annotations

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
    """Parsed upgrade bounds: per-key inclusive bounds for filter and exits."""

    filter: dict[str, KeyBound]
    exits: dict[str, KeyBound]


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
        if isinstance(bound.minimum, bool):
            if not isinstance(value, bool):
                raise OutOfBoundsError(
                    f"out of bounds: {section}.{key}={value!r} must be a bool, "
                    "allowed range [False, True]"
                )
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OutOfBoundsError(
                f"out of bounds: {section}.{key}={value!r} must be a number, "
                f"allowed range [{bound.minimum}, {bound.maximum}]"
            )
        if value < bound.minimum or value > bound.maximum:
            raise OutOfBoundsError(
                f"out of bounds: {section}.{key}={value!r} outside "
                f"[{bound.minimum}, {bound.maximum}]"
            )


def validate_against_bounds(params: ParamSet, bounds: Bounds) -> None:
    """Reject any override outside its bound with OutOfBoundsError, never clamp."""
    _check_section("filter", params.filter, bounds.filter)
    _check_section("exits", params.exits, bounds.exits)
