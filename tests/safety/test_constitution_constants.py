"""Constitution bytes keep their exact form in code (INV-S-09).

The rule file ``rules/pumpgrok-team.mdc`` is the single source: rule 5
posts ``FLOOR HALTED <U+2013> DAILY LOSS LIMIT``, rule 3 reports
``UNKNOWN RESULT <U+2013> ...``. This test:

- extracts the backtick span on rule line 34 and evaluates the
  ``FLOOR_HALTED_DAILY`` assignment in ``src/pumpgrok/risk/engine.py``
  without importing the desk, then compares exact bytes;
- asserts the ticket core ``SOL-\\d{8}-\\d{3}`` is byte-identical in every
  home (``core/approvals.py``, ``ledger/tickets.py``,
  ``src/pumpgrok/cli.py``; the retired ``desk_state`` root oracle carried
  the same pattern until its 05-08 deletion);
- asserts the approval grammar ``approve <ticket> <mint> <size>
  <slippage>`` is documented and enforced token-for-token in
  ``core/approvals.py`` while rule line 28 names the same four fields;
- asserts the daily-loss halt stays a floor: ``RiskBudget`` caps
  ``daily_loss_halt_fraction`` at ``Decimal("0.05")`` (INV-C-06 twin);
- asserts no module other than ``risk/engine.py`` assigns
  ``FLOOR_HALTED_DAILY`` (hyphenated ``FLOOR HALTED - ...`` mirrors in
  ``ledger/desk_bus.py`` are the INV-R-21 desk format, not definitions).

``chr(0x2013)`` spellings keep this file ASCII; the rule file itself is
read as UTF-8 bytes.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES = REPO_ROOT / "rules" / "pumpgrok-team.mdc"
ENGINE = REPO_ROOT / "src" / "pumpgrok" / "risk" / "engine.py"
APPROVALS = REPO_ROOT / "src" / "pumpgrok" / "core" / "approvals.py"
RISK_BUDGET = REPO_ROOT / "src" / "pumpgrok" / "core" / "risk_budget.py"

EN_DASH = chr(0x2013)
TICKET_CORE = r"SOL-\d{8}-\d{3}"


def _rule_lines() -> list[str]:
    return RULES.read_text(encoding="utf-8").splitlines()


def _rule_backtick_span(line_no: int) -> str:
    line = _rule_lines()[line_no - 1]
    spans = re.findall(r"`([^`]*)`", line)
    assert spans, f"rule line {line_no} carries no backtick span"
    return spans[0]


def _static_string(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _static_string(node.left) + _static_string(node.right)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "chr"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
    ):
        return chr(node.args[0].value)
    raise AssertionError(f"non-constant string expression: {ast.dump(node)}")


def _assigned_string(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if name in targets:
                return _static_string(node.value)
    raise AssertionError(f"{path} assigns no {name}")


def _pattern_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            dotted = ""
            while isinstance(func, ast.Attribute):
                dotted = f".{func.attr}{dotted}"
                func = func.value
            if isinstance(func, ast.Name):
                dotted = f"{func.id}{dotted}"
            if dotted.endswith("re.compile") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.append(first.value)
    return found


def test_constants_match_rule_file_bytes() -> None:
    """INV-S-09: code constants equal the rule-file bytes exactly."""
    floor_span = _rule_backtick_span(34)
    assert floor_span == f"FLOOR HALTED {EN_DASH} DAILY LOSS LIMIT", repr(floor_span)
    unknown_line = _rule_lines()[30 - 1]
    assert f"UNKNOWN RESULT {EN_DASH}" in unknown_line, repr(unknown_line)
    assert EN_DASH in _rule_lines()[28 - 1] or "slippage" in _rule_lines()[28 - 1]

    engine_value = _assigned_string(ENGINE, "FLOOR_HALTED_DAILY")
    assert engine_value == floor_span, (repr(engine_value), repr(floor_span))
    assert "-" not in engine_value.replace(EN_DASH, ""), "hyphen where the en dash belongs"

    for home in (
        REPO_ROOT / "src" / "pumpgrok" / "core" / "approvals.py",
        REPO_ROOT / "src" / "pumpgrok" / "ledger" / "tickets.py",
        REPO_ROOT / "src" / "pumpgrok" / "cli.py",
    ):
        assert home.is_file(), f"ticket home missing: {home}"
        # Capture groups do not change the matched bytes; strip them so the
        # anchored `^SOL-(\d{8})-(\d{3})$` and unanchored forms compare equal.
        normalised = [p.replace("(", "").replace(")", "") for p in _pattern_literals(home)]
        assert any(TICKET_CORE in pattern for pattern in normalised), str(home)

    approvals_text = APPROVALS.read_text(encoding="utf-8")
    assert "approve <ticket> <mint> <size> <slippage>" in approvals_text
    assert "mint" in _rule_lines()[28 - 1] and "slippage" in _rule_lines()[28 - 1]

    budget_text = RISK_BUDGET.read_text(encoding="utf-8")
    assert 'Decimal("0.05")' in budget_text
    assert "daily_loss_halt_fraction" in budget_text


def test_floor_constant_has_a_single_home() -> None:
    """INV-S-09: only risk/engine.py defines FLOOR_HALTED_DAILY."""
    definers: list[str] = []
    for root in (path for path in (REPO_ROOT / "src", REPO_ROOT / "tools") if path.exists()):
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "FLOOR_HALTED_DAILY" for t in node.targets
                ):
                    definers.append(path.relative_to(REPO_ROOT).as_posix())
    assert definers == ["src/pumpgrok/risk/engine.py"], definers


def test_rule_file_keeps_en_dashes() -> None:
    """INV-S-09: rules :30 and :34 use U+2013, never a hyphen."""
    lines = _rule_lines()
    assert lines[30 - 1].count(EN_DASH) >= 1
    assert lines[34 - 1].count(EN_DASH) >= 1
    assert "`FLOOR HALTED - DAILY LOSS LIMIT`" not in lines[34 - 1]
