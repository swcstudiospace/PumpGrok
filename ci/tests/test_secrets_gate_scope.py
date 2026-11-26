"""Scope regressions for the G-3 secrets gate: which paths and content it scans.

Each test fails on the gate as it stood before these fixes:
- SKIP_DIRS applies only to the --all walk, on paths relative to the root (T01, T03).
- --base scans every commit's blob in base..HEAD, including merge resolutions (T02).
- Long lines are scanned, and the patterns stay linear on them (T04).
- .svg is scanned; lockfiles are exempt by exact name only (T15).
- Every .env file is forbidden except the tracked .env.example template (T16).

Synthetic credentials are assembled at runtime so this file does not trip the gate it tests.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

GATES = Path(__file__).resolve().parents[1] / "gates"


def _load():
    spec = importlib.util.spec_from_file_location("check_secrets_scope", GATES / "check_secrets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load()


def _aws_key() -> str:
    return "AK" + "IA" + "Q3XZ7LMN2PRT8WVB"


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout


@pytest.fixture
def repo(tmp_path, gate, monkeypatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "seed.txt").write_text("seed\n")
    _git(root, "add", "seed.txt")
    _git(root, "commit", "-q", "-m", "seed")
    monkeypatch.setattr(gate, "REPO_ROOT", root)
    return root


def _commit(repo: Path, rel: str, text: str, message: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", message)


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def _run_cli(gate, monkeypatch, capsys, *args: str) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["check_secrets.py", *args])
    code = gate.main()
    return code, capsys.readouterr().err


# T01: SKIP_DIRS prunes only the --all walk. Explicit files and commits are always scanned.


def test_explicit_file_under_a_skip_named_directory_is_scanned(gate, tmp_path, monkeypatch, capsys):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "config.py").write_text(f'KEY = "{_aws_key()}"\n')

    code, err = _run_cli(
        gate, monkeypatch, capsys, "--root", str(tmp_path), "--files", "vendor/config.py"
    )

    assert code == 1
    assert "vendor/config.py:1" in err


def test_committed_file_under_a_skip_named_directory_is_scanned(gate, repo, monkeypatch, capsys):
    base = _head(repo)
    _commit(repo, "build/config.py", f'KEY = "{_aws_key()}"\n', "add build file")

    code, err = _run_cli(gate, monkeypatch, capsys, "--base", base)

    assert code == 1
    assert "build/config.py:1" in err


# T03: the --all walk prunes SKIP_DIRS by path relative to the root, not by absolute path.


def test_all_walk_scans_a_checkout_under_a_skip_named_directory(
    gate, tmp_path, monkeypatch, capsys
):
    root = tmp_path / "build" / "checkout"
    root.mkdir(parents=True)
    (root / "config.py").write_text(f'KEY = "{_aws_key()}"\n')

    code, err = _run_cli(gate, monkeypatch, capsys, "--all", "--root", str(root))

    assert code == 1
    assert "config.py:1" in err


def test_all_walk_still_prunes_skip_dirs_below_the_root(gate, tmp_path, monkeypatch, capsys):
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text(f'KEY = "{_aws_key()}"\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "clean.py").write_text('KEY = "clean"\n')

    code, err = _run_cli(gate, monkeypatch, capsys, "--all", "--root", str(tmp_path))

    assert code == 0, err


# T02: a secret that a later commit removes is still in history, so the gate must catch it.


def test_secret_removed_by_a_later_commit_is_caught(gate, repo, monkeypatch, capsys):
    base = _head(repo)
    aws = _aws_key()
    _commit(repo, "config.py", f'KEY = "{aws}"\n', "add key")
    _commit(repo, "config.py", 'KEY = "clean"\n', "remove key")

    code, err = _run_cli(gate, monkeypatch, capsys, "--base", base)

    assert code == 1
    assert "config.py:1" in err
    assert "aws_access_key" in err
    assert aws not in err


def test_secret_present_only_in_a_merge_commit_is_caught(gate, repo, monkeypatch, capsys):
    base = _head(repo)
    aws = _aws_key()
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "side.txt", "side\n", "side work")
    _git(repo, "checkout", "-q", "-")
    _commit(repo, "main.txt", "main\n", "main work")
    _git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
    (repo / "resolved.py").write_text(f'KEY = "{aws}"\n')
    _git(repo, "add", "resolved.py")
    _git(repo, "commit", "-q", "-m", "merge side")
    _commit(repo, "resolved.py", 'KEY = "clean"\n', "remove key")

    code, err = _run_cli(gate, monkeypatch, capsys, "--base", base)

    assert code == 1
    assert "resolved.py:1" in err
    assert aws not in err


# T04: no line-length cap, and the patterns stay linear on long lines.


def test_secret_on_a_long_line_is_flagged(gate, tmp_path):
    path = tmp_path / "minified.js"
    path.write_text("x = '" + "a" * 5000 + f'\';KEY = "{_aws_key()}"\n')

    rules = {f["rule"] for f in gate.scan_file(path, "minified.js")}

    assert "aws_access_key" in rules


@pytest.mark.parametrize(
    "line",
    [
        "a" * 60_000,
        "0123456789abcdef" * 4_000,
        "1" * 60_000,
        "helius.com/" * 6_000,
        "x.solana-mainnet.quiknode.pro/" * 2_000,
    ],
)
def test_long_adversarial_lines_scan_in_linear_time(gate, line):
    # Before the anchoring, a 20k-character alphanumeric line took about 25 s. Linear scanning
    # finishes these in milliseconds; the bound is loose so the test does not flake on slow hosts.
    started = time.monotonic()
    gate.scan_line("long.txt", 1, line)
    assert time.monotonic() - started < 5.0


# T15: .svg is text and is scanned. Lockfiles are exempt by exact name, not by extension.


def test_svg_is_scanned(gate, tmp_path):
    path = tmp_path / "logo.svg"
    path.write_text(f"<svg><desc>{_aws_key()}</desc></svg>\n")

    rules = {f["rule"] for f in gate.scan_file(path, "logo.svg")}

    assert "aws_access_key" in rules


def test_tracked_uv_lock_is_exempt_by_exact_name(gate, tmp_path):
    for rel in ("uv.lock", "services/desk-gateway/uv.lock"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'KEY = "{_aws_key()}"\n')

        assert gate.scan_file(path, rel) == []


def test_other_lockfiles_are_scanned(gate, tmp_path):
    path = tmp_path / "Cargo.lock"
    path.write_text(f'KEY = "{_aws_key()}"\n')

    rules = {f["rule"] for f in gate.scan_file(path, "Cargo.lock")}

    assert "aws_access_key" in rules


# T16: every .env file is forbidden except the tracked template, which is scanned for content.


@pytest.mark.parametrize("name", [".env", ".env.local", ".env.production"])
def test_env_files_are_forbidden(gate, tmp_path, name):
    path = tmp_path / name
    path.write_text("TOKEN=value\n")

    assert [f["rule"] for f in gate.scan_file(path, name)] == ["forbidden_file"]


def test_env_example_is_scanned_not_forbidden(gate, tmp_path):
    path = tmp_path / ".env.example"
    path.write_text(f"AWS_ACCESS_KEY_ID={_aws_key()}\n")

    rules = {f["rule"] for f in gate.scan_file(path, ".env.example")}

    assert "forbidden_file" not in rules
    assert "aws_access_key" in rules
