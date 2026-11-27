"""No PR-number waiver remains in the gate workflow (CONTEXT D-07).

A waiver keyed on a pull request number lets one PR skip a gate by number, which no receipt
records. This test parses every ``if:`` expression in gates.yml and rejects numeric literals
compared against any PR-number expression (``pull_request.number``, ``github.event.number``).

    python3 -m pytest ci/tests/test_no_pr_waivers.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GATES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "gates.yml"

# A numeric literal compared against a PR number — in either order.
_PR_NUMBER_COMPARISON = re.compile(
    r"(?:pull_request\.number|github\.event\.number)\s*(?:==|!=|>=|<=|>|<|in)\s*'?\[?\s*\d"
    r"|(?<![\d.])\d+\s*(?:==|!=|>=|<=|>|<)\s*(?:pull_request\.number|github\.event\.number)"
    r"|fromJSON\(\s*'\[\s*\d"
)


def _workflow() -> dict:
    return yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))


def _if_expressions() -> list[str]:
    """Every job- and step-level ``if:`` expression in the gates workflow."""
    expressions: list[str] = []
    for job in (_workflow().get("jobs") or {}).values():
        job_if = job.get("if")
        if isinstance(job_if, str):
            expressions.append(job_if)
        for step in job.get("steps") or []:
            step_if = step.get("if") if isinstance(step, dict) else None
            if isinstance(step_if, str):
                expressions.append(step_if)
    return expressions


def test_gates_workflow_has_no_numeric_pr_comparison() -> None:
    expressions = _if_expressions()
    assert expressions, "gates.yml must have if: expressions for the scan to mean anything"
    offenders = [expr for expr in expressions if _PR_NUMBER_COMPARISON.search(expr)]
    assert not offenders, f"PR-number waivers in gates.yml if: expressions: {offenders}"
