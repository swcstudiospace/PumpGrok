"""Machine-checked contract for runbook commands (OBS-004, T-05-04).

Only fenced ```bash blocks in docs/runbooks/*.md are checked; prose is never
executed and never checked (RESEARCH Pitfall 19). A copy-paste from a runbook
runs with operator privileges, so every fenced command must be one of:

- a ``pumpgrok`` verb,
- a ``docker compose`` lifecycle verb,
- a FOUNDATION section 6 canonical command, or
- ``uv sync`` / ``uv run`` inside a dev-loop runbook (setup, engine).

``curl`` is rejected unconditionally. ``cp``/``sed`` and interactive editors
are rejected unless an explicit per-line allowlist entry with a reason exists
in this file; the allowlist is currently empty on purpose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_DIR = REPO_ROOT / "docs" / "runbooks"

EXPECTED_RUNBOOKS = (
    "setup.md",
    "engine.md",
    "start_stop.md",
    "kill_switch.md",
    "breaker_reset.md",
    "outage.md",
    "rollback.md",
    "reading_reports.md",
    "go_live.md",
)

KNOWN_PUMPGROK_VERBS = frozenset(
    {
        "doctor",
        "run",
        "paper",
        "state",
        "killswitch",
        "ticket",
        "live",
        "replay",
        "verify",
        "report",
        "scout",
        "risk",
        "chief",
        "rug",
        "journal",
        "audit",
        "tools",
    }
)

DOCKER_LIFECYCLE_VERBS = frozenset(
    {
        "up",
        "down",
        "run",
        "ps",
        "logs",
        "stop",
        "start",
        "restart",
        "build",
        "pull",
        "config",
    }
)

# Runbooks about the dev loop may use uv; every other runbook must use bare
# pumpgrok/docker/canonical commands so operators never depend on a venv.
DEV_LOOP_FILES = frozenset({"setup.md", "engine.md"})
UV_SUBCOMMANDS = frozenset({"sync", "run"})

# Exact fenced lines exempted with a recorded reason. Empty: no exceptions
# granted. Add an entry here (line -> reason) instead of weakening the test.
ALLOWLISTED_LINES: dict[str, str] = {}

FENCE_RE = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def fenced_bash_lines(text: str) -> list[str]:
    """Every non-blank, non-comment line inside ```bash fences."""
    lines: list[str] = []
    for block in FENCE_RE.findall(text):
        for raw in block.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.append(stripped)
    return lines


def check_text(name: str, text: str) -> list[str]:
    """Return one violation string per offending fenced line."""
    violations: list[str] = []
    for line in fenced_bash_lines(text):
        if line in ALLOWLISTED_LINES:
            continue
        tokens = line.split()
        first = tokens[0]
        if "curl" in tokens:
            violations.append(f"{name}: {line!r}: curl is never allowed in runbooks")
            continue
        if first == "pumpgrok":
            if len(tokens) < 2 or tokens[1].startswith("-") or tokens[1] not in KNOWN_PUMPGROK_VERBS:
                violations.append(f"{name}: {line!r}: unknown pumpgrok verb")
            continue
        if first == "docker":
            if len(tokens) < 3 or tokens[1] != "compose" or tokens[2] not in DOCKER_LIFECYCLE_VERBS:
                violations.append(f"{name}: {line!r}: docker is allowed only as docker compose <lifecycle>")
            continue
        if first == "uv":
            if name not in DEV_LOOP_FILES:
                violations.append(f"{name}: {line!r}: uv is allowed only in dev-loop runbooks")
            elif len(tokens) < 2 or tokens[1] not in UV_SUBCOMMANDS:
                violations.append(f"{name}: {line!r}: uv is allowed only as uv sync/run")
            continue
        if first == "./scripts/check.sh":
            continue
        if first == "bash" and len(tokens) > 1 and tokens[1].startswith("scripts/"):
            continue
        if first == "python3" and len(tokens) > 1 and (
            tokens[1].startswith("ci/gates/") or tokens[1].startswith("scripts/")
        ):
            continue
        if first in {"cp", "sed", "awk", "ed", "vi", "vim", "nano", "emacs"}:
            violations.append(
                f"{name}: {line!r}: mutating/editor command needs an allowlist reason"
            )
            continue
        violations.append(f"{name}: {line!r}: not a canonical, pumpgrok, or docker compose command")
    return violations


def _read(name: str) -> str:
    return (RUNBOOK_DIR / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", EXPECTED_RUNBOOKS)
def test_runbook_has_no_forbidden_fenced_commands(name: str) -> None:
    assert check_text(name, _read(name)) == []


def test_all_expected_runbooks_exist() -> None:
    missing = [name for name in EXPECTED_RUNBOOKS if not (RUNBOOK_DIR / name).is_file()]
    assert missing == []


def test_planted_curl_line_fails() -> None:
    """Negative direction: a curl line inside a fence must be flagged."""
    assert check_text("synthetic.md", "```bash\ncurl https://example.invalid/healthz\n```") != []


def test_planted_cp_line_fails_without_allowlist_reason() -> None:
    """Negative direction: cp needs an explicit allowlist entry with a reason."""
    assert check_text("synthetic.md", "```bash\ncp .env.example .env\n```") != []


def test_prose_is_never_checked() -> None:
    """Pitfall 19: cp/curl in prose (outside fences) must not fail."""
    text = "Copy .env.example to .env with cp. Never curl an endpoint by hand.\n"
    assert check_text("synthetic.md", text) == []
