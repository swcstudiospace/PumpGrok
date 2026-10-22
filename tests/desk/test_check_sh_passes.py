"""Repository check script passes (INV-S-11).

Runs ``scripts/check.sh`` exactly as CI does (list argv, never a shell)
and asserts exit 0. The script is the executable form of the instruction
hygiene rules: emoji sweep, frontmatter and reference checks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SH = REPO_ROOT / "scripts" / "check.sh"


def test_check_sh_exit_zero() -> None:
    """INV-S-11: scripts/check.sh exits 0 on this tree."""
    assert CHECK_SH.is_file(), "scripts/check.sh is missing"
    completed = subprocess.run(
        ["bash", str(CHECK_SH)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
