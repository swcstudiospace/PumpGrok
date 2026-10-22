"""Regression tests for the G-3 secrets gate.

Covers three review findings: excerpts must mask every credential on a line, --staged must scan
the index blobs a commit records, and a renamed file must be scanned under its new path.

Synthetic credentials are assembled at runtime so this file does not trip the gate it tests.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

GATES = Path(__file__).resolve().parents[1] / "gates"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, GATES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load("check_secrets")


def _aws_key() -> str:
    return "AK" + "IA" + "Q3XZ7LMN2PRT8WVB"


def _github_token() -> str:
    return "gh" + "p_" + "aB3dE5fG7hJ9kL1mN2pQ4rS6tU8vW0xY2zA4"


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


def _run_cli(gate, monkeypatch, capsys, *args: str) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["check_secrets.py", *args])
    code = gate.main()
    return code, capsys.readouterr().err


# Finding 1: excerpts must not print a second credential from the same line.


def test_excerpt_hides_every_credential_on_the_line(gate):
    aws, gh = _aws_key(), _github_token()
    line = f'AWS = "{aws}"  GH = "{gh}"'
    findings = gate.scan_line("fixture.py", 1, line)
    assert {"aws_access_key", "github_token"} <= {f["rule"] for f in findings}
    for f in findings:
        assert aws not in f["excerpt"]
        assert gh not in f["excerpt"]


def test_cli_report_never_prints_a_full_credential(gate, tmp_path, monkeypatch, capsys):
    aws, gh = _aws_key(), _github_token()
    (tmp_path / "config.py").write_text(f'AWS = "{aws}"  GH = "{gh}"\n')
    code, err = _run_cli(
        gate, monkeypatch, capsys, "--root", str(tmp_path), "--files", "config.py"
    )
    assert code == 1
    assert "aws_access_key" in err
    assert aws not in err
    assert gh not in err


def test_overlapping_secrets_leave_no_fragment(gate):
    out = gate._redact("x AAAABBBBCCCC y", ["AAAABBBB", "BBBBCCCC"])
    assert "BBBB" not in out
    assert "CCCC" not in out


# Finding 2: --staged must scan the staged blob, not the working-tree file.


def test_staged_credential_is_caught_after_worktree_is_cleaned(
    gate, repo, monkeypatch, capsys
):
    aws = _aws_key()
    (repo / "config.py").write_text(f'KEY = "{aws}"\n')
    _git(repo, "add", "config.py")
    (repo / "config.py").write_text('KEY = "clean"\n')

    code, err = _run_cli(gate, monkeypatch, capsys, "--staged")

    assert code == 1
    assert "config.py:1" in err
    assert "aws_access_key" in err
    assert aws not in err


def test_staged_credential_is_caught_after_worktree_file_is_deleted(
    gate, repo, monkeypatch, capsys
):
    (repo / "config.py").write_text(f'KEY = "{_aws_key()}"\n')
    _git(repo, "add", "config.py")
    (repo / "config.py").unlink()

    code, err = _run_cli(gate, monkeypatch, capsys, "--staged")

    assert code == 1
    assert "config.py:1" in err


def test_clean_staged_content_passes(gate, repo, monkeypatch, capsys):
    (repo / "config.py").write_text('KEY = "clean"\n')
    _git(repo, "add", "config.py")
    (repo / "config.py").write_text(f'KEY = "{_aws_key()}"\n')

    code, _ = _run_cli(gate, monkeypatch, capsys, "--staged")

    # The index holds clean content; the dirty working copy is not what gets committed.
    assert code == 0


def test_staged_deletion_is_not_scanned(gate, repo, monkeypatch, capsys):
    _git(repo, "rm", "-q", "seed.txt")

    code, out_err = _run_cli(gate, monkeypatch, capsys, "--staged")

    assert code == 0, out_err


def test_staged_submodule_pointer_is_skipped(gate, repo, monkeypatch, capsys):
    head = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},vendor-sub")

    assert gate.staged_blobs() == {}
    code, _ = _run_cli(gate, monkeypatch, capsys, "--staged")
    assert code == 0


# Finding 3: a renamed file must be scanned under its new path.


def test_renamed_file_with_credential_is_scanned_under_new_path(
    gate, repo, monkeypatch, capsys
):
    # Filler keeps similarity high so git reports the move as a rename (R), not delete plus add.
    filler = "".join(f"value_{i} = {i}\n" for i in range(30))
    (repo / "old.py").write_text(filler)
    _git(repo, "add", "old.py")
    _git(repo, "commit", "-q", "-m", "add old")
    _git(repo, "mv", "old.py", "new.py")
    (repo / "new.py").write_text(filler + f'KEY = "{_aws_key()}"\n')
    _git(repo, "add", "new.py")

    assert gate.staged_blobs().keys() == {"new.py"}
    code, err = _run_cli(gate, monkeypatch, capsys, "--staged")

    assert code == 1
    assert "new.py:31" in err
    assert _aws_key() not in err


# changed_files and --files must scan a non-ASCII name under its real path. Plain git output quotes
# such names, and the quoted form names no file on disk, so the scan used to skip the file.


def test_changed_non_ascii_file_is_scanned_under_real_path(gate, repo, monkeypatch, capsys):
    base = _git(repo, "rev-parse", "HEAD").strip()
    name = "cl\u00e9_config.py"
    (repo / name).write_text(f'KEY = "{_aws_key()}"\n')
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", "add non-ascii file")

    code, err = _run_cli(gate, monkeypatch, capsys, "--base", base)

    assert code == 1
    assert f"{name}:1" in err
    assert _aws_key() not in err


def test_files_argument_with_non_ascii_name_is_scanned(gate, tmp_path, monkeypatch, capsys):
    name = "cl\u00e9_config.py"
    (tmp_path / name).write_text(f'KEY = "{_aws_key()}"\n')

    code, err = _run_cli(gate, monkeypatch, capsys, "--root", str(tmp_path), "--files", name)

    assert code == 1
    assert f"{name}:1" in err
    assert _aws_key() not in err
