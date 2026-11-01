"""Behaviour guard for the CI check job.

The job used to read pyproject.toml and the Makefile from the pull request head, so a PR could
weaken lint or typing and still pass, and the drift checks never ran in CI. These tests parse
ci.yml, execute its base-overlay step against a local git remote that carries a weakened PR
branch, and confirm that `make check` runs the drift commands.

    python3 -m pytest ci/tests/test_ci_workflow.py -v
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

BASE_PYPROJECT = '[tool.ruff.lint]\nselect = ["E", "F"]\n'
BASE_MAKEFILE = "check:\n\techo base\n"
PR_PYPROJECT = "[tool.ruff.lint]\nselect = []\n"
PR_MAKEFILE = "check:\n\ttrue\n"

DRIFT_COMMANDS = (
    "assemble-prompts.sh --check",
    "generate-templates.py --check",
    "generate-event-schemas.py --check",
    "scripts/check.sh",
)
CANONICAL_COMMANDS = ("ruff check .", "mypy src/", "pytest -q", "pip-audit")


def _check_steps() -> list[dict]:
    return yaml.safe_load(CI_WORKFLOW.read_text())["jobs"]["check"]["steps"]


def _overlay_step(steps: list[dict]) -> dict:
    found = [
        step
        for step in steps
        if "git checkout" in step.get("run", "") and "pyproject.toml" in step.get("run", "")
    ]
    assert len(found) == 1, "the check job needs exactly one base-overlay step"
    return found[0]


def _make_check_index(steps: list[dict]) -> int:
    indexes = [i for i, step in enumerate(steps) if step.get("run") == "make check"]
    assert len(indexes) == 1, "the check job must run `make check` exactly once"
    return indexes[0]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=ci-test",
            "-c",
            "user.email=ci-test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _pr_clone(tmp_path: Path) -> Path:
    """Shallow clone of a PR branch that weakens lint config, as actions/checkout produces."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    (origin / "pyproject.toml").write_text(BASE_PYPROJECT)
    (origin / "Makefile").write_text(BASE_MAKEFILE)
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "base")
    _git(origin, "checkout", "-q", "-b", "pr")
    (origin / "pyproject.toml").write_text(PR_PYPROJECT)
    (origin / "Makefile").write_text(PR_MAKEFILE)
    _git(origin, "commit", "-q", "-am", "weaken lint")
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--branch", "pr", origin.as_uri(), str(clone)],
        check=True,
        capture_output=True,
    )
    return clone


def _run_overlay(clone: Path, base_ref: str) -> None:
    step = _overlay_step(_check_steps())
    # GitHub evaluates ${{ github.base_ref || 'main' }}; the test supplies the result directly.
    env = {**os.environ, "BASE_REF": base_ref}
    # Same shell GitHub uses for run: steps on Linux.
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=clone,
        env=env,
        check=True,
        capture_output=True,
    )


def test_check_job_runs_make_check_once_after_the_base_overlay():
    steps = _check_steps()
    assert steps.index(_overlay_step(steps)) < _make_check_index(steps)


def test_make_check_reaches_the_drift_and_canonical_commands():
    plan = subprocess.run(
        ["make", "-n", "check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for command in (*DRIFT_COMMANDS, *CANONICAL_COMMANDS):
        assert command in plan, f"make check does not run: {command}"


def test_overlay_restores_base_lint_and_check_config_on_a_pull_request(tmp_path):
    clone = _pr_clone(tmp_path)
    assert (clone / "pyproject.toml").read_text() == PR_PYPROJECT

    _run_overlay(clone, base_ref="main")

    assert (clone / "pyproject.toml").read_text() == BASE_PYPROJECT
    assert (clone / "Makefile").read_text() == BASE_MAKEFILE


def test_overlay_fails_the_job_when_the_base_ref_is_missing(tmp_path):
    clone = _pr_clone(tmp_path)
    with pytest.raises(subprocess.CalledProcessError):
        _run_overlay(clone, base_ref="no-such-base-branch")
