"""Skill contracts: manifests and the skill protocol (interfaces.md 2.8)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pumpgrok.core.side_effect import SideEffect

if TYPE_CHECKING:
    from pumpgrok.core.bot import BotManifest
    from pumpgrok.core.registry import ToolRegistry


class SkillPermissions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_side_effect: SideEffect = SideEffect.READ
    network: bool = True
    filesystem: Literal["none", "var", "repo"] = "none"

    @field_validator("max_side_effect")
    @classmethod
    def _never_live(cls, v: SideEffect) -> SideEffect:
        if v is SideEffect.LIVE_WRITE:
            raise ValueError("a skill may never declare live-write")
        return v


class SkillManifest(BaseModel):
    """Frontmatter of skills/<name>/SKILL.md parsed into a model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,60}$")
    description: str = Field(min_length=1, max_length=1024)
    bots: list[str] = Field(min_length=1)  # seat ids or ['all']
    gates: list[str] = Field(default_factory=list)  # ['G-2', ...]
    required_tools: list[str] = Field(default_factory=list)  # catalog names
    required_data: list[str] = Field(default_factory=list)  # DataSource names
    permissions: SkillPermissions = Field(default_factory=SkillPermissions)
    fixtures: list[str] = Field(default_factory=list)  # tests/fixtures/** used by skill tests

    @field_validator("bots")
    @classmethod
    def _bot_ids(cls, v: list[str]) -> list[str]:
        for b in v:
            if b != "all" and not b.startswith("bot-0"):
                raise ValueError(f"bad bot id {b!r}")
        return v


@runtime_checkable
class Skill(Protocol):
    """Tools plus decision logic. Unit-testable with recorded fixtures and no network."""

    manifest: type[SkillManifest]

    async def run(
        self, registry: ToolRegistry, bot: BotManifest, context: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...
