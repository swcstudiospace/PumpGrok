"""ONB-04 production wiring: the production-built registry gates every roster tool.

``build_production_operator_registry`` passes ``OperatorGrants().allows``: a roster tool
resolves only after an authenticated operator ``allow`` for that seat and tool, and a
revoke takes effect at the next check. ``build_operator_registry`` stays opt-in (no gate),
which the replay and test harness depend on.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from pumpgrok.config.settings import load_settings
from pumpgrok.core.bot import BotManifest
from pumpgrok.core.errors import PermissionDenied
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.manifests import load_bot_manifests, roster_tool_names
from pumpgrok.core.registry import ToolRegistry
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import WallClock
from pumpgrok.tools import build_operator_registry, build_production_operator_registry

ROOT = Path(__file__).resolve().parents[2]
REPO_ROSTERS = ROOT / "contracts" / "tool-rosters"
SEAT = "bot-01-scout"
OTHER_SEAT = "bot-02-risk"
TOOL = "market.price"
LEDGER = Path("var") / "ledger.sqlite"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

Built = tuple[ToolRegistry, dict[str, BotManifest], httpx.AsyncClient]


@pytest.fixture
def operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory whose operator key is owned by the running account."""
    monkeypatch.chdir(tmp_path)
    oc.init_key(Path("var") / "operator")
    return tmp_path


@pytest.fixture
def bound_correlation() -> Iterator[None]:
    """ToolRegistry.find refuses to run without an ambient correlation id."""
    factory = IdFactory(WallClock(), random.Random(3))
    with bind_correlation(CorrelationId.new(factory)):
        yield


def _build(*, production: bool) -> Built:
    """Build a registry over the working-directory ledger, as the CLI does."""
    builder = build_production_operator_registry if production else build_operator_registry
    return builder(
        data_dir=Path("desk"),
        repo_root=ROOT,
        settings=load_settings(),
        ledger_path=LEDGER,
        p_drop=0.0,
    )


def _record(seat: str, tool: str, decision: str) -> None:
    store = LedgerStore(LEDGER)
    try:
        oc.record_tool_choice(
            store,
            seat=seat,
            tool=tool,
            decision=decision,
            contracts_dir=REPO_ROSTERS,
            now=NOW,
        )
    finally:
        store.close()


def _refusal_reason(registry: ToolRegistry, seat: str, tool: str) -> str:
    manifest = load_bot_manifests(REPO_ROSTERS)[seat]
    with pytest.raises(PermissionDenied) as info:
        registry.find(tool, max_side_effect=SideEffect.READ, bot=manifest)
    return str(info.value.fields["reason"])


async def test_production_registry_refuses_an_ungranted_roster_tool(
    operator_home: Path, bound_correlation: None
) -> None:
    registry, _manifests, client = _build(production=True)
    try:
        assert TOOL in roster_tool_names(REPO_ROSTERS, SEAT)
        assert TOOL in registry.names()
        assert _refusal_reason(registry, SEAT, TOOL) == "not_operator_approved"
    finally:
        await client.aclose()


async def test_production_registry_resolves_only_after_an_authenticated_allow(
    operator_home: Path, bound_correlation: None
) -> None:
    registry, manifests, client = _build(production=True)
    try:
        assert _refusal_reason(registry, SEAT, TOOL) == "not_operator_approved"

        _record(SEAT, TOOL, "allow")
        # The same registry instance resolves the tool: grants are read at each check.
        resolved = registry.find(TOOL, max_side_effect=SideEffect.READ, bot=manifests[SEAT])
        assert resolved is not None

        _record(SEAT, TOOL, "revoke")
        assert _refusal_reason(registry, SEAT, TOOL) == "not_operator_approved"
    finally:
        await client.aclose()


async def test_production_grant_is_scoped_to_one_seat_and_one_tool(
    operator_home: Path, bound_correlation: None
) -> None:
    registry, manifests, client = _build(production=True)
    try:
        shared = sorted(
            roster_tool_names(REPO_ROSTERS, SEAT)
            & roster_tool_names(REPO_ROSTERS, OTHER_SEAT)
            & frozenset(registry.names())
        )
        assert len(shared) >= 2, shared
        granted, other = shared[0], shared[1]
        _record(SEAT, granted, "allow")

        resolved = registry.find(granted, max_side_effect=SideEffect.READ, bot=manifests[SEAT])
        assert resolved is not None
        assert _refusal_reason(registry, OTHER_SEAT, granted) == "not_operator_approved"
        assert _refusal_reason(registry, SEAT, other) == "not_operator_approved"
    finally:
        await client.aclose()


async def test_opt_in_builder_stays_ungated_without_a_grant(
    operator_home: Path, bound_correlation: None
) -> None:
    registry, manifests, client = _build(production=False)
    try:
        tool = registry.find(TOOL, max_side_effect=SideEffect.READ, bot=manifests[SEAT])
        assert tool is not None
    finally:
        await client.aclose()
