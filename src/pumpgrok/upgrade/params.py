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

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator

from pumpgrok.backtest.candidate import CandidateParams

__all__ = ["ParamSet"]


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
        return self.candidate().content_hash
