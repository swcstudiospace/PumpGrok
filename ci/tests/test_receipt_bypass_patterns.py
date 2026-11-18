"""Regression tests for the G-2 bypass patterns in ci/gates/check_receipt.py.

Covers two triaged findings:
  - T05: `pytest --collect-only` (and its `--co` alias) must be refused as a bypass. The old
    pattern `pytest.*--co\\b` never matched the long form because `\\b` cannot follow `--co`
    inside `--collect-only`.
  - T17: the inline live flag must be refused in any letter case, as check_rollback.py already
    does with re.IGNORECASE. `PUMPGROK_LIVE_ENABLE=TRUE` is a bypass attempt too.

    python3 -m pytest ci/tests/test_receipt_bypass_patterns.py -q
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

GATES = Path(__file__).resolve().parents[1] / "gates"


def _load_receipt_gate():
    spec = importlib.util.spec_from_file_location("check_receipt", GATES / "check_receipt.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def receipt_gate():
    return _load_receipt_gate()


def _receipt_for(cmd: str) -> dict:
    return {
        "task_id": "PG-1",
        "bot": "bot-04-sniper",
        "approved_by": "bot-02-risk",
        "commands": [{"cmd": cmd, "exit_code": 0, "output_tail": "collected 3 items"}],
        "claims": [{"claim": "ran", "evidence_command_index": 0}],
        "unverified": ["live RPC behaviour"],
    }


@pytest.mark.parametrize(
    "cmd",
    [
        "uv run pytest -q --collect-only",
        "uv run pytest --collect-only -q tests/",
        "uv run pytest --co -q",
        "pytest --co",
    ],
)
def test_collect_only_is_refused_as_a_bypass(receipt_gate, cmd):
    problems = receipt_gate.check(_receipt_for(cmd), "bot-04-sniper")
    assert any("contains a bypass" in p for p in problems), problems


@pytest.mark.parametrize(
    "cmd",
    [
        "uv run pytest -q",
        "uv run pytest --color=yes -q",
        "uv run pytest --cov=src -q",
        "uv run pytest --config-file=pytest.ini -q",
    ],
)
def test_real_pytest_runs_are_not_flagged_as_collect_only(receipt_gate, cmd):
    problems = receipt_gate.check(_receipt_for(cmd), "bot-04-sniper")
    assert not any("collect-only" in p for p in problems), problems


@pytest.mark.parametrize(
    "cmd",
    [
        "PUMPGROK_LIVE_ENABLE=TRUE uv run pumpgrok run --mode paper",
        "PUMPGROK_LIVE_ENABLE=True uv run pumpgrok run --mode paper",
        "PUMPGROK_LIVE_ENABLE=1 uv run pumpgrok run --mode paper",
    ],
)
def test_live_flag_is_refused_in_any_letter_case(receipt_gate, cmd):
    problems = receipt_gate.check(_receipt_for(cmd), "bot-04-sniper")
    assert any("contains a bypass" in p for p in problems), problems


def test_live_flag_set_to_zero_is_not_flagged(receipt_gate):
    problems = receipt_gate.check(
        _receipt_for("PUMPGROK_LIVE_ENABLE=0 uv run pumpgrok run --mode paper"), "bot-04-sniper"
    )
    assert not any("contains a bypass" in p for p in problems), problems
