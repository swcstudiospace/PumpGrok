"""The gateway target runs from the repo root, so it shares the root ``var/`` (review finding 3).

``make gateway`` must not change into ``services/desk-gateway``: the desk paths are relative to
the working directory, so a ``cd`` would give the gateway its own ``var/`` while the CLI, the
reports and the kill latch use the root one. The service's environment is selected with
``uv run --project`` instead. Root tests may import ``subprocess``; the INV-S-04 guard covers
``services/`` and ``src/``, not ``tests/``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_dry_run(target: str) -> str:
    make = shutil.which("make")
    if make is None:
        pytest.skip("make is not installed")
    result = subprocess.run(  # fixed argv, no shell
        [make, "-n", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_make_gateway_does_not_change_directory() -> None:
    recipe = _make_dry_run("gateway")
    assert "desk-gateway" in recipe, recipe
    assert "cd " not in recipe, recipe


def test_make_gateway_selects_service_environment_with_project() -> None:
    recipe = _make_dry_run("gateway")
    assert "--project services/desk-gateway" in recipe, recipe
    assert "desk_gateway" in recipe, recipe
