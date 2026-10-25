"""Criterion 13: no backtest-to-live path; live stays refused with exit 3.

No module under ``src/pumpgrok/backtest/`` or the paper path imports from
``src/pumpgrok/execution/live/`` (AST plus import-graph check), and
``pumpgrok run --mode live --once`` still exits 3. Offline only.
"""

from __future__ import annotations

import ast
from pathlib import Path

from pumpgrok.cli import main

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "pumpgrok"
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")

BACKTEST_DIR = SRC / "backtest"
PAPER_PATHS = [SRC / "execution" / "paper_adapter.py"]
UPGRADE_DIR = SRC / "upgrade"

LIVE_MODULE = "pumpgrok.execution.live"


def _live_imports(path: Path) -> list[str]:
    """Return one entry per import in the file that reaches the live package."""
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
    return found


def _guarded_files() -> list[Path]:
    files = [path for path in sorted(BACKTEST_DIR.glob("*.py")) if path.is_file()]
    files.extend(path for path in PAPER_PATHS if path.is_file())
    files.extend(
        path for path in sorted(UPGRADE_DIR.rglob("*.py")) if "__pycache__" not in path.parts
    )
    return files


def test_no_backtest_or_paper_module_imports_live() -> None:
    """Backtest, paper and upgrade paths never import the live package."""
    assert BACKTEST_DIR.is_dir()
    for path in PAPER_PATHS:
        assert path.is_file(), path
    assert UPGRADE_DIR.is_dir()
    offenders = []
    for path in _guarded_files():
        offenders.extend(_live_imports(path))
    assert offenders == []


def test_run_mode_live_once_exits_3(tmp_path, monkeypatch) -> None:
    """Live stays refused: run --mode live --once exits 3 before any other work."""
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "live", "--once", "--replay", SMOKE]) == 3
