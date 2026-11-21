"""Onboarding settings section (ONB, Phase 14). Off by default.

Kept importable without being composed into `Settings`: the settings
surface digest is pinned by tests, so this section is consumed directly by
the onboarding package until a future phase composes it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OnboardingSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    access_decisions_path: str = "var/desk/access-decisions.jsonl"
    choice_records_path: str = "var/desk/choice-records.jsonl"
    seats: tuple[str, ...] = Field(default_factory=tuple)
