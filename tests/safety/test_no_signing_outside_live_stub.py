"""No fund-moving symbols outside the refusing live stub (SEC-003), no ed25519 import elsewhere.

Walks the AST of every ``src/pumpgrok/**/*.py`` file and fails on any exact
``sign``, ``send_transaction``, ``sendTransaction`` or ``Keypair`` symbol,
except under ``src/pumpgrok/execution/live/`` where the refusing
``LiveAdapterStub`` lives. Matching is exact AST equality, never substrings,
so ``signature`` (``engine/analyzer.py``) and docstring mentions never match.

It also fails on any import that names an ``ed25519`` module outside the
decode-only ``src/pumpgrok/core/ed25519_point.py`` (INV-S-01, owner-approved
amendment): ``import ed25519``, ``from x.ed25519 import y`` and
``from x import ed25519`` all count. ``ed25519_point`` is a different name and
never matches.

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

DECODE_ONLY_MODULE = "core/ed25519_point.py"

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


def _names_ed25519_module(node: ast.AST) -> bool:
    """True when an import statement names an ``ed25519`` module or imports one."""
    if isinstance(node, ast.Import):
        return any("ed25519" in alias.name.split(".") for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        module_parts = node.module.split(".") if node.module else []
        return "ed25519" in module_parts or any(alias.name == "ed25519" for alias in node.names)
    return False


def _scan_file(path: Path, rel: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    if not rel.startswith(EXEMPT_PREFIX):
        for node in ast.walk(tree):
            for name in _names(node):
                if name in FORBIDDEN:
                    found.append((node.lineno, f"signing symbol {name!r}"))
    if rel != DECODE_ONLY_MODULE:
        for node in ast.walk(tree):
            if _names_ed25519_module(node):
                found.append((node.lineno, "ed25519 import outside the decode-only module"))
    return [f"{rel}:{line}: {reason}" for line, reason in sorted(found)]


def find_violations(package_root: Path) -> list[str]:
    """Return one `path:line: reason` entry per signing symbol or ed25519 import."""
    found: list[str] = []
    for path in sorted(package_root.rglob("*.py")):
        rel = path.relative_to(package_root).as_posix()
        found.extend(_scan_file(path, rel))
    return found


def test_no_signing_symbols_outside_quarantine() -> None:
    """INV-S-01: no fund-moving symbols outside the refusing live stub."""
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
    ("core/probe.py", "import ed25519\n", True),
    ("core/probe.py", "from cryptography.hazmat.primitives.asymmetric.ed25519 import X\n", True),
    ("core/probe.py", "from cryptography.hazmat.primitives.asymmetric import ed25519\n", True),
    ("core/probe.py", "from . import ed25519\n", True),
    ("core/probe.py", "from .ed25519 import X\n", True),
    ("execution/live/probe.py", "import ed25519\n", True),
    ("core/probe.py", "from pumpgrok.core.ed25519_point import decode_public_point\n", False),
    ("core/probe.py", "import ed25519_point\n", False),
    ("core/ed25519_point.py", "import ed25519\n", False),
    ("core/ed25519_point.py", "def sign(tx):\n    return tx\n", True),
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


def test_planted_ed25519_import_in_scratch_copy_is_caught(tmp_path: Path) -> None:
    package = tmp_path / "pumpgrok"
    shutil.copytree(SRC, package, ignore=shutil.ignore_patterns("__pycache__"))
    ids = package / "core" / "ids.py"
    planted = "\nfrom cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey\n"
    ids.write_text(ids.read_text(encoding="utf-8") + planted)
    found = find_violations(package)
    assert any(
        entry.startswith("core/ids.py:") and "ed25519 import" in entry for entry in found
    ), found
