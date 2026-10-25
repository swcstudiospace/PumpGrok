"""UPG-01 / G-09: the upgrade package never touches the live order path.

AST scan: no module under src/pumpgrok/upgrade/ imports anything under
pumpgrok.execution.live, and no live adapter symbol name appears. This
keeps the Phase 10 import-graph proof green by construction.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

UPGRADE_DIR = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "upgrade"

LIVE_MODULE = "pumpgrok.execution.live"

LIVE_SYMBOLS = frozenset(
    {
        "LiveAdapter",
        "LiveAdapterStub",
        "LiveGate",
    }
)


def _live_references(path: Path) -> list[str]:
    """Return one entry per live import or live adapter symbol in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == LIVE_MODULE or item.name.startswith(LIVE_MODULE + "."):
                    found.append(f"{path}:{node.lineno}: import {item.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == LIVE_MODULE or module.startswith(LIVE_MODULE + "."):
                found.append(f"{path}:{node.lineno}: from {module} import ...")
            elif module == "pumpgrok.execution" and any(item.name == "live" for item in node.names):
                found.append(f"{path}:{node.lineno}: from {module} import live")
        elif isinstance(node, ast.Name) and node.id in LIVE_SYMBOLS:
            found.append(f"{path}:{node.lineno}: names {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in LIVE_SYMBOLS:
            found.append(f"{path}:{node.lineno}: names {node.attr}")
    return found


def _guarded_files() -> list[Path]:
    return sorted(path for path in UPGRADE_DIR.rglob("*.py") if "__pycache__" not in path.parts)


def test_upgrade_package_never_touches_live() -> None:
    """G-09: the upgrade package imports nothing live and names no live symbol."""
    assert UPGRADE_DIR.is_dir()
    offenders = []
    for path in _guarded_files():
        offenders.extend(_live_references(path))
    assert offenders == []


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("from pumpgrok.execution.live import LiveGate\n", True),
        ("from pumpgrok.execution import live\n", True),
        ("import pumpgrok.execution.live.live_adapter\n", True),
        ("adapter = LiveAdapterStub()\n", True),
        ("gate = LiveGate()\n", True),
        ("from pumpgrok.backtest.evaluate import CandidateParams\n", False),
        ("from pumpgrok.core.errors import PumpgrokError\n", False),
        ("from . import sibling\n", False),
        ("live_upgrade_note = 'pumpgrok.execution.live'\n", False),
    ],
)
def test_probe_is_classified(tmp_path: Path, source: str, flagged: bool) -> None:
    """The scan flags live imports and adapter symbols, not strings or ports."""
    package = tmp_path / "mod.py"
    package.write_text(source, encoding="utf-8")
    assert bool(_live_references(package)) is flagged
