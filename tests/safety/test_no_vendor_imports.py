"""The vendor tree is never imported by src/pumpgrok (INV-S-12).

Ports only: no ``ImportFrom`` whose module starts with ``src.`` or
``vendor`` under ``src/pumpgrok/``. Absolute ``import vendor...`` and
``import src...`` forms are flagged too. Reads by path (JSONL fixtures)
are not imports and are unaffected.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"


def _scan_file(path: Path, rel: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", maxsplit=1)[0]
                if root in {"vendor", "src"}:
                    found.append(f"{rel}:{node.lineno}: imports {root} tree")
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            root = node.module.split(".", maxsplit=1)[0]
            if root in {"vendor", "src"}:
                found.append(f"{rel}:{node.lineno}: imports {root} tree")
    return found


def find_violations() -> list[str]:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found.extend(_scan_file(path, path.relative_to(SRC).as_posix()))
    return found


def test_src_never_imports_vendor() -> None:
    """INV-S-12: no vendor/src imports under src/pumpgrok."""
    assert find_violations() == []


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("from vendor.x import y\n", True),
        ("from src.pumpgrok.core.ids import x\n", True),
        ("import vendor.grokbot\n", True),
        ("from pumpgrok.core.ids import x\n", False),
        ("from . import sibling\n", False),
        ("from .core import ids\n", False),
    ],
)
def test_probe_is_classified(tmp_path: Path, source: str, flagged: bool) -> None:
    package = tmp_path / "mod.py"
    package.write_text(source, encoding="utf-8")
    assert bool(_scan_file(package, "mod.py")) is flagged
