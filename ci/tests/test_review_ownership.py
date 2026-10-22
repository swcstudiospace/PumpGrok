"""Regression tests for G-1 ownership review findings 4 and 5.

Finding 4: a rename must be checked against the owner of its source path as well as its
destination, so changed_files() must report both sides of a rename.

Finding 5: a recursive rule such as 'mine/**/*.py' must not match paths outside 'mine/'.

    python3 -m pytest ci/tests/test_review_ownership.py -q
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

GATES = Path(__file__).resolve().parents[1] / "gates"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, GATES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ownership():
    return _load("check_ownership")


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


@pytest.fixture
def rename_repo(tmp_path: Path) -> tuple[Path, str]:
    """A repo where bot_b/mod.py is a git-detected rename of bot_a/mod.py.

    diff.renames is set explicitly so the fixture reproduces the default rename detection
    that hosts apply to `git diff`.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "tests")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "diff.renames", "true")
    (repo / "bot_a").mkdir()
    (repo / "bot_b").mkdir()
    (repo / "bot_a" / "mod.py").write_text("a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "feature")
    _git(repo, "mv", "bot_a/mod.py", "bot_b/mod.py")
    _git(repo, "commit", "-qm", "move across owners")
    return repo, base


# --- Finding 4: renames report and check the source path ----------------------------------


def test_changed_files_reports_rename_source_and_destination(ownership, monkeypatch, rename_repo):
    repo, base = rename_repo
    monkeypatch.setattr(ownership, "REPO_ROOT", repo)
    assert sorted(ownership.changed_files(base)) == ["bot_a/mod.py", "bot_b/mod.py"]


def test_rename_out_of_foreign_directory_is_flagged_as_foreign(ownership, monkeypatch, rename_repo):
    repo, base = rename_repo
    monkeypatch.setattr(ownership, "REPO_ROOT", repo)
    manifest = {
        "bots": {"bot-a": {}, "bot-b": {}},
        "ownership": [
            {"pattern": "bot_a/**", "owner": "bot-a"},
            {"pattern": "bot_b/**", "owner": "bot-b"},
        ],
    }
    files = ownership.changed_files(base)
    unowned, foreign, contracts = ownership.classify_files(files, manifest, "bot-b")
    assert unowned == []
    assert foreign == [("bot_a/mod.py", "bot-a")]
    assert contracts == []


# --- Finding 5: recursive rules stay inside their directory -------------------------------


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("mine/**/*.py", "mine/a.py", True),
        ("mine/**/*.py", "mine/x/y/a.py", True),
        ("mine/**/*.py", "mine/x/a.txt", False),
        ("mine/**/*.py", "other/private.py", False),
        ("mine/**/*.py", "a/mine/b.py", False),
        ("mine/**/*.py", "minex/a.py", False),
        ("mine/**/*.py", "mine", False),
        ("**/*.py", "a/b/c.py", True),
        ("**/*.py", "c.py", True),
        ("**/*.py", "a/b/c.txt", False),
    ],
)
def test_recursive_pattern_keeps_its_directory_prefix(ownership, pattern, path, expected):
    assert ownership._match(pattern, path) is expected


def test_recursive_rule_does_not_assign_foreign_directory_path(ownership):
    manifest = {
        "bots": {"bot-risk": {}, "bot-a": {}},
        "ownership": [
            {"pattern": "**/*.py", "owner": "bot-risk"},
            {"pattern": "mine/**/*.py", "owner": "bot-a"},
        ],
    }
    assert ownership.resolve_owner("other/private.py", manifest) == ("bot-risk", False)
    assert ownership.resolve_owner("mine/private.py", manifest) == ("bot-a", False)


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("src/*/**/*.py", "src/app/main.py", True),
        ("src/*/**/*.py", "src/app/deep/main.py", True),
        ("src/*/**/*.py", "src/main.py", False),
        ("src/*/**/*.py", "other/app/main.py", False),
        ("dir*/**/*.py", "dirA/a.py", True),
        ("dir*/**/*.py", "dirA/x/a.py", True),
        ("dir*/**/*.py", "other/a.py", False),
        ("dir*/x.py", "dirA/x.py", True),
        ("dir*/x.py", "dirA/y/x.py", False),
    ],
)
def test_wildcard_directory_prefix_still_matches(ownership, pattern, path, expected):
    assert ownership._match(pattern, path) is expected


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("dir*/**", "dirA/x/a.py", True),
        ("dir*/**", "dirA/a.py", True),
        ("dir*/**", "dirA", True),
        ("dir*/**", "other/x/a.py", False),
        ("mine/**", "mine/a/b.py", True),
        ("mine/**", "minex/a.py", False),
    ],
)
def test_wildcard_slash_double_star_prefix_matches(ownership, pattern, path, expected):
    assert ownership._match(pattern, path) is expected
