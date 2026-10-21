"""No fund-moving symbols outside the refusing live stub (SEC-003).

Walks the AST of every ``src/pumpgrok/**/*.py`` file and fails on any exact
``sign``, ``send_transaction``, ``sendTransaction`` or ``Keypair`` symbol,
except under ``src/pumpgrok/execution/live/`` where the refusing
``LiveAdapterStub`` lives. Matching is exact AST equality, never substrings,
so ``signature`` (``engine/analyzer.py``) and docstring mentions never match.

Node kinds mirror ``tests/safety/test_static_guards.py``: names, attributes,
import aliases, definitions, arguments, keywords, and string constants.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"

EXEMPT_PREFIX = "execution/live/"

FORBIDDEN = frozenset({"sign", "send_transaction", "sendTransaction", "Keypair"})

LIVE_STUB = SRC / "execution" / "live" / "live_adapter.py"

BANNED_VENUE_IMPORTS = frozenset({"solders", "solana"})
BANNED_STUB_NAMES = frozenset({"Transaction", "VersionedTransaction", "Message"})


def _names(node: ast.AST) -> list[str]:
    """Every exact-match candidate name carried by one AST node."""
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


def _scan_file(path: Path, rel: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for name in _names(node):
            if name in FORBIDDEN:
                found.append((node.lineno, f"signing symbol {name!r}"))
    return [f"{rel}:{line}: {reason}" for line, reason in sorted(found)]


def find_violations(package_root: Path) -> list[str]:
    """Return one `path:line: reason` entry per signing symbol use."""
    found: list[str] = []
    for path in sorted(package_root.rglob("*.py")):
        rel = path.relative_to(package_root).as_posix()
        if rel.startswith(EXEMPT_PREFIX):
            continue
        found.extend(_scan_file(path, rel))
    return found


def test_no_signing_symbols_outside_live_stub() -> None:
    assert find_violations(SRC) == []


def test_live_stub_builds_no_transaction() -> None:
    assert LIVE_STUB.is_file()
    tree = ast.parse(LIVE_STUB.read_text(encoding="utf-8"), filename=str(LIVE_STUB))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in BANNED_VENUE_IMPORTS
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                assert node.module.split(".")[0] not in BANNED_VENUE_IMPORTS
        elif isinstance(node, (ast.Name, ast.Attribute)):
            name = node.id if isinstance(node, ast.Name) else node.attr
            assert name not in BANNED_STUB_NAMES, name


PROBES: list[tuple[str, str, bool]] = [
    ("core/probe.py", "def sign(tx):\n    return tx\n", True),
    ("core/probe.py", "sig = Keypair()\n", True),
    ("core/probe.py", "x.send_transaction(t)\n", True),
    ("core/probe.py", 'getattr(c, "sendTransaction")\n', True),
    ("core/probe.py", "from solders.keypair import Keypair as K\n", True),
    ("core/probe.py", "f(sign=1)\n", True),
    ("core/probe.py", 'signature = raw.get("signature")\n', False),
    ("core/probe.py", '"""Never a real signature here."""\nVALUE = 1\n', False),
    ("core/probe.py", "signature_hash = 1\n", False),
    ("execution/live/probe.py", "def sign(tx):\n    return tx\n", False),
    ("execution/live/probe.py", "sig = Keypair()\n", False),
]


@pytest.mark.parametrize(("rel", "source", "flagged"), PROBES)
def test_probe_is_classified(tmp_path: Path, rel: str, source: str, flagged: bool) -> None:
    package = tmp_path / "pumpgrok"
    target = package / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    found = find_violations(package)
    assert bool(found) is flagged, found


def test_smuggled_signing_symbol_in_scratch_copy_is_caught(tmp_path: Path) -> None:
    package = tmp_path / "pumpgrok"
    shutil.copytree(SRC, package, ignore=shutil.ignore_patterns("__pycache__"))
    ids = package / "core" / "ids.py"
    ids.write_text(ids.read_text(encoding="utf-8") + "\ndef sign(tx):\n    return tx\n")
    found = find_violations(package)
    assert any(entry.startswith("core/ids.py:") for entry in found), found
