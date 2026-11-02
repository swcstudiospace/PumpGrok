"""Declared promotion search space: the owner's candidate list, validated fail closed (UPG-05).

config/upgrade_space.toml lists the parameter sets the scheduled promotion check searches.
The owner lists candidates in that version-controlled file; the code invents no parameter
values. The file ships empty, so the check is skipped until candidates are declared.

Shape: one array-of-tables entry named candidate per candidate, each with an optional filter
table and an optional exits table of integer, boolean or string knobs. The array keeps
declaration order, which decides ties in the search (the first best candidate wins).

load_declared_space parses the file and fails closed. It raises DeclaredSpaceError for a
malformed file, more than MAX_DECLARED_CANDIDATES candidates (never truncated), an unknown
key, or a float knob. It raises OutOfBoundsError for any value outside upgrade_bounds.toml.
Every candidate passes through ParamSet, which validates it with the real CandidateParams
model.

Imports stay in core/*, upgrade/bounds and upgrade/params. Never backtest.harness or cli.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.upgrade.bounds import Bounds, load_bounds, validate_against_bounds
from pumpgrok.upgrade.params import ParamSet

__all__ = [
    "DEFAULT_SPACE_PATH",
    "MAX_DECLARED_CANDIDATES",
    "DeclaredSpaceError",
    "load_declared_space",
]

#: Most candidates one scheduled check searches. Equals the gate's eligible-trial limit.
MAX_DECLARED_CANDIDATES = 20

#: The tables one candidate may declare; any other key fails the load.
_TABLE_KEYS = ("filter", "exits")

DEFAULT_SPACE_PATH = Path(__file__).resolve().parents[1] / "config" / "upgrade_space.toml"


class DeclaredSpaceError(PumpgrokError):
    """The declared search space is malformed, over the candidate limit, or unsupported."""

    code = "declared_space"


def _check_leaves(index: int, where: str, value: Any) -> None:
    """Refuse any leaf the search cannot hash: only int, bool and str are JSON-stable there."""
    if isinstance(value, dict):
        for key, item in value.items():
            _check_leaves(index, f"{where}.{key}", item)
    elif isinstance(value, list):
        for item in value:
            _check_leaves(index, where, item)
    elif not isinstance(value, (bool, int, str)):
        raise DeclaredSpaceError(
            f"candidate {index}: {where} holds {type(value).__name__}; "
            "the search takes integer, boolean and string knobs only"
        )


def _parse_candidate(index: int, entry: Any, bounds: Bounds) -> dict[str, Any]:
    """Return one candidate's mapping with only the tables it declares, validated fail closed."""
    if not isinstance(entry, dict):
        raise DeclaredSpaceError(f"candidate {index}: must be a table")
    unknown = sorted(set(entry) - set(_TABLE_KEYS))
    if unknown:
        raise DeclaredSpaceError(
            f"candidate {index}: unknown keys {unknown}; allowed keys are filter and exits"
        )
    mapping: dict[str, Any] = {}
    for key in _TABLE_KEYS:
        if key not in entry:
            continue
        table = entry[key]
        if not isinstance(table, dict):
            raise DeclaredSpaceError(f"candidate {index}: {key} must be a table")
        _check_leaves(index, key, table)
        mapping[key] = dict(table)
    try:
        params = ParamSet(**mapping)
    except (ValueError, TypeError) as err:
        raise DeclaredSpaceError(f"candidate {index}: not a valid parameter set: {err}") from err
    validate_against_bounds(params, bounds)
    return mapping


def load_declared_space(path: Path | str = DEFAULT_SPACE_PATH) -> tuple[dict[str, Any], ...]:
    """Read and validate the declared search space; fail closed on any defect.

    Returns the candidates in declaration order, each a mapping holding only the tables it
    declares. An empty file returns an empty tuple. Any defect raises; nothing is clamped,
    truncated or defaulted.
    """
    resolved = Path(path)
    try:
        with open(resolved, "rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as err:
        raise DeclaredSpaceError(f"upgrade space {resolved}: not valid TOML: {err}") from err
    unknown = sorted(set(raw) - {"candidate"})
    if unknown:
        raise DeclaredSpaceError(f"upgrade space {resolved}: unknown top-level keys {unknown}")
    entries = raw.get("candidate", [])
    if not isinstance(entries, list):
        raise DeclaredSpaceError(f"upgrade space {resolved}: candidate must be an array of tables")
    if len(entries) > MAX_DECLARED_CANDIDATES:
        raise DeclaredSpaceError(
            f"{len(entries)} candidates declared; at most {MAX_DECLARED_CANDIDATES} are allowed",
            declared=len(entries),
        )
    bounds = load_bounds()
    return tuple(_parse_candidate(index, entry, bounds) for index, entry in enumerate(entries))
