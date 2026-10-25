"""INT-05: ambient randomness lives only at the two composition roots.

``os.urandom`` appears only in ``core/ids.py`` (approval-id root) and
``core/binding_key.py`` (binding-key root); the replay ``DEFAULT_SEED``
symbol never leaves ``src/pumpgrok/replay/``; production id/RNG factories
take an explicit seed from the composition root instead of the replay
fallback. Deterministic, no network.
"""

from __future__ import annotations

import asyncio
import ast
import inspect
import re
from pathlib import Path

import httpx

from pumpgrok.cli import _mint_approval_id
from pumpgrok.core.ids import ULID_RE, IdFactory, mint_approval_id
from pumpgrok.core.registry import ToolRegistry
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.tools import build_operator_registry, build_registry
from pumpgrok.tools.onchain.rpc import RpcClient

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"
REPLAY = SRC / "replay"
START = 1469918176.385


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_default_seed_never_leaves_replay() -> None:
    """No ``DEFAULT_SEED`` import or reference outside ``src/pumpgrok/replay/``."""
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if REPLAY in path.parents:
            continue
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "pumpgrok.replay.rng":
                if any(a.name == "DEFAULT_SEED" for a in node.names):
                    offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
            elif isinstance(node, ast.Name) and node.id == "DEFAULT_SEED":
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
            elif isinstance(node, ast.Attribute) and node.attr == "DEFAULT_SEED":
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert offenders == []


def test_urandom_roots_are_only_ids_and_binding_key() -> None:
    """``os.urandom`` is referenced only by the two allowlisted roots."""
    allowed = {"core/ids.py", "core/binding_key.py"}
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "urandom":
                if isinstance(node.value, ast.Name) and node.value.id == "os":
                    if rel not in allowed:
                        offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []


def test_production_factories_accept_an_explicit_seed() -> None:
    """Every production id/RNG factory takes its seed from the caller."""
    assert "rng" in inspect.signature(ToolRegistry.__init__).parameters
    assert "rng" in inspect.signature(RpcClient.__init__).parameters
    assert "rng" in inspect.signature(build_registry).parameters
    assert "seed" in inspect.signature(build_operator_registry).parameters

    clock = FixtureClock(start=START)
    first = IdFactory(clock, make_rng(11)).ulid()
    second = IdFactory(FixtureClock(start=START), make_rng(11)).ulid()
    assert first == second

    audits: list[object] = []
    registry = ToolRegistry(
        clock=FixtureClock(start=START),
        audit_sink=audits.append,
        limits_checker=lambda _request, _bot: True,
        rng=make_rng(11),
    )
    assert registry is not None
    client = httpx.AsyncClient()
    try:
        rpc = RpcClient(["https://rpc.invalid"], client, FixtureClock(start=START), make_rng(11))
        assert rpc is not None
    finally:
        asyncio.run(client.aclose())


def test_approval_ids_are_shaped_but_not_seeded() -> None:
    """CLI approval ids keep the ``apr-<ULID>`` shape from the OS-entropy root."""
    for minted in (mint_approval_id(), _mint_approval_id()):
        assert minted.startswith("apr-")
        assert re.match(ULID_RE, minted[len("apr-"):]) is not None
