"""No PR-number waiver remains in the gate workflow (CONTEXT D-07).

A waiver keyed on a pull request number lets one PR skip a gate by number, which no receipt
records. Plan 18-07 later raises PR_NUMBER_WAIVERS to exactly one entry and plan 19-04 returns
it to the empty tuple; this file pins the empty tuple until then.

    python3 -m pytest ci/tests/test_no_pr_waivers.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "gates.yml"

PR_NUMBER_WAIVERS: tuple[int, ...] = ()

_NUMERIC_LIST = re.compile(r"fromJSON\(\s*'\[\s*\d")


def _gates_text() -> str:
    return GATES_WORKFLOW.read_text(encoding="utf-8")


def test_waiver_set_is_pinned_empty() -> None:
    assert PR_NUMBER_WAIVERS == ()


def test_gates_workflow_names_no_pull_request_number() -> None:
    assert "pull_request.number" not in _gates_text()


def test_gates_workflow_has_no_numeric_pr_list() -> None:
    assert not _NUMERIC_LIST.search(_gates_text())
