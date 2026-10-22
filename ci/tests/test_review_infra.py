"""Static invariants for the gate workflow and the runtime image.

Nothing here runs docker or GitHub Actions. It parses the YAML and the Dockerfile and checks
that the files agree with the repository they describe: referenced paths exist, the trusted
overlay cannot silently fail, every command the Dockerfile invokes is installed by it, the
roster contracts land where the loaders resolve them in the installed layout, and the pins match.

    python3 -m pytest ci/tests/test_review_infra.py -v
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path, PurePosixPath

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GATES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "gates.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
GATES_DIR = REPO_ROOT / "ci" / "gates"
ROSTER_SOURCE = REPO_ROOT / "contracts" / "tool-rosters"

# The image's builder venv (UV_PROJECT_ENVIRONMENT) and its site-packages, for python:3.12-slim.
INSTALLED_SITE = PurePosixPath("/opt/venv/lib/python3.12/site-packages")
ROSTER_DEST = "/opt/venv/lib/python3.12/contracts/tool-rosters"

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


# --- Dockerfile and .dockerignore ------------------------------------------------------------


def _dockerfile_lines() -> list[str]:
    return DOCKERFILE.read_text(encoding="utf-8").splitlines()


def _instructions(keyword: str) -> list[str]:
    return [ln.strip() for ln in _dockerfile_lines() if ln.strip().startswith(keyword + " ")]


def _dockerignore_rules() -> list[str]:
    return [
        ln.strip()
        for ln in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def _docker_pattern(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        c = pattern[i]
        out.append("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c))
        i += 1
    return re.compile("".join(out))


def _docker_excluded(path: str, rules: list[str]) -> bool:
    """Docker semantics: a rule matches a path or any of its parent directories; last match wins."""
    parts = path.split("/")
    candidates = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    excluded = False
    for rule in rules:
        negated = rule.startswith("!")
        rx = _docker_pattern(rule[1:] if negated else rule)
        if any(rx.fullmatch(c) for c in candidates):
            excluded = not negated
    return excluded


def test_dockerfile_copy_sources_exist_and_are_not_excluded() -> None:
    rules = _dockerignore_rules()
    sources: list[str] = []
    for line in _instructions("COPY"):
        if line.startswith("COPY --from="):
            continue
        sources.extend(line.split()[1:-1])
    assert sources, "no build-context COPY sources found"
    for src in sources:
        assert (REPO_ROOT / src).exists(), f"COPY source missing from repo: {src}"
        assert not _docker_excluded(src, rules), f"COPY source {src!r} is excluded by .dockerignore"


def test_dockerignore_ships_only_roster_files_from_contracts() -> None:
    rules = _dockerignore_rules()
    assert _docker_excluded("contracts/changes/x.yaml", rules)
    assert _docker_excluded("contracts/events/x.yaml", rules)
    for f in ROSTER_SOURCE.iterdir():
        if f.is_file():
            assert not _docker_excluded(f"contracts/tool-rosters/{f.name}", rules), (
                f"roster file {f.name} is excluded from the build context"
            )


def _loader_resolved_roster_paths() -> dict[str, PurePosixPath]:
    """Where each loader resolves the rosters for an installed (non-editable) pumpgrok package.

    The index into parents[] is read from the loader source, so a change to either loader's
    path expression is caught here instead of silently drifting from the image layout.
    """
    cli_src = (REPO_ROOT / "src" / "pumpgrok" / "cli.py").read_text(encoding="utf-8")
    proj_src = (REPO_ROOT / "src" / "pumpgrok" / "contracts" / "projection.py").read_text(
        encoding="utf-8"
    )
    tools_src = (REPO_ROOT / "src" / "pumpgrok" / "tools" / "__init__.py").read_text(
        encoding="utf-8"
    )
    cli_idx = re.search(r"def _repo_root\(\).*?parents\[(\d+)\]", cli_src, re.S)
    proj_idx = re.search(
        r'def default_contracts_dir\(\).*?parents\[(\d+)\]\s*/\s*"contracts"\s*/\s*"tool-rosters"',
        proj_src,
        re.S,
    )
    assert cli_idx, "cli._repo_root() changed; update the loader-resolution check"
    assert proj_idx, "projection.default_contracts_dir() changed; update the check"
    assert 'repo_root / "contracts" / "tool-rosters"' in tools_src, "registry roster path changed"

    cli_file = INSTALLED_SITE / "pumpgrok" / "cli.py"
    proj_file = INSTALLED_SITE / "pumpgrok" / "contracts" / "projection.py"
    return {
        "cli._repo_root": cli_file.parents[int(cli_idx.group(1))] / "contracts" / "tool-rosters",
        "projection.default_contracts_dir": proj_file.parents[int(proj_idx.group(1))]
        / "contracts"
        / "tool-rosters",
    }


def test_roster_copy_destination_equals_loader_resolved_path() -> None:
    resolved = _loader_resolved_roster_paths()
    assert {str(p) for p in resolved.values()} == {ROSTER_DEST}, resolved
    copies = [ln for ln in _instructions("COPY") if ln.split()[-1] == ROSTER_DEST]
    assert len(copies) == 1, f"expected one COPY into {ROSTER_DEST}, found {copies}"
    assert copies[0].split()[1] == "contracts/tool-rosters"


def test_roster_source_directory_exists_with_core_and_bot_manifests() -> None:
    assert ROSTER_SOURCE.is_dir()
    assert (ROSTER_SOURCE / "_core.yaml").is_file()
    assert any(ROSTER_SOURCE.glob("bot-*.yaml"))


def test_roster_copy_is_built_after_install_and_made_readable() -> None:
    lines = [ln.strip() for ln in _dockerfile_lines()]
    sync_i = next(i for i, ln in enumerate(lines) if ln.startswith("RUN uv sync"))
    copy_i = next(i for i, ln in enumerate(lines) if ln.startswith("COPY contracts/tool-rosters "))
    runtime_i = next(
        i for i, ln in enumerate(lines) if ln.startswith("FROM python") and "AS runtime" in ln
    )
    chmod_i = None
    for i, ln in enumerate(lines):
        m = re.fullmatch(r"RUN chmod -R a\+rX (\S+)", ln)
        if m and ROSTER_DEST.startswith(m.group(1) + "/"):
            chmod_i = i
    assert chmod_i is not None, "no chmod -R a+rX covers the roster destination"
    # After uv sync (which would not touch it), before the runtime stage copies /opt/venv.
    assert sync_i < copy_i < chmod_i < runtime_i


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
