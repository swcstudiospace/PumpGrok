"""Regression tests for ci/gates/check_desk_integrity.py: required directories and .yml files.

contracts/tool-packs/ and grokbot/templates/ are required (T11): an absent directory fails G-7
instead of printing a NOTE and passing. Rosters and packs are read under both .yaml and .yml
(T41), so a .yml file cannot skip the checks.

python3 -m pytest ci/tests/test_desk_integrity_required.py -q
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

GATES = Path(__file__).resolve().parents[1] / "gates"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_desk_integrity", GATES / "check_desk_integrity.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load()


def _tool(name="desk.state_status", kind="read", gates=None, required=None):
    required = list(required or [])
    return {
        "name": name,
        "kind": kind,
        "gates": list(gates or []),
        "description": "fixture tool",
        "input": {
            "type": "object",
            "additionalProperties": False,
            "properties": {field: {"type": "string"} for field in required},
            "required": required,
        },
    }


def _write(directory: Path, name: str, doc: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(yaml.safe_dump(doc, sort_keys=False))


def _rosters(repo: Path) -> Path:
    rosters = repo / "contracts" / "tool-rosters"
    _write(rosters, "_core.yaml", {"tools": [_tool(f"desk.core_{i}") for i in range(8)]})
    _write(
        rosters,
        "bot-04-sniper.yaml",
        {
            "seat": "bot-04-sniper",
            "short": "sniper",
            "endpoint": "/mcp/sniper",
            "core": True,
            "tools": [
                _tool(
                    "sniper.paper_buy",
                    kind="write",
                    gates=["g6"],
                    required=["approval_id", "rollback_plan"],
                )
            ],
        },
    )
    return rosters


def _run(repo: Path, *, packs: bool, templates: bool):
    packs_dir = repo / "contracts" / "tool-packs"
    templates_dir = repo / "grokbot" / "templates"
    if packs:
        packs_dir.mkdir(parents=True)
        (packs_dir / ".gitkeep").touch()
    if templates:
        templates_dir.mkdir(parents=True)
        (templates_dir / ".gitkeep").touch()
    (repo / "prompts").mkdir(exist_ok=True)
    (repo / "prompts-assembled").mkdir(exist_ok=True)
    return gate.run(
        repo,
        _rosters(repo),
        packs_dir=packs_dir,
        prompts_dir=repo / "prompts",
        assembled_dir=repo / "prompts-assembled",
        templates_dir=templates_dir,
    )


class TestRequiredDirectories:
    def test_missing_pack_directory_is_a_problem(self, tmp_path):
        problems, _ = _run(tmp_path, packs=False, templates=True)
        assert any("tool-packs" in p and "pack directory not found" in p for p in problems)

    def test_missing_template_directory_is_a_problem(self, tmp_path):
        problems, _ = _run(tmp_path, packs=True, templates=False)
        assert any(
            "grokbot/templates" in p and "template directory not found" in p for p in problems
        )

    def test_both_directories_present_and_empty_pass(self, tmp_path):
        problems, counts = _run(tmp_path, packs=True, templates=True)
        assert problems == []
        assert counts["rosters"] == 1
        assert counts["packs"] == 0
        assert counts["templates"] == 0

    def test_cli_exits_nonzero_when_a_required_directory_is_absent(self, tmp_path):
        _rosters(tmp_path)
        result = subprocess.run(
            [sys.executable, str(GATES / "check_desk_integrity.py"), "--repo", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "G-7 FAIL" in result.stderr
        assert "pack directory not found" in result.stderr
        assert "template directory not found" in result.stderr


class TestYamlExtensionIsChecked:
    def test_yml_roster_is_checked(self, tmp_path):
        _write(
            tmp_path / "contracts" / "tool-rosters",
            "bot-99-bogus.yml",
            {"seat": "not-a-seat", "short": "x", "endpoint": "/mcp/x", "core": True, "tools": []},
        )
        problems, counts = _run(tmp_path, packs=True, templates=True)
        assert counts["rosters"] == 2
        assert any("bot-99-bogus.yml" in p and "seat 'not-a-seat'" in p for p in problems), problems

    def test_yml_pack_is_checked(self, tmp_path):
        packs_dir = tmp_path / "contracts" / "tool-packs"
        _write(packs_dir, "desk-pack.yml", {"app": "desk-pack"})
        problems, counts = _run(tmp_path, packs=False, templates=True)
        assert counts["packs"] == 1
        assert any("desk-pack.yml" in p and "no 'tools' list" in p for p in problems), problems
