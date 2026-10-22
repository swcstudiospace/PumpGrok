"""CHANGELOG phase coverage (OBS-005, SC3b).

Equivalent to the SC3b shell loop::

    for p in 1 2 3 4 5; do grep -q "Phase $p" CHANGELOG.md || exit 1; done

Both heading styles pass: ``## Phase N: ...`` and
``## [Unreleased] - Phase N: ...``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"


@pytest.mark.parametrize("phase", [1, 2, 3, 4, 5])
def test_changelog_carries_phase_heading(phase: int) -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    assert re.search(rf"Phase {phase}\b", text), f"CHANGELOG.md has no Phase {phase} heading"
