"""STR-05 / criterion 7: no strategy hook reaches an LLM client; an idle runtime makes zero calls.

Three checks:
(a) a static scan of every module under src/pumpgrok/strategies/ finds no import of the Grok
    package, the shared LLM guard module, or a Grok client name;
(b) importing the baseline strategy modules in a fresh interpreter loads no Grok or LLM module,
    so the ban holds through transitive imports too;
(c) with every Grok client constructor and call patched to fail, an idle runtime and a runtime
    driven over real ticks make zero client calls.
"""

from __future__ import annotations

import ast
import asyncio
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.llm import GrokOps
from pumpgrok.grok.gateway import GrokGateway
from pumpgrok.grok.transport import XaiTransport
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.strategies import Intent
from pumpgrok.strategies.legacy import tick_snapshot
from pumpgrok.strategies.mean_reversion import MeanReversion
from pumpgrok.strategies.momentum_breakout import MomentumBreakout
from pumpgrok.strategies.new_launch_sniper import NewLaunchSniper
from pumpgrok.strategies.runtime import StrategyRuntime

REPO = Path(__file__).resolve().parents[2]
STRATEGY_DIR = REPO / "src" / "pumpgrok" / "strategies"
FIXTURES = REPO / "tests" / "fixtures" / "replay"
FORBIDDEN_PREFIXES = ("pumpgrok.grok", "pumpgrok.core.llm")
FORBIDDEN_NAMES = frozenset({"GrokGateway", "GrokOps", "GrokTransport", "XaiTransport"})
BASELINE: tuple[type[Any], ...] = (MomentumBreakout, NewLaunchSniper, MeanReversion)


def _imports(path: Path) -> tuple[set[str], set[str]]:
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
            names.update(alias.name for alias in node.names)
    return modules, names


def test_no_strategy_module_imports_an_llm_client() -> None:
    scanned = sorted(STRATEGY_DIR.rglob("*.py"))
    assert scanned, "the strategy package must exist"
    for path in scanned:
        modules, names = _imports(path)
        offending = sorted(m for m in modules if m.startswith(FORBIDDEN_PREFIXES))
        assert offending == [], f"{path.name} imports an LLM module"
        assert not names & FORBIDDEN_NAMES, f"{path.name} imports an LLM client name"


def test_baseline_import_graph_loads_no_llm_module() -> None:
    code = (
        "import sys\n"
        "import pumpgrok.strategies.momentum_breakout\n"
        "import pumpgrok.strategies.new_launch_sniper\n"
        "import pumpgrok.strategies.mean_reversion\n"
        "import pumpgrok.strategies.recovery\n"
        "loaded = [m for m in sys.modules\n"
        "          if m.startswith(('pumpgrok.grok', 'pumpgrok.core.llm'))]\n"
        "print(sorted(loaded))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == "[]"


def _client_patches() -> list[tuple[Any, str]]:
    return [
        (GrokOps, "__init__"),
        (GrokGateway, "__init__"),
        (GrokGateway, "admit"),
        (XaiTransport, "__init__"),
        (XaiTransport, "__call__"),
    ]


@pytest.fixture
def client_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def boom(target: str) -> Callable[..., object]:
        def refuse(*_args: object, **_kwargs: object) -> object:
            calls.append(target)
            raise AssertionError(f"an LLM client was reached: {target}")

        return refuse

    for owner, attribute in _client_patches():
        monkeypatch.setattr(owner, attribute, boom(f"{owner.__name__}.{attribute}"))
    return calls


async def _noop(_intents: tuple[Intent, ...]) -> None:
    return None


def test_idle_runtime_makes_zero_client_calls(client_calls: list[str]) -> None:
    runtime = StrategyRuntime(
        clock=FixtureClock(start=0.0),
        strategies=tuple(cls() for cls in BASELINE),
        sink=_noop,
    )
    asyncio.run(runtime.run([]))
    assert client_calls == []


def test_driven_runtime_makes_zero_client_calls(client_calls: list[str]) -> None:
    data = load_dataset(FIXTURES / "strat-breakout")
    ticks = sorted((tick_snapshot(event) for event in data.events), key=lambda tick: tick.ts)
    fired: list[Intent] = []

    async def collect(intents: tuple[Intent, ...]) -> None:
        fired.extend(intents)

    runtime = StrategyRuntime(
        clock=FixtureClock(start=0.0),
        strategies=tuple(cls() for cls in BASELINE),
        sink=collect,
    )
    asyncio.run(runtime.run(ticks))
    assert fired, "the driven runtime must reach the strategy hooks"
    assert client_calls == []
