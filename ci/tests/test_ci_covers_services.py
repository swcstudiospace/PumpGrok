"""CI lint, typecheck and audit cover services/ once a service lands (D-13).

The check job in ci.yml runs `make lint typecheck test audit`. The Makefile makes each of those
path-conditional on a service source tree, so these tests read the workflow and ask make for
dry-run recipes. Nothing is executed beyond `make -n`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SERVICE_DIR = "services/desk-signer"


def _make_dry_run(target: str) -> str:
    result = subprocess.run(
        ["make", "-n", target],
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
    assert "make lint typecheck cov audit" in _check_job_runs()


def test_ci_check_job_enforces_the_coverage_floor_through_make_cov():
    cov = _make_dry_run("cov")
    assert "--cov=pumpgrok" in cov
    assert "pytest -q -m 'not slow'" in cov


def test_make_check_enforces_the_coverage_floor_not_only_the_fast_suite():
    recipe = _make_dry_run("check")
    assert "--cov=pumpgrok" in recipe


def test_makefile_service_wildcard_is_path_conditional_on_desk_signer():
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert f"$(wildcard {SERVICE_DIR}/src)" in makefile


def test_no_service_tree_is_present_for_the_gate_today():
    assert not (REPO_ROOT / SERVICE_DIR / "src").exists()


def test_lint_mentions_services_as_a_path_conditional_step():
    assert "services" in _make_dry_run("lint")


def test_typecheck_mentions_services_as_a_path_conditional_step():
    assert "services" in _make_dry_run("typecheck")


def test_audit_mentions_services_as_a_path_conditional_step():
    assert "services" in _make_dry_run("audit")


def test_typecheck_stays_a_no_op_for_services_until_desk_signer_lands():
    recipe = _make_dry_run("typecheck")
    assert "mypy services/" not in recipe
    assert "mypy src/" in recipe


def test_audit_stays_a_no_op_for_services_until_desk_signer_lands():
    recipe = _make_dry_run("audit")
    assert "pip-audit -r /tmp/pumpgrok-service-req.txt" not in recipe
    assert "pip-audit -r /tmp/pumpgrok-req.txt --strict" in recipe
