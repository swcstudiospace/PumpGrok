"""The gateway target runs from the repo root, so it shares the root ``var/`` (review finding 3).

``make gateway`` must not change into ``services/desk-gateway``: the desk paths are relative to
the working directory, so a ``cd`` would give the gateway its own ``var/`` while the CLI, the
reports and the kill latch use the root one. The service's environment is selected with
``uv run --project`` instead. Root tests may import ``subprocess``; the INV-S-04 guard covers
``services/`` and ``src/``, not ``tests/``.
"""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_tokens(target: str) -> list[str]:
    make = shutil.which("make")
    # TEST-D-10: one policy — fail when make is absent in CI, skip locally.
    if make is None and os.environ.get("CI"):
        pytest.fail("make is required in CI")
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
    tokens: list[str] = []
    for line in result.stdout.splitlines():
        if line.strip():
            tokens.extend(shlex.split(line))
    return tokens


def test_make_gateway_does_not_change_directory() -> None:
    # TEST-T24: assert on parsed argv tokens — no `cd` token, not a substring.
    tokens = _make_tokens("gateway")
    assert "services/desk-gateway" in tokens, tokens
    assert "cd" not in tokens, tokens


def test_make_gateway_selects_service_environment_with_project() -> None:
    tokens = _make_tokens("gateway")
    assert "--project" in tokens
    assert tokens[tokens.index("--project") + 1] == "services/desk-gateway"
    assert "desk_gateway" in tokens, tokens
