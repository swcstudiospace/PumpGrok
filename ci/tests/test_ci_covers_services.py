"""CI lint, typecheck and audit cover services/ once a service lands (D-13).

The check job in ci.yml runs `make lint typecheck test audit`. The Makefile makes the service
steps of lint, typecheck and audit path-conditional on a service source tree. These tests pin the
gating behaviour, not whether the tree exists: they override SERVICE_SRC on the make command line
to exercise both branches, and they check that the default recipe follows the directory's real
existence. Adding services/desk-signer/src later does not fail them. Only `make -n` runs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SERVICE_DIR = "services/desk-signer"
SERVICE_SRC = f"{SERVICE_DIR}/src"


def _make_dry_run(target: str, *overrides: str) -> str:
    result = subprocess.run(
        ["make", "-n", target, *overrides],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return result.stdout


def _check_job_runs() -> str:
    jobs = yaml.safe_load(CI_WORKFLOW.read_text())["jobs"]
    return " ".join(step.get("run", "") for step in jobs["check"]["steps"])


def test_ci_check_job_runs_the_service_aware_make_targets():
    assert "make lint typecheck test audit" in _check_job_runs()


def test_makefile_service_wildcard_is_path_conditional_on_desk_signer():
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert f"$(wildcard {SERVICE_SRC})" in makefile


@pytest.mark.parametrize(
    ("target", "service_step", "skipped"),
    [
        ("lint", f"uv run ruff check {SERVICE_SRC}", "service lint skipped"),
        ("typecheck", f"uv run mypy {SERVICE_SRC}", "service typecheck skipped"),
        ("audit", "pip-audit -r /tmp/pumpgrok-service-req.txt --strict", "service audit skipped"),
    ],
)
def test_service_step_runs_when_the_src_tree_is_set(target, service_step, skipped):
    assert service_step in _make_dry_run(target, f"SERVICE_SRC={SERVICE_SRC}")


@pytest.mark.parametrize(
    ("target", "service_step", "skipped"),
    [
        ("lint", f"uv run ruff check {SERVICE_SRC}", "service lint skipped"),
        ("typecheck", f"uv run mypy {SERVICE_SRC}", "service typecheck skipped"),
        ("audit", "pip-audit -r /tmp/pumpgrok-service-req.txt --strict", "service audit skipped"),
    ],
)
def test_service_step_is_replaced_by_a_skip_message_when_the_src_tree_is_empty(
    target, service_step, skipped
):
    recipe = _make_dry_run(target, "SERVICE_SRC=")
    assert skipped in recipe
    assert service_step not in recipe


@pytest.mark.parametrize("target", ["lint", "typecheck", "audit"])
def test_default_recipe_follows_the_directory_existence(target):
    recipe = _make_dry_run(target)
    tree_present = (REPO_ROOT / SERVICE_SRC).is_dir()
    assert (f"service {target} skipped" in recipe) == (not tree_present)


def test_typecheck_keeps_the_root_src_check_in_every_case():
    assert "uv run mypy src/" in _make_dry_run("typecheck")
