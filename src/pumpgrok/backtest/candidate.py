"""Candidate parameter overrides: the leaf home of CandidateParams (UPG-01, BT-07).

CandidateParams validates filter and exits override mappings, builds the
effective FilterSettings and ExitsSettings, and hashes the normalized
overrides. It lives in this module, not in the evaluator, so the upgrade
parameter sets and the ledger active-set reader can import it without
reaching the scheduler: the evaluator imports the scheduler, and the
scheduler's replay runtime reads the active set. The imports here are
pydantic, the stdlib, the settings models, and canonical_json; none of
them reaches the evaluator, the scheduler, or the ledger active-set module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from pumpgrok.config.settings import ExitsSettings, FilterSettings
from pumpgrok.core.idempotency import canonical_json

__all__ = [
    "CandidateParams",
    "ScoringKnobError",
    "param_set_mapping",
]

#: Tunable names the replay never consults, so accepting them would be a
#: hollow knob. ScoringWeights fields (audit, narrative, timing, metrics),
#: the ScoringSettings container names (weights, timing_cache_seconds), and
#: min_total_score, which lives on FilterSettings but decide_token never
#: reads: it consults only passes_filter, so the knob is inert in replay.
_SCORING_KNOBS = frozenset(
    {
        "audit",
        "narrative",
        "timing",
        "metrics",
        "weights",
        "timing_cache_seconds",
        "min_total_score",
    }
)


class ScoringKnobError(ValueError):
    """A candidate tunable names a scoring knob the replay never consults."""


def _reject_scoring_knobs(section: str, mapping: Mapping[str, Any]) -> None:
    """Refuse scoring knobs inside one override mapping, fail closed."""
    for key in mapping:
        if key in _SCORING_KNOBS:
            raise ScoringKnobError(
                f"scoring knob {key!r} in {section!r} is not tunable: "
                "the replay consults only passes_filter, so the knob is inert"
            )


def _normalized_leaf(value: Any) -> Any:
    """Map one override leaf onto a canonical_json scalar.

    Floats normalize through Decimal so the hash input stays deterministic
    while canonical_json keeps rejecting raw float leaves.
    """
    if isinstance(value, (bool, int, str, Decimal)):
        return value
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, list):
        return [_normalized_leaf(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("override mapping keys must be str")
        return {key: _normalized_leaf(item) for key, item in value.items()}
    raise TypeError(f"override leaf of type {type(value).__name__} is not supported")


def _normalized_mapping(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize one override mapping: None and {} both mean no overrides."""
    if not mapping:
        return {}
    return {key: _normalized_leaf(value) for key, value in mapping.items()}


class CandidateParams(BaseModel):
    """One candidate parameter set: filter and exits overrides only.

    Both mappings are optional; absent means desk defaults. Each provided
    mapping is validated by constructing the real FilterSettings or
    ExitsSettings model, so unknown fields fail. Any other top-level key,
    including scoring weights, fails through extra forbidden. Scoring knobs
    wherever they appear, including min_total_score inside filter, fail
    through the explicit blocklist with a typed validation error. Pydantic
    surfaces validator ValueError subclasses as ValidationError.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    filter: dict[str, Any] | None = None
    exits: dict[str, Any] | None = None

    @field_validator("filter")
    @classmethod
    def _check_filter(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Blocklist scoring knobs, then validate against FilterSettings."""
        if value is None:
            return None
        _reject_scoring_knobs("filter", value)
        FilterSettings(**value)
        return value

    @field_validator("exits")
    @classmethod
    def _check_exits(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Blocklist scoring knobs, then validate against ExitsSettings."""
        if value is None:
            return None
        _reject_scoring_knobs("exits", value)
        ExitsSettings(**value)
        return value

    def filter_settings(self) -> FilterSettings:
        """Desk defaults with the candidate filter overrides applied."""
        if self.filter is None:
            return FilterSettings()
        return FilterSettings(**dict(self.filter))

    def exits_settings(self) -> ExitsSettings:
        """Desk defaults with the candidate exits overrides applied."""
        if self.exits is None:
            return ExitsSettings()
        return ExitsSettings(**dict(self.exits))

    @property
    def content_hash(self) -> str:
        """sha256 over the canonical_json of the normalized overrides.

        Identity only: the digest names the exact set and never acts as
        a score, a metric, or a verdict. ParamSet.content_hash, the harness
        trial hashes, and the winner hash all read this one definition.
        """
        payload: dict[str, Any] = {
            "exits": _normalized_mapping(self.exits),
            "filter": _normalized_mapping(self.filter),
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def param_set_mapping(data: bytes) -> dict[str, Any]:
    """Parse parameter-set file bytes into the JSON mapping CandidateParams validates.

    The bytes must hold one JSON object whose leaves are JSON-stable: ints,
    strings, bools, lists and mappings, with float leaves refused. Any other
    input raises ValueError, which the backtest CLI maps to a usage error.
    """
    try:
        parsed: Any = json.loads(data.decode("utf-8"))
    except ValueError as exc:
        raise ValueError("parameter-set bytes must hold a JSON mapping") from exc
    if not isinstance(parsed, dict):
        raise ValueError("parameter-set bytes must hold a JSON mapping")
    try:
        canonical_json(parsed)
    except TypeError as exc:
        raise ValueError("parameter-set JSON must hold ints, strings and bools") from exc
    return parsed
