"""Fast and soak split (D-12): the default test path excludes the slow soak, and make targets
select tests by marker.

The test reads pyproject.toml and asks make for its dry-run recipe text. It never collects or
runs tests, so the soak suite is not started here.
"""

from __future__ import annotations

import shlex
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _ini_options() -> dict:
    return tomllib.loads(PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]


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


def test_slow_marker_is_registered():
    assert any(str(marker).startswith("slow:") for marker in _ini_options()["markers"])


def test_default_addopts_deselect_the_slow_marker():
    tokens = shlex.split(_ini_options()["addopts"])
    assert "-m" in tokens
    assert tokens[tokens.index("-m") + 1] == "not slow"


def test_soak_suite_is_marked_slow():
    soak_files = sorted((REPO_ROOT / "tests" / "soak").glob("test_*.py"))
    assert soak_files
    for path in soak_files:
        assert "@pytest.mark.slow" in path.read_text(), path.name


def test_make_test_is_the_fast_path():
    assert "-m 'not slow'" in _make_dry_run("test")


def test_make_test_soak_selects_only_the_slow_marker():
    recipe = _make_dry_run("test-soak")
    assert "-m slow" in recipe
    assert "not slow" not in recipe


def test_make_test_all_selects_every_marker():
    assert "-m 'slow or not slow'" in _make_dry_run("test-all")


def test_make_cov_measures_branches_and_writes_coverage_xml():
    recipe = _make_dry_run("cov")
    assert "--cov=pumpgrok" in recipe
    assert "coverage.xml" in recipe
    assert "-m 'not slow'" in recipe


def test_coverage_floor_is_declared_with_branch_measurement():
    config = tomllib.loads(PYPROJECT.read_text())["tool"]["coverage"]
    assert config["run"]["branch"] is True
    floor = config["report"]["fail_under"]
    assert 0 < floor < 100
