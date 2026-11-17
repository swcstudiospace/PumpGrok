"""The Hermes installer honours ``enabled`` in ``hermes/cron/jobs.yaml``.

Runs ``scripts/hermes-install-cron.sh`` against a copy of the cron tree with a stub
``hermes`` first on PATH. The stub only records its argv as JSON lines. HOME and the
desk path point into tmp_path, so the real Hermes store is never touched.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts" / "hermes-install-cron.sh"

# Job names the installer creates; each equals the ``name`` field in jobs.yaml.
INSTALLED_NAMES = (
    "[bot:scout] discover",
    "[bot:scout] pipeline",
    "[bot:risk] audit-open-leads",
    "[bot:chief] pickup",
    "[bot:rug] watch-paper",
    "[bot:chief] journal-rollup",
)

STUB = f"""#!{sys.executable}
import json
import os
import sys

with open(os.environ["HERMES_STUB_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
"""


def _jobs_by_name(jobs_yaml: Path) -> dict[str, dict]:
    doc = yaml.safe_load(jobs_yaml.read_text(encoding="utf-8"))
    return {job["name"]: job for job in doc["jobs"]}


@pytest.fixture
def sandbox(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(INSTALLER, root / "scripts" / INSTALLER.name)
    shutil.copytree(REPO_ROOT / "hermes" / "cron", root / "hermes" / "cron")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "hermes"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    return {
        "root": root,
        "bin": bin_dir,
        "home": home,
        "log": tmp_path / "hermes-calls.jsonl",
    }


def _run_installer(sandbox: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{sandbox['bin']}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(sandbox["home"]),
        "HERMES_STUB_LOG": str(sandbox["log"]),
    }
    script = sandbox["root"] / "scripts" / INSTALLER.name
    return subprocess.run(
        ["bash", str(script), "--desk", str(sandbox["home"] / "desk")],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _create_calls(sandbox: dict[str, Path]) -> dict[str, list[str]]:
    """Map job name to the argv of its ``hermes -p OWNER cron create`` call."""
    calls: dict[str, list[str]] = {}
    if not sandbox["log"].exists():
        return calls
    for line in sandbox["log"].read_text(encoding="utf-8").splitlines():
        argv = json.loads(line)
        if argv[2:4] != ["cron", "create"]:
            continue
        calls[argv[argv.index("--name") + 1]] = argv
    return calls


def test_installer_creates_each_job_once(sandbox: dict[str, Path]) -> None:
    result = _run_installer(sandbox)
    assert result.returncode == 0, result.stderr
    assert sorted(_create_calls(sandbox)) == sorted(INSTALLED_NAMES)


@pytest.mark.parametrize("name", INSTALLED_NAMES)
def test_job_is_created_paused_exactly_when_disabled_in_yaml(
    sandbox: dict[str, Path], name: str
) -> None:
    result = _run_installer(sandbox)
    assert result.returncode == 0, result.stderr
    enabled = _jobs_by_name(REPO_ROOT / "hermes" / "cron" / "jobs.yaml")[name]["enabled"]
    argv = _create_calls(sandbox)[name]
    assert ("--paused" in argv) is (not enabled), f"{name}: enabled={enabled} argv={argv}"


def test_disabled_job_carries_pause_reason(sandbox: dict[str, Path]) -> None:
    result = _run_installer(sandbox)
    assert result.returncode == 0, result.stderr
    argv = _create_calls(sandbox)["[bot:chief] journal-rollup"]
    reason = argv[argv.index("--paused-reason") + 1]
    assert "enabled: false" in reason
    assert "chief-journal-rollup" in reason


def test_missing_enabled_flag_refuses_before_any_create(sandbox: dict[str, Path]) -> None:
    jobs_yaml = sandbox["root"] / "hermes" / "cron" / "jobs.yaml"
    doc = yaml.safe_load(jobs_yaml.read_text(encoding="utf-8"))
    for job in doc["jobs"]:
        if job["name"] == "[bot:chief] journal-rollup":
            del job["enabled"]
    jobs_yaml.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = _run_installer(sandbox)

    assert result.returncode != 0
    assert "[bot:chief] journal-rollup" in result.stderr
    assert _create_calls(sandbox) == {}
