"""MKT-09 / criterion 10: the live-data paper root refuses non-paper and endpoint-less builds.

Offline only. The transport is the read-only double from ``tests/datafeed``; no test
here reaches a network endpoint. The root has no default endpoint: every build names
one explicitly.
"""

from __future__ import annotations

import ast
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


def _build(tmp_path: Path, transport: ReadOnlyDouble, **overrides: object) -> LivePaperRoot:
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
    return build_live_paper_root(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", ["live", "replay", "manual", "PAPER", ""])
async def test_non_paper_mode_is_refused_before_any_io(tmp_path: Path, mode: str) -> None:
    transport = ReadOnlyDouble()

    with pytest.raises(ValueError):
        _build(tmp_path, transport, mode=mode)

    assert transport.frames == []
    assert not (tmp_path / "desk").exists()


@pytest.mark.parametrize("endpoint", [None, ""])
async def test_missing_endpoint_is_refused_before_any_io(tmp_path: Path, endpoint: object) -> None:
    transport = ReadOnlyDouble()

    with pytest.raises(ValueError):
        _build(tmp_path, transport, endpoint=endpoint)

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
    root = _build(tmp_path, transport)
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
    root = _build(tmp_path, transport)
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
    assert ALLOWLIST == frozenset()
