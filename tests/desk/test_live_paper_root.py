"""SC 10: the live-data paper root refuses unless paper, with no fund-moving symbols."""

from __future__ import annotations

import ast
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
