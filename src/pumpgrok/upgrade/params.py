"""Content-hashed upgrade parameter sets (UPG-01).

A ParamSet holds optional filter, exits and strategy override mappings validated
through CandidateParams, so unknown fields and inert scoring knobs are
refused exactly the way evaluate.py refuses them. content_hash is sha256
over the canonical_json of the normalized overrides.

The hash is identity only: it names the exact set and never acts as a
score, a metric, or a verdict. No promotion, ranking, or comparison may
read it as quality.
"""

from __future__ import annotations

import copy
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from pumpgrok.backtest.candidate import CandidateParams

__all__ = ["ParamSet"]


class ParamSet(BaseModel):
    """One upgrade parameter set: filter, exits and strategy overrides plus identity hash.

    Every mapping is optional; absent means desk defaults. The strategy section maps
    a strategy id to its [strategy.ID.PARAM] overrides. Construction validates through
    CandidateParams, so unknown keys and inert scoring knobs fail closed with a
    ValidationError at construction time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    filter: dict[str, Any] | None = None
    exits: dict[str, Any] | None = None
    strategy: dict[str, dict[str, Any]] | None = None

    _content_hash: str | None = PrivateAttr(default=None)

    @model_validator(mode="before")
    @classmethod
    def _deep_copy_mappings(cls, data: Any) -> Any:
        """Copy the mappings so later caller mutation cannot reach inside (EVT-SW-41)."""
        if not isinstance(data, dict):
            return data
        copied = dict(data)
        for key in ("filter", "exits", "strategy"):
            if key in copied and copied[key] is not None:
                copied[key] = copy.deepcopy(copied[key])
        return copied

    @model_validator(mode="after")
    def _refuse_unknown_and_inert(self) -> Self:
        """Validate overrides through CandidateParams at construction."""
        candidate = CandidateParams(filter=self.filter, exits=self.exits, strategy=self.strategy)
        object.__setattr__(self, "_content_hash", candidate.content_hash)
        return self

    @model_serializer(mode="wrap")
    def _omit_empty_strategy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Omit the strategy key when absent or empty, so legacy serialization is unchanged."""
        data: dict[str, Any] = handler(self)
        if not data.get("strategy"):
            data.pop("strategy", None)
        return data

    def candidate(self) -> CandidateParams:
        """Return these overrides as the validated CandidateParams."""
        return CandidateParams(filter=self.filter, exits=self.exits, strategy=self.strategy)

    @property
    def content_hash(self) -> str:
        """sha256 over the canonical_json of the normalized overrides (cached at construction).

        Identity only: the digest names the exact set and never acts as
        a score, a metric, or a verdict.
        """
        if self._content_hash is None:
            object.__setattr__(self, "_content_hash", self.candidate().content_hash)
        assert self._content_hash is not None
        return self._content_hash
