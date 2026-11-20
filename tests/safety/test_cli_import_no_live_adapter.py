"""LIV-01 runtime proof: CLI, backtest and promotion imports never load the live adapter.

A fresh interpreter imports the CLI package and its backtest and promotion modules, then
reports whether the adapter module and the gate module sit in sys.modules. Offline only.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
ADAPTER = "pumpgrok.execution.live.live_adapter"
GATE = "pumpgrok.execution.live.live_gate"
PROBE = (
    "import sys\n"
    "import pumpgrok.cli\n"
    "import pumpgrok.cli.backtest\n"
    "import pumpgrok.cli.promotion\n"
    f"print(int({ADAPTER!r} in sys.modules), int({GATE!r} in sys.modules))\n"
)


def test_cli_backtest_promotion_import_loads_no_live_adapter(tmp_path: Path) -> None:
    """LIV-01: the adapter module stays unloaded; the gate module stays loaded (G-02)."""
    pythonpath = os.pathsep.join([str(SRC), os.environ.get("PYTHONPATH", "")])
    env = {**os.environ, "PYTHONPATH": pythonpath}
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["0", "1"], result.stdout
