#!/usr/bin/env python3
"""Gate G-8 — an idle event desk makes zero Grok calls (EVT-12).

The scenario is tests/events/test_idle_zero_grok.py: a full event-mode desk advances 24 virtual
hours with no source events. Its Grok count comes from the production GrokGateway, so this gate
only runs the scenario and reads the verdict. It runs twice:

1. clean: the desk must pass, with zero calls observed;
2. canary (PUMPGROK_IDLE_GROK_CANARY=1): one admitted gateway call is injected into the idle
   window. The run must fail and report IDLE_GROK_CALLS. A gate that passes the canary is blind.

The gate reads no source tree beyond the scenario, so it needs only the stdlib. The scenario needs
pytest and pumpgrok, so the gate uses the first interpreter that imports both: this one, else the
locked .venv (created by `make sync`). Nothing is skipped: no interpreter means a failed gate.

    python3 ci/gates/check_idle_grok.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO = "tests/events/test_idle_zero_grok.py"
CANARY_ENV = "PUMPGROK_IDLE_GROK_CANARY"
INJECTED_MARK = "IDLE_GROK_CALLS="
RUN_TIMEOUT_S = 900
TAIL_LINES = 40


def _venv_python() -> Path:
    return REPO_ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "python"


def _imports_scenario_deps(python: str) -> bool:
    probe = subprocess.run(
        [python, "-c", "import pytest, pumpgrok"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def find_python() -> str | None:
    """The first interpreter that can run the scenario, or None."""
    candidates = [sys.executable, str(_venv_python())]
    for candidate in candidates:
        if Path(candidate).exists() and _imports_scenario_deps(candidate):
            return candidate
    return None


def run_scenario(python: str, *, canary: bool) -> subprocess.CompletedProcess[str] | None:
    """Run the scenario once. None means it did not finish in time, which fails the gate."""
    env = {key: value for key, value in os.environ.items() if key != CANARY_ENV}
    if canary:
        env[CANARY_ENV] = "1"
    try:
        return subprocess.run(
            [python, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider", SCENARIO],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=RUN_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return None


def verdict(
    clean: subprocess.CompletedProcess[str] | None,
    injected: subprocess.CompletedProcess[str] | None,
) -> tuple[bool, str]:
    """Pass only when the clean desk passes and the injected call is caught."""
    if clean is None or clean.returncode != 0:
        return False, "idle desk failed or made a Grok call over 24 virtual hours"
    if injected is None:
        return False, "canary run did not finish; the gate cannot show it catches a call"
    output = injected.stdout + injected.stderr
    if injected.returncode == 0 or INJECTED_MARK not in output:
        return False, "gate did not catch an injected Grok call; it is blind"
    return True, "idle desk: zero Grok calls over 24 virtual hours; injected call detected"


def _tail(run: subprocess.CompletedProcess[str] | None) -> str:
    if run is None:
        return "(timed out)"
    lines = (run.stdout + run.stderr).splitlines()
    return "\n".join(lines[-TAIL_LINES:])


def main() -> int:
    python = find_python()
    if python is None:
        print(
            "check_idle_grok: no interpreter has pytest and pumpgrok; run `make sync` first",
            file=sys.stderr,
        )
        return 1
    clean = run_scenario(python, canary=False)
    injected = run_scenario(python, canary=True) if clean and clean.returncode == 0 else None
    ok, message = verdict(clean, injected)
    if not ok:
        print(f"[FAIL] {message}")
        print(_tail(clean))
        if clean is not None and clean.returncode == 0:
            print(_tail(injected))
        return 1
    print(f"[PASS] {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
