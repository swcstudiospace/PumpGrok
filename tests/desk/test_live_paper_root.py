<<<<<<< HEAD
"""SC 10: the live-data paper root refuses unless paper, with no fund-moving symbols."""
=======
"""MKT-09 / criterion 10: the live-data paper root refuses non-paper and endpoint-less builds.

Offline only. The transport is the read-only double from ``tests/datafeed``; no test
here reaches a network endpoint. The root has no default endpoint: every build names
one explicitly.
"""
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687

from __future__ import annotations

import ast
<<<<<<< HEAD
from pathlib import Path
from types import ModuleType

import pytest

from pumpgrok.core.adapter import ExecutionMode
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.live_paper import (
    LivePaperError,
    build_live_paper,
    strategy_factory,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "pumpgrok"

COMPOSED = (
    "supervisor/live_paper.py",
    "supervisor/intent_router.py",
    "supervisor/exit_rules.py",
    "datafeed/readonly.py",
    "datafeed/price.py",
    "datafeed/marks.py",
)

FORBIDDEN = frozenset({"sign", "send_transaction", "sendTransaction", "signTransaction", "Keypair"})


def _open_store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


async def _never_place(request) -> None:  # pragma: no cover - build only
    raise AssertionError("build must not place")


def test_refuses_unless_paper(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        for mode in (ExecutionMode.LIVE, "live", "paper-event", "manual"):
            with pytest.raises(LivePaperError, match="paper mode"):
                build_live_paper(
                    mode=mode,
                    store=store,
                    clock=FixtureClock(0.0),
                    place=_never_place,
                )
    finally:
        store.close()


def test_builds_under_paper(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        desk = build_live_paper(
            mode=ExecutionMode.PAPER,
            store=store,
            clock=FixtureClock(0.0),
            place=_never_place,
            params={"momentum_breakout": {"breakout_bps": 100}},
        )
        assert desk.mode == "paper"
        assert desk.prices is not None
        assert desk.runtime is not None
        assert desk.router is not None
        assert set(desk.allowed_methods) == {
            "getAccountInfo",
            "logsSubscribe",
            "getTransaction",
            "subscribeNewToken",
            "subscribeMigration",
        }
    finally:
        store.close()


def test_builds_under_paper_string_mode(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        desk = build_live_paper(
            mode="paper",
            store=store,
            clock=FixtureClock(0.0),
            place=_never_place,
            params={"momentum_breakout": {"breakout_bps": 100}},
        )
        assert desk.mode == "paper"
    finally:
        store.close()


def test_registry_module_fallback_is_guarded(tmp_path: Path) -> None:
    """resolve_factory returning a module object must not be called as a class."""
    store = _open_store(tmp_path)
    try:
        with pytest.raises(LivePaperError, match="no strategy class"):
            build_live_paper(
                mode="paper",
                store=store,
                clock=FixtureClock(0.0),
                place=_never_place,
                strategy_ids=("legacy_screening",),
            )
    finally:
        store.close()
    # The guard itself refuses a module object outright.
    with pytest.raises(LivePaperError):
        strategy_factory("legacy_screening")
    assert isinstance(strategy_factory("momentum_breakout"), type)
    assert not isinstance(ModuleType("x"), type)


def test_unknown_strategy_refused(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        with pytest.raises(LivePaperError, match="unknown strategy"):
            build_live_paper(
                mode="paper",
                store=store,
                clock=FixtureClock(0.0),
                place=_never_place,
                strategy_ids=("no_such_strategy",),
            )
    finally:
        store.close()


def _names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.alias):
        names = [node.name.split(".")[-1]]
        if node.asname:
            names.append(node.asname)
        return names
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.keyword):
        return [node.arg] if node.arg else []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    return []


def test_no_signing_or_send_syms_in_composed_modules() -> None:
    """AST scan: no signing or send symbol anywhere in the composed modules."""
    offenders: list[str] = []
    for rel in COMPOSED:
        path = SRC / rel
        assert path.is_file(), rel
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for name in _names(node):
                if name in FORBIDDEN:
                    offenders.append(f"{rel}:{node.lineno}: {name!r}")
    assert offenders == []
=======
import inspect
from pathlib import Path

import pytest

from datafeed.readonly_double import ReadOnlyDouble
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.datafeed.price import LivePriceSource
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor import live_paper
from pumpgrok.supervisor.live_paper import LivePaperRoot, build_live_paper_root

ENDPOINT = "https://rpc.example.invalid"
MINT = "MintLive1111111111111111111111111111111111111"
START = 1_767_225_600.0
LIVE_PAPER_SOURCE = Path(live_paper.__file__)

#: Names that would sign or send. The allowlist is empty: none may appear in the root.
FORBIDDEN_SYMBOLS = frozenset(
    {
        "sign",
        "sign_transaction",
        "signTransaction",
        "send_transaction",
        "sendTransaction",
        "send_raw_transaction",
        "sendRawTransaction",
    }
)
ALLOWLIST: frozenset[str] = frozenset()


async def _build(tmp_path: Path, transport: ReadOnlyDouble, **overrides: object) -> LivePaperRoot:
    kwargs: dict[str, object] = {
        "mode": "paper",
        "endpoint": ENDPOINT,
        "transport": transport,
        "clock": FixtureClock(START),
        "rng_seed": 7,
        "data_dir": tmp_path / "desk",
        "budget": RiskBudget(),
        "limits": EngineLimits(),
        "max_age_s": 10.0,
        "max_observations": 4,
    }
    kwargs.update(overrides)
    return await build_live_paper_root(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", ["live", "replay", "manual", "PAPER", ""])
async def test_non_paper_mode_is_refused_before_any_io(tmp_path: Path, mode: str) -> None:
    transport = ReadOnlyDouble()

    with pytest.raises(ValueError):
        await _build(tmp_path, transport, mode=mode)

    assert transport.frames == []
    assert not (tmp_path / "desk").exists()


@pytest.mark.parametrize("endpoint", [None, ""])
async def test_missing_endpoint_is_refused_before_any_io(tmp_path: Path, endpoint: object) -> None:
    transport = ReadOnlyDouble()

    with pytest.raises(ValueError):
        await _build(tmp_path, transport, endpoint=endpoint)

    assert transport.frames == []
    assert not (tmp_path / "desk").exists()


def test_endpoint_has_no_default() -> None:
    parameter = inspect.signature(build_live_paper_root).parameters["endpoint"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


async def test_call_without_endpoint_is_refused(tmp_path: Path) -> None:
    transport = ReadOnlyDouble()

    with pytest.raises(TypeError):
        build_live_paper_root(  # type: ignore[call-arg]
            mode="paper",
            transport=transport,
            clock=FixtureClock(START),
            rng_seed=7,
            data_dir=tmp_path / "desk",
            budget=RiskBudget(),
            limits=EngineLimits(),
            max_age_s=10.0,
            max_observations=4,
        )

    assert transport.frames == []


async def test_paper_root_builds_with_explicit_endpoint_and_double(tmp_path: Path) -> None:
    transport = ReadOnlyDouble()
    root = await _build(tmp_path, transport)
    try:
        assert transport.frames == []
        assert root.boundary.endpoint == ENDPOINT
        assert type(root.prices) is LivePriceSource
        assert root.bridge.price is root.prices

        root.health.note_frame()
        clock = FixtureClock(START)
        await root.bridge.publish(
            CurveObservation(
                mint=MINT,
                ts_utc=clock.utc_iso(),
                s_lamports=42_000_000_000,
                t_units=764_608_076_000_000,
                complete=False,
                source="rpc",
            )
        )
        snapshot = await root.prices.curve(MINT)
        assert snapshot is not None
        assert snapshot.source == "rpc"
    finally:
        root.close()


async def test_root_boundary_reads_reach_double_and_sends_do_not(tmp_path: Path) -> None:
    transport = ReadOnlyDouble()
    root = await _build(tmp_path, transport)
    try:
        await root.boundary.rpc("getAccountInfo", [MINT, {"encoding": "base64"}])
        assert [frame["method"] for _, frame in transport.frames] == ["getAccountInfo"]

        with pytest.raises(ValueError):
            await root.boundary.rpc("sendTransaction", [])
        assert len(transport.frames) == 1
    finally:
        root.close()


def _scan_forbidden(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_SYMBOLS:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_SYMBOLS:
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in FORBIDDEN_SYMBOLS:
                found.add(node.name)
        elif isinstance(node, ast.alias):
            if node.name.split(".")[-1] in FORBIDDEN_SYMBOLS or node.name in FORBIDDEN_SYMBOLS:
                found.add(node.name)
        elif isinstance(node, ast.keyword) and node.arg in FORBIDDEN_SYMBOLS:
            found.add(node.arg)
        elif isinstance(node, ast.Constant) and node.value in FORBIDDEN_SYMBOLS:
            found.add(str(node.value))
    return found


def test_live_paper_root_has_no_signing_or_send_symbol() -> None:
    tree = ast.parse(LIVE_PAPER_SOURCE.read_text(encoding="utf-8"), filename=str(LIVE_PAPER_SOURCE))
    found = _scan_forbidden(tree)
    assert found - ALLOWLIST == set(), found
    assert frozenset() == ALLOWLIST
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
