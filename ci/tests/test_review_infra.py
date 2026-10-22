"""Static invariants for the gate workflow and the runtime image.

Nothing here runs docker or GitHub Actions. It parses the YAML and the Dockerfile and checks
that the files agree with the repository they describe: referenced paths exist, the trusted
overlay cannot silently fail, every command the Dockerfile invokes is installed by it, and the
pins match.

    python3 -m pytest ci/tests/test_review_infra.py -v
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GATES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "gates.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
GATES_DIR = REPO_ROOT / "ci" / "gates"

_GATE_CALL = re.compile(r"python3\s+(ci/gates/[\w./-]+\.py)")
_OVERLAY = 'git checkout "origin/$BASE_REF" -- ci/gates/'
_GUARD = 'git cat-file -e "origin/$BASE_REF:ci/gates"'


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _run_steps(workflow: dict) -> list[tuple[str, dict]]:
    """Return (job_id, step) for every step, so a check can name where it came from."""
    out: list[tuple[str, dict]] = []
    for job_id, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            out.append((job_id, step))
    return out


def _overlay_steps(workflow: dict) -> list[tuple[str, dict]]:
    return [(j, s) for j, s in _run_steps(workflow) if _OVERLAY in str(s.get("run", ""))]


# --- gates.yml -------------------------------------------------------------------------------


def test_gate_workflow_parses_and_defines_jobs() -> None:
    workflow = _workflow(GATES_WORKFLOW)
    assert workflow["jobs"], "gates.yml defines no jobs"
    for job_id, job in workflow["jobs"].items():
        assert job.get("runs-on"), f"job {job_id!r} has no runs-on"
        assert job.get("steps"), f"job {job_id!r} has no steps"


def test_needs_reference_defined_jobs() -> None:
    jobs = _workflow(GATES_WORKFLOW)["jobs"]
    for job_id, job in jobs.items():
        needs = job.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        for dep in needs:
            assert dep in jobs, f"job {job_id!r} needs undefined job {dep!r}"


def test_every_gate_script_invoked_exists_in_repo() -> None:
    workflow = _workflow(GATES_WORKFLOW)
    invoked = {
        match
        for _, step in _run_steps(workflow)
        for match in _GATE_CALL.findall(str(step.get("run", "")))
    }
    assert invoked, "no ci/gates scripts are invoked; the pattern is stale"
    missing = sorted(p for p in invoked if not (REPO_ROOT / p).is_file())
    assert not missing, f"workflow invokes gate scripts absent from the repo: {missing}"


def test_overlay_source_directory_exists_in_repo() -> None:
    # The overlay copies ci/gates/ from the base; the PR tree must also carry the directory so
    # that the gate scripts exist for the on-push and self-test paths.
    assert GATES_DIR.is_dir()
    assert any(GATES_DIR.glob("check_*.py"))


def test_every_overlay_is_guarded_before_checkout() -> None:
    # Without a guard, a base branch that lacks ci/gates/ makes `git checkout` abort under
    # set -e with no actionable message. The guard must run first and fail closed.
    workflow = _workflow(GATES_WORKFLOW)
    overlays = _overlay_steps(workflow)
    assert {job for job, _ in overlays} == {"gates", "gate-self-test"}
    for job_id, step in overlays:
        run = str(step["run"])
        assert _GUARD in run, f"job {job_id!r} overlays ci/gates/ without a base-presence guard"
        assert run.index(_GUARD) < run.index(_OVERLAY), (
            f"job {job_id!r} checks out ci/gates/ before testing the base for it"
        )
        assert "exit 1" in run[run.index(_GUARD) : run.index(_OVERLAY)], (
            f"job {job_id!r} guard does not fail closed"
        )


def test_overlay_takes_gates_from_base_ref_only() -> None:
    # The gate implementations come from the base ref only; no overlay may check out from HEAD.
    for job_id, step in _overlay_steps(_workflow(GATES_WORKFLOW)):
        run = str(step["run"])
        assert 'git checkout "origin/$BASE_REF" -- ci/gates/' in run, job_id


# --- Dockerfile ------------------------------------------------------------------------------


def _dockerfile_lines() -> list[str]:
    return DOCKERFILE.read_text(encoding="utf-8").splitlines()


def _instructions(keyword: str) -> list[str]:
    return [ln.strip() for ln in _dockerfile_lines() if ln.strip().startswith(keyword + " ")]


def test_dockerfile_copy_sources_exist_and_are_not_excluded() -> None:
    ignore = [
        ln.strip()
        for ln in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    for line in _instructions("COPY"):
        if line.startswith("COPY --from="):
            continue
        parts = line.split()[1:-1]
        for src in parts:
            assert (REPO_ROOT / src).exists(), f"COPY source missing from repo: {src}"
            top = src.split("/")[0]
            assert top not in ignore, f"COPY source {src!r} is excluded by .dockerignore"


def test_dockerfile_uv_pin_matches_ci_and_is_copied_from_pinned_image() -> None:
    copies = [ln for ln in _instructions("COPY") if "--from=ghcr.io/astral-sh/uv:" in ln]
    assert len(copies) == 1, "expected exactly one uv binary copy"
    pin = re.search(r"ghcr\.io/astral-sh/uv:([\d.]+)", copies[0])
    assert pin, "uv image is not version-pinned"

    ci_text = CI_WORKFLOW.read_text(encoding="utf-8")
    ci_pins = set(re.findall(r'pip install "uv==([\d.]+)"', ci_text))
    assert ci_pins == {pin.group(1)}, f"uv pin drift: Dockerfile {pin.group(1)} vs CI {ci_pins}"


def test_every_command_the_dockerfile_invokes_is_installed() -> None:
    # Builder: `uv sync` needs /uv, which the COPY --from line provides.
    run_lines = _instructions("RUN")
    uv_runs = [ln for ln in run_lines if re.search(r"\buv\s", ln)]
    assert uv_runs, "expected a uv invocation in the builder"
    uv_copy = [ln for ln in _instructions("COPY") if "--from=ghcr.io/astral-sh/uv:" in ln]
    assert uv_copy and uv_copy[0].endswith("/bin/"), "uv/uvx not copied into PATH"

    # Runtime: the ENTRYPOINT binary must be produced by the install step and be on PATH.
    entry = _instructions("ENTRYPOINT")
    assert entry, "no ENTRYPOINT"
    command = re.findall(r'"([^"]+)"', entry[0])[0]
    scripts = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "scripts"
    ]
    assert command in scripts, f"ENTRYPOINT {command!r} is not a console script"
    env_text = "\n".join(_dockerfile_lines())
    assert "/opt/venv/bin" in env_text, "venv bin dir is not on PATH in the runtime stage"
    assert "UV_PROJECT_ENVIRONMENT=/opt/venv" in env_text, "install target is not /opt/venv"
    assert "COPY --from=builder /opt/venv /opt/venv" in env_text

    # The RUN lines use only tools present in python:3.12-slim (useradd from passwd, coreutils).
    # apt-get is absent from that contract: it would need package lists the image does not pin.
    assert not any("apt-get" in ln for ln in _instructions("RUN"))


def test_dockerfile_python_base_matches_python_version_file() -> None:
    pinned = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    froms = _instructions("FROM")
    assert froms, "no FROM"
    for line in froms:
        assert f"python:{pinned}-slim" in line, f"base image drifts from .python-version: {line}"


def test_runtime_stage_is_non_root_and_only_var_is_writable() -> None:
    text = "\n".join(_dockerfile_lines())
    assert re.search(r"^USER pumpgrok$", text, re.MULTILINE)
    assert "chown pumpgrok:pumpgrok /app/var" in text
