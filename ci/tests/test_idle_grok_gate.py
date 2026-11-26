"""The idle-desk gate (G-8) is wired into the runner, the Makefile and CI, and it catches a call.

The verdict tests use fake subprocess results. The end-to-end test runs the real canary: one
admitted Grok call injected into the 24-hour idle window must make the scenario fail, and the
failure must carry the IDLE_GROK_CALLS marker the gate looks for.

    python3 -m pytest ci/tests/test_idle_grok_gate.py -v
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GATES = REPO_ROOT / "ci" / "gates"
GATE = GATES / "check_idle_grok.py"
RUN_ALL = GATES / "run_all.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = REPO_ROOT / "Makefile"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    return _load(GATE, "check_idle_grok")


def _proc(code: int, output: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["pytest"], returncode=code, stdout=output, stderr="")


def test_run_all_runs_the_idle_gate_last(monkeypatch: pytest.MonkeyPatch) -> None:
    run_all = _load(RUN_ALL, "run_all")
    calls: list[tuple[str, list[str]]] = []

    def fake_run(name: str, argv: list[str]) -> tuple[str, int]:
        calls.append((name, argv))
        return name, 0

    monkeypatch.setattr(run_all, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["run_all.py", "--bot", "bot-02-risk", "--receipt", "r.json"])
    assert run_all.main() == 0
    name, argv = calls[-1]
    assert name.startswith("G-8")
    assert argv == [str(GATE)]


def _check_job_runs() -> list[str]:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["check"]["steps"]
    return [str(step.get("run", "")).strip() for step in steps]


def test_ci_check_job_runs_the_idle_gate() -> None:
    assert "make idle-grok" in _check_job_runs()


def test_makefile_idle_grok_target_runs_the_gate() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "\nidle-grok:" in text
    assert "ci/gates/check_idle_grok.py" in text
    assert "idle-grok" in text.splitlines()[0].split()


def test_verdict_passes_when_clean_passes_and_canary_is_caught(gate: ModuleType) -> None:
    ok, _ = gate.verdict(_proc(0), _proc(1, "IDLE_GROK_CALLS=1 admissions=1"))
    assert ok


def test_verdict_fails_when_the_idle_desk_makes_a_call(gate: ModuleType) -> None:
    ok, message = gate.verdict(_proc(1, "IDLE_GROK_CALLS=1"), _proc(1, "IDLE_GROK_CALLS=1"))
    assert not ok
    assert "idle desk" in message


def test_verdict_fails_when_the_canary_passes(gate: ModuleType) -> None:
    ok, message = gate.verdict(_proc(0), _proc(0))
    assert not ok
    assert "blind" in message


def test_verdict_fails_when_canary_fails_without_the_marker(gate: ModuleType) -> None:
    ok, _ = gate.verdict(_proc(0), _proc(1, "ImportError: nothing ran"))
    assert not ok


def test_verdict_fails_when_a_run_times_out(gate: ModuleType) -> None:
    assert not gate.verdict(None, None)[0]
    assert not gate.verdict(_proc(0), None)[0]


def test_real_canary_call_fails_the_idle_scenario(gate: ModuleType) -> None:
    python = gate.find_python()
    if python is None:
        pytest.fail("no interpreter has pytest and pumpgrok; run `make sync`")
    run = gate.run_scenario(python, canary=True)
    assert run is not None
    assert run.returncode != 0
    assert gate.INJECTED_MARK in run.stdout + run.stderr
