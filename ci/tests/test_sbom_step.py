"""The CycloneDX SBOM is generated from the locked dependency export and uploaded as a CI artifact.

These tests read .github/workflows/security-pr.yml only. They do not run cyclonedx-py (that
needs network access to the package index), and they do not replace the security workflow
guards in test_security_workflows.py, which also cover the new job.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_PR = REPO_ROOT / ".github" / "workflows" / "security-pr.yml"
SBOM_FILE = "sbom.cdx.json"
SAME_REPO_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"


@pytest.fixture(scope="module")
def sbom_job() -> dict:
    jobs = yaml.safe_load(SECURITY_PR.read_text())["jobs"]
    matches = [
        job
        for job in jobs.values()
        if any("cyclonedx-py" in step.get("run", "") for step in job.get("steps", []))
    ]
    assert len(matches) == 1, "exactly one job must generate the CycloneDX SBOM"
    return matches[0]


@pytest.fixture(scope="module")
def sbom_run(sbom_job: dict) -> str:
    runs = [step["run"] for step in sbom_job["steps"] if "cyclonedx-py" in step.get("run", "")]
    return "\n".join(runs)


def test_sbom_job_runs_on_a_github_hosted_runner(sbom_job: dict):
    assert sbom_job["runs-on"] == "ubuntu-latest"


def test_sbom_job_skips_fork_pull_requests(sbom_job: dict):
    assert SAME_REPO_GUARD in sbom_job["if"]


def test_sbom_is_generated_from_the_locked_export(sbom_run: str):
    assert (
        "uv export --frozen --no-dev --no-emit-project --format requirements-txt --no-hashes"
        in sbom_run
    )
    assert "cyclonedx-py requirements req.txt" in sbom_run


def test_sbom_generator_is_pinned_and_run_ephemerally(sbom_run: str):
    # uvx runs the pinned generator outside uv.lock, so the dev group stays unchanged (D-13).
    assert re.search(r"uvx --from cyclonedx-bom==\d+\.\d+\.\d+ cyclonedx-py", sbom_run)


def test_sbom_is_written_as_cyclonedx_json(sbom_run: str):
    assert "--of JSON" in sbom_run
    assert f"-o {SBOM_FILE}" in sbom_run


def test_sbom_is_uploaded_as_an_artifact_that_must_exist(sbom_job: dict):
    uploads = [
        step
        for step in sbom_job["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload["with"]["path"] == SBOM_FILE
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload.get("if") == "always()"
