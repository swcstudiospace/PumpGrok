"""Trading platform registry for the onboarding flow.

Every platform below is evidenced in the codebase; no venue, endpoint, or
client is invented here. Selection gates backtest/paper modes only. Live
trading stays refused: the live stub is listed for completeness and
``can_select`` refuses it in every mode (live starts exit 3 in
``pumpgrok.execution.live.live_gate``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pumpgrok.onboarding.choices import read_choices, record_choice

# Modes a platform may be selected for. "live" never appears: no platform
# in this registry enables live execution.
_SELECTABLE_MODES = frozenset({"backtest", "paper"})


@dataclass(frozen=True)
class Platform:
    """One selectable platform and the inputs it needs."""

    platform_id: str
    description: str
    modes: frozenset[str]
    required_inputs: tuple[str, ...]

    def can_select(self, mode: str) -> bool:
        return mode in self.modes


REGISTRY: tuple[Platform, ...] = (
    Platform(
        platform_id="paper-execution",
        description="PaperAdapter, the only enabled execution adapter.",
        modes=_SELECTABLE_MODES,
        required_inputs=("seat_tool_access",),
    ),
    Platform(
        platform_id="solana-rpc",
        description="Solana mainnet JSON-RPC read-only ingress.",
        modes=_SELECTABLE_MODES,
        required_inputs=("rpc_endpoint",),
    ),
    Platform(
        platform_id="pumpfun",
        description="pump.fun REST plus PumpPortal websocket market data.",
        modes=_SELECTABLE_MODES,
        required_inputs=("rpc_endpoint",),
    ),
    Platform(
        platform_id="jupiter-quote",
        description="Jupiter Swap V2 quotes, informational only.",
        modes=_SELECTABLE_MODES,
        required_inputs=("rpc_endpoint",),
    ),
    Platform(
        platform_id="xai-grok",
        description="x.ai Grok completions, not a trading venue.",
        modes=_SELECTABLE_MODES,
        required_inputs=("xai_api_key",),
    ),
    Platform(
        platform_id="disabled-live-stub",
        description="Live stub. No live adapter ships in this release.",
        modes=frozenset(),
        required_inputs=(),
    ),
)

BY_ID: dict[str, Platform] = {platform.platform_id: platform for platform in REGISTRY}


def list_platforms() -> tuple[Platform, ...]:
    """Every platform available for selection in the onboarding flow."""
    return REGISTRY


def select_platform(platform_id: str, mode: str) -> Platform:
    """Resolve ``platform_id`` for ``mode`` or raise ``KeyError``.

    Unknown ids and any live selection raise; the error names the field,
    never a secret.
    """
    platform = BY_ID.get(platform_id)
    if platform is None or not platform.can_select(mode):
        raise KeyError(f"platform refused for mode {mode}: {platform_id}")
    return platform


def record_platform_choice(path: Path, platform_id: str, mode: str) -> dict[str, str]:
    """Record an operator platform choice after validating it."""
    select_platform(platform_id, mode)
    return record_choice(path, "platform", platform_id)


def recorded_platform(path: Path) -> str | None:
    """Latest recorded platform id, or ``None`` when nothing was recorded."""
    selected: str | None = None
    for row in read_choices(path):
        if row.get("name") == "platform":
            selected = row.get("value")
    return selected
