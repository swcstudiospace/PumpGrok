"""Historical banner presence (DOC-04, Phase 7 plans 07-05 and 07-06).

Fixed set from CONTEXT D-05. Each listed file must begin with the exact
first line ``Historical design record``. Plan 07-05 banners the three root
files; the two design files are bannered by plan 07-06, so this module is
expected to fail until 07-06 lands. Acceptance in 07-05 is collection
without error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

BANNER_FIRST_LINE = "Historical design record"

FIXED_SET = (
    "docs/DISCOVERY.md",
    "docs/MIGRATION_MAP.md",
    "docs/upgrade-plan-desk-v2.md",
    "docs/design/interfaces.md",
    "docs/design/paper-engine.md",
)


@pytest.mark.parametrize("relative", FIXED_SET)
def test_file_begins_with_banner(relative: str) -> None:
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    first = text.splitlines()[0].strip() if text else ""
    assert first == BANNER_FIRST_LINE, f"{relative} first line is not the historical banner"
