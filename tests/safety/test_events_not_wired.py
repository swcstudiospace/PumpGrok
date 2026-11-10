"""Desk loop roots do not import the event bus."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_GUARDED = (
    "pumpgrok.supervisor",
    "pumpgrok.execution",
    "pumpgrok.engine",
    "pumpgrok.replay.runner",
    "pumpgrok.cli.parsing",
    "pumpgrok.cli.verbs_ops",
    "pumpgrok.cli.verbs_state",
    "pumpgrok.cli.dispatch",
)
_BUS = "pumpgrok.events.bus"


def _imports_bus(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == _BUS or alias.name.startswith(f"{_BUS}.") for alias in node.names):
                return True
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and (node.module == _BUS or node.module.startswith(f"{_BUS}."))
        ):
            return True
    return False


def test_guarded_roots_do_not_import_bus() -> None:
    script = (
        "import sys\n"
        + "".join(f"import {_name}\n" for _name in _GUARDED)
        + "from pumpgrok.cli.parsing import build_parser\n"
        + "build_parser()\n"
        + f"assert {_BUS!r} not in sys.modules\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO,
        env={**dict(**{"PYTHONPATH": str(_SRC)}), **dict(__import__("os").environ)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    dispatch = _SRC / "pumpgrok" / "cli" / "dispatch.py"
    tree = ast.parse(dispatch.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        names = {alias.name for alias in node.names}
        if names & {"_verify_verb", "_run"}:
            assert node.module != _BUS
            assert not node.module.startswith(f"{_BUS}.")

    for relative in (
        "pumpgrok/supervisor",
        "pumpgrok/execution",
        "pumpgrok/engine",
        "pumpgrok/replay/runner.py",
        "pumpgrok/cli/parsing.py",
        "pumpgrok/cli/verbs_ops.py",
        "pumpgrok/cli/verbs_state.py",
        "pumpgrok/cli/dispatch.py",
    ):
        root = _SRC / relative
        files = [root] if root.is_file() else list(root.rglob("*.py"))
        offenders = [path for path in files if _imports_bus(path)]
        assert offenders == []
