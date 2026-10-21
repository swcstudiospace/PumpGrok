"""desk.ownership_resolve: repo paths to owning seats (TOOL-007).

Reads ``ownership.yaml`` at call time; LAST matching pattern wins and an
unmatched path is reported unowned. Patterns are matched with
``fnmatch.fnmatchcase`` (``*`` crosses directories, as in the gate).
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import meta_now

__all__ = [
    "OWNERSHIP_RESOLVE_SPEC",
    "OwnershipResolveIn",
    "OwnershipResolveOut",
    "build_ownership_resolve_tool",
    "run_ownership_resolve",
]


class OwnershipResolveIn(ToolInput):
    """Up to 100 repo-relative paths to resolve."""

    paths: list[str] = Field(min_length=1, max_length=100)


class OwnershipResolveOut(ToolOutput):
    """Per-path owner (last match wins) plus the unowned remainder."""

    resolved: list[dict] = Field(default_factory=list)
    unowned: list[str] = Field(default_factory=list)


OWNERSHIP_RESOLVE_SPEC = ToolSpec(
    name="desk.ownership_resolve",
    description=(
        "Resolve repo paths to owning seats under ownership.yaml; last "
        "match wins, unowned paths are reported."
    ),
    input_model=OwnershipResolveIn,
    output_model=OwnershipResolveOut,
    side_effect=SideEffect.READ,
    timeout_s=5.0,
    rate_limit_key="desk",
    backend="pumpgrok.tools.desk.ownership_resolve",
)


def _load_rules(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    rules = manifest.get("ownership", [])
    return [r for r in rules if isinstance(r, dict) and "pattern" in r and "owner" in r]


async def run_ownership_resolve(inp: OwnershipResolveIn, manifest_path: Path) -> dict:
    """Resolve each path; last matching rule wins."""
    rules = _load_rules(manifest_path)
    resolved: list[dict] = []
    unowned: list[str] = []
    for path in inp.paths:
        match: dict[str, Any] | None = None
        for rule in rules:
            if fnmatch.fnmatchcase(path, str(rule["pattern"])):
                match = rule
        if match is None:
            unowned.append(path)
        else:
            resolved.append(
                {
                    "path": path,
                    "owner": str(match["owner"]),
                    "contract_surface": bool(match.get("contract_surface", False)),
                }
            )
    ambient = ambient_correlation()
    return OwnershipResolveOut.model_validate(
        {
            "resolved": resolved,
            "unowned": unowned,
            "meta": meta_now(
                "desk", inp.correlation_id or (str(ambient) if ambient else None)
            ),
        }
    ).model_dump()


def build_ownership_resolve_tool(manifest_path: Path) -> Tool:
    """Bind ``desk.ownership_resolve`` to one manifest path (no globals)."""

    @tool(OWNERSHIP_RESOLVE_SPEC)
    async def _ownership_resolve(payload: OwnershipResolveIn) -> dict:
        return await run_ownership_resolve(payload, manifest_path)

    return _ownership_resolve
