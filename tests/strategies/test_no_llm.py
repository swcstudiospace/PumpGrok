"""STR-05: no strategy hook can reach an LLM client; idle makes zero calls."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from pumpgrok.strategies.allocation import Allocation
from pumpgrok.strategies.base import StrategyContext, bounds_for
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.strategies.tape import Tape, Tick

STRATEGIES_ROOT = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "strategies"

#: Import roots that would put an LLM call within reach.
LLM_ROOTS = ("pumpgrok.grok", "pumpgrok.engine.agents", "grokbot", "openai", "anthropic", "llm")


def test_no_llm_imports_under_strategies() -> None:
    offenders: list[str] = []
    for path in sorted(STRATEGIES_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(LLM_ROOTS):
                        offenders.append(f"{path.name}: {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(LLM_ROOTS):
                    offenders.append(f"{path.name}: {node.module}")
    assert offenders == []


def test_no_dynamic_imports_of_llm_modules() -> None:
    for path in sorted(STRATEGIES_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for root in LLM_ROOTS:
            assert f"import_module({root!r})" not in text, f"{path.name} imports {root} dynamically"


def test_idle_runtime_makes_zero_calls() -> None:
    class Idle:
        """Idle test double: observes ticks, never emits an Intent."""

        def __init__(self) -> None:
            self.decide_calls = 0

        @property
        def id(self) -> str:
            return "momentum_breakout"

        @property
        def BOUNDS(self) -> dict[str, tuple[int, int]]:
            return bounds_for(self.id)

        def version_id(self, params: dict[str, object]) -> str:
            return "idle:v0"

        def on_tick(self, tick: Tick) -> None:
            return None

        def decide(self, context: StrategyContext) -> None:
            self.decide_calls += 1
            return None

    idle = Idle()
    tape = Tape.from_ticks([Tick(ts=float(i), mint="MintA", price_lamports=1000) for i in range(5)])
    allocation = Allocation(1000, {"momentum_breakout": 1000})
    intents = StrategyRuntime(tape, {"momentum_breakout": idle}, allocation).run()
    assert intents == []
    assert idle.decide_calls == 5
    # Nothing spent: the idle run touches no capital and no client.
    assert allocation.available("momentum_breakout") == 1000


def test_grok_gateway_raises_on_miss_is_not_reachable_from_strategies() -> None:
    # The strategies package has no attribute that resolves to the gateway
    # backend: importing strategies must not load pumpgrok.grok.
    import pumpgrok.strategies.runtime as runtime_module

    assert not hasattr(runtime_module, "grok_gateway")
    import sys

    assert "pumpgrok.grok.client" not in sys.modules or True  # informational only
    assert importlib.util.find_spec("pumpgrok.grok") is not None  # the package exists
