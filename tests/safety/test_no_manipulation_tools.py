"""Skeleton guard: the desk cannot manipulate venue or social rails (SC4).

Phase 3 skeleton (completed by RISK-007 in Phase 5): asserts the social
directory exists with real content (non-vacuous), scans it for write-verb
and manipulation helpers with the SC4 literal plus an AST pass, and
asserts no registered catalog tool carries a manipulation name.
"""

from __future__ import annotations

import ast
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import httpx

from pumpgrok.core.side_effect import SideEffect
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools import build_registry, register_read_tools
from pumpgrok.tools.onchain.rpc import RpcClient

SOCIAL = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "tools" / "social"

# SC4 literal, verbatim: bare write verbs or a write-verb method argument.
_SC4 = re.compile(r"\b(post|put|patch|delete)\b|method=['\"](POST|PUT|PATCH|DELETE)")

# RISK-007 manipulation stems (substring match inside social/ only).
_STEMS = ("post", "reply", "like", "follow", "dm", "broadcast", "wash", "volume")


def test_social_directory_is_non_empty() -> None:
    assert SOCIAL.is_dir(), "tools/social/ must exist for the SC4 check to mean anything"
    py_files = sorted(p for p in SOCIAL.glob("*.py") if p.name != "__pycache__")
    assert len(py_files) >= 1, "tools/social/ must hold at least one module"
    assert any(p.read_text(encoding="utf-8").strip() for p in py_files)


def test_social_has_no_write_verbs_sc4_literal() -> None:
    for path in sorted(SOCIAL.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        hits = _SC4.findall(text)
        assert not hits, f"{path.name} matches the SC4 write-verb check: {hits[:3]}"


def test_social_has_no_manipulation_helpers() -> None:
    for path in sorted(SOCIAL.glob("*.py")):
        lowered = path.read_text(encoding="utf-8").lower()
        for stem in _STEMS:
            assert stem not in lowered, f"{path.name} mentions manipulation stem {stem!r}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("post", "put", "patch", "delete"):
                raise AssertionError(f"{path.name} calls write-verb method {node.attr}")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in _STEMS + ("post", "put", "patch", "delete"), (
                    f"{path.name} defines manipulation helper {node.name}"
                )


def test_registered_tools_carry_no_manipulation_names() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no network in the skeleton guard")

    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    rpc = RpcClient(
        ["https://rpc.invalid"],
        httpx.AsyncClient(transport=transport),
        FixtureClock(start=1469918176.385),
        rng=random.Random(21),
    )
    reg, _ = build_registry(clock=FixtureClock(start=1469918176.385), rng=random.Random(22))
    register_read_tools(reg, rpc)
    assert reg.names(), "registry must hold tools for the name scan to mean anything"
    for name in reg.names():
        for stem in _STEMS:
            assert stem not in name, f"tool {name} carries manipulation stem {stem!r}"
        spec = reg.spec(name)
        assert spec.side_effect is SideEffect.READ
