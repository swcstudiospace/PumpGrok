"""Content-hashed upgrade parameter sets (UPG-01).

A ParamSet holds optional filter and exits override mappings validated
through CandidateParams, so unknown fields and inert scoring knobs are
refused exactly the way evaluate.py refuses them. content_hash is sha256
over the canonical_json of the normalized overrides.

The hash is identity only: it names the exact set and never acts as a
score, a metric, or a verdict. No promotion, ranking, or comparison may
read it as quality.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator

from pumpgrok.backtest.evaluate import CandidateParams
from pumpgrok.core.idempotency import canonical_json

__all__ = ["ParamSet"]


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


def _normalized_mapping(mapping: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize one override mapping: None and {} both mean no overrides."""
    if not mapping:
        return {}
    return {key: _normalized_leaf(value) for key, value in mapping.items()}


class ParamSet(BaseModel):
    """One upgrade parameter set: filter and exits overrides plus identity hash.

    Both mappings are optional; absent means desk defaults. Construction
    validates through CandidateParams, so unknown keys and inert scoring
    knobs fail closed with a ValidationError at construction time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    filter: dict[str, Any] | None = None
    exits: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _refuse_unknown_and_inert(self) -> Self:
        """Validate overrides through CandidateParams at construction."""
        CandidateParams(filter=self.filter, exits=self.exits)
        return self

    def candidate(self) -> CandidateParams:
        """Return these overrides as the validated CandidateParams."""
        return CandidateParams(filter=self.filter, exits=self.exits)

    @property
    def content_hash(self) -> str:
        """sha256 over the canonical_json of the normalized overrides.

        Identity only: the digest names the exact set and never acts as
        a score, a metric, or a verdict.
        """
        payload: dict[str, Any] = {
            "exits": _normalized_mapping(self.exits),
            "filter": _normalized_mapping(self.filter),
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
