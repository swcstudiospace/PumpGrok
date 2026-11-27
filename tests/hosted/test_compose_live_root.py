"""HOST-16: compose runs the live-data paper root; fixture only in replay profile."""

from __future__ import annotations

from pathlib import Path

import yaml

_services = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))["services"]


def test_default_desk_runs_live_paper_root() -> None:
    command = " ".join(str(x) for x in _services["pumpgrok"]["command"])
    assert "--live-paper" in command
    assert "--replay" not in command
    assert "tests/fixtures/replay/smoke" not in command


def test_fixture_only_under_replay_profile() -> None:
    replay = _services.get("pumpgrok-replay")
    assert replay is not None
    assert "replay" in replay["profiles"]
    command = " ".join(str(x) for x in replay["command"])
    assert "--replay" in command
    assert "tests/fixtures/replay/smoke" in command


def test_live_paper_gated_on_od04_review() -> None:
    env = _services["pumpgrok"]["environment"]
    assert env.get("PUMPGROK_OD04_PROBE_REVIEW") == "approved"


def test_gateway_has_no_fixture_command() -> None:
    assert "command" not in _services["desk-gateway"]
