"""PRM-05: promotion is event-triggered only — no timers, no Grok.

AST proof over src/pumpgrok/promotion/: fails on any Clock sleep, any
asyncio.sleep, any timer constructor and any import of the Grok gateway
or model modules. The evaluator is a pure function over an evidence
event, so the test also drives it directly.
"""

from __future__ import annotations

import ast
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.promotion.evaluator import EvidenceView, PromotionEvaluator
from pumpgrok.promotion.stages import Stage
from pumpgrok.promotion.thresholds import PromotionThresholds

PROMOTION_DIR = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "promotion"

FORBIDDEN_IMPORTS = ("pumpgrok.grok", "pumpgrok.models", "openai", "anthropic")
FORBIDDEN_ATTRS = ("sleep", "Timer", "set_interval", "set_timeout")


def _sources() -> list[Path]:
    return sorted(PROMOTION_DIR.rglob("*.py"))


def test_promotion_has_no_grok_import() -> None:
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(("pumpgrok.grok", "pumpgrok.models")), path
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(("pumpgrok.grok", "pumpgrok.models")), path


def test_promotion_has_no_timers_or_sleeps() -> None:
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_ATTRS, f"{path}: .{node.attr}"
            if isinstance(node, ast.Name) and node.id == "Timer":
                raise AssertionError(f"{path}: Timer constructor")


def test_evaluator_is_a_pure_function_over_evidence() -> None:
    evaluator = PromotionEvaluator(PromotionThresholds())
    evidence = EvidenceView(
        strategy_id="momentum_breakout",
        eligible=True,
        paper_days=14,
        closed_trades=50,
        profit_factor=Decimal("1.25"),
        drawdown_fraction=Decimal("0.10"),
        event_id="evt-1",
    )
    assert evaluator.next_stage(Stage.BACKTEST, evidence) is Stage.PAPER
    assert evaluator.next_stage(Stage.PAPER, evidence) is Stage.LIVE_ELIGIBLE
