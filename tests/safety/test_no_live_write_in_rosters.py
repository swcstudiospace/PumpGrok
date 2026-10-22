"""No live-write tool in any shipped roster (INV-S-02).

Loads every ``contracts/tool-rosters/*.yaml`` (plus the shared
``_core.yaml`` grants) and asserts, for each roster:

- no tool entry carries ``side_effect: live-write``;
- no tool name starts with ``exec.live``;
- every tool name matches ``TOOL_NAME_RE`` (R19);
- the effective roster size is 8..15 inclusive (R35).

This is the pytest twin of the G-7 gate; both must hold.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ROSTERS = REPO_ROOT / "contracts" / "tool-rosters"

TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def _rosters() -> list[Path]:
    assert ROSTERS.is_dir(), "contracts/tool-rosters is missing"
    files = sorted(p for p in ROSTERS.glob("*.yaml") if p.name != "_core.yaml")
    assert files, "no roster files found"
    return files


def _core_grants() -> list[str]:
    core = ROSTERS / "_core.yaml"
    if not core.is_file():
        return []
    doc = yaml.safe_load(core.read_text(encoding="utf-8")) or {}
    return [str(tool["name"]) for tool in doc.get("tools", [])]


def _check_roster(path: Path, core: list[str]) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names = [str(tool["name"]) for tool in doc.get("tools", [])]
    problems: list[str] = []
    for tool in doc.get("tools", []):
        name = str(tool["name"])
        if str(tool.get("side_effect", "")) == "live-write":
            problems.append(f"{path.name}: {name} carries live-write")
        if name.startswith("exec.live"):
            problems.append(f"{path.name}: {name} uses the exec.live prefix")
        if TOOL_NAME_RE.fullmatch(name) is None:
            problems.append(f"{path.name}: {name} violates TOOL_NAME_RE")
    effective = sorted(set(names) | set(core))
    if not 8 <= len(effective) <= 15:
        problems.append(f"{path.name}: effective size {len(effective)} outside 8..15")
    return problems


def test_rosters_have_no_live_write() -> None:
    """INV-S-02: no live-write, no exec.live*, names valid, size 8..15."""
    core = _core_grants()
    problems: list[str] = []
    for path in _rosters():
        problems.extend(_check_roster(path, core))
    assert problems == []


@pytest.mark.parametrize(
    ("name", "side_effect", "bad"),
    [
        ("desk.state_status", "read", False),
        ("exec.place", "write", False),
        ("exec.live_place", "live-write", True),
        ("risk.kill_switch", "live-write", True),
        ("BadName", "read", True),
        ("exec place", "read", True),
    ],
)
def test_entry_is_classified(name: str, side_effect: str, bad: bool) -> None:
    problems: list[str] = []
    if side_effect == "live-write":
        problems.append("live-write")
    if name.startswith("exec.live"):
        problems.append("exec.live prefix")
    if TOOL_NAME_RE.fullmatch(name) is None:
        problems.append("name regex")
    assert bool(problems) is bad, problems
