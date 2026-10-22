"""Regression tests for check_rollback.py: approvals must name the destructive action (G-6)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

GATES = Path(__file__).resolve().parents[1] / "gates"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, GATES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rollback_gate():
    return _load("check_rollback")


def _approval(operation: str, blast_radius: str = "max_notional_sol=0.2") -> dict:
    return {
        "operation": operation,
        "approved_by": "human:operator",
        "at": "2026-10-21T00:00:00Z",
        "blast_radius": blast_radius,
    }


def _run(tmp_path: Path, commands: list[str], approvals: list) -> subprocess.CompletedProcess:
    receipt = {
        "commands": [{"cmd": cmd, "exit_code": 0} for cmd in commands],
        "approvals": approvals,
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    return subprocess.run(
        [sys.executable, str(GATES / "check_rollback.py"), "--receipt", str(path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


class TestApprovalNamesTheAction:
    def test_unrelated_approval_does_not_authorize_destructive_command(self, tmp_path):
        r = _run(tmp_path, ["git reset --hard HEAD~1"], [_approval("cache cleanup")])
        assert r.returncode == 1
        assert "no approval whose operation names this command" in r.stderr

    def test_approval_naming_the_same_command_authorizes_it(self, tmp_path):
        r = _run(tmp_path, ["git reset --hard HEAD~1"], [_approval("git reset --hard HEAD~1")])
        assert r.returncode == 0, r.stderr

    def test_approval_naming_only_the_verb_does_not_authorize(self, tmp_path):
        r = _run(tmp_path, ["git reset --hard HEAD~1"], [_approval("git reset --hard")])
        assert r.returncode == 1

    def test_approval_for_a_different_target_does_not_authorize(self, tmp_path):
        r = _run(tmp_path, ["rm -rf var/replay"], [_approval("rm -rf var/cache")])
        assert r.returncode == 1
        assert "rm -rf var/replay" in r.stderr

    @pytest.mark.parametrize("operation", ["rm -rf var/rep", "rm -rf var", "rm -rf"])
    def test_approval_naming_only_a_prefix_of_the_target_does_not_authorize(
        self, tmp_path, operation
    ):
        r = _run(tmp_path, ["rm -rf var/replay"], [_approval(operation)])
        assert r.returncode == 1

    def test_chained_command_is_not_authorized_by_approval_of_its_first_part(self, tmp_path):
        r = _run(
            tmp_path,
            ["rm -rf var/replay; rm -rf /"],
            [_approval("rm -rf var/replay")],
        )
        assert r.returncode == 1

    def test_trade_approval_for_another_operation_does_not_authorize_trade(self, tmp_path):
        # A complete approval with a notional blast radius, but for a different action.
        r = _run(
            tmp_path,
            ["uv run pumpgrok killswitch clear --by human:op --reason ok"],
            [_approval("cache cleanup", "max_notional_sol=0.2")],
        )
        assert r.returncode == 1
        assert "max_notional_sol=<float>" in r.stderr

    def test_approval_for_the_trade_authorizes_it(self, tmp_path):
        r = _run(
            tmp_path,
            ["uv run pumpgrok killswitch clear --by human:op --reason ok"],
            [_approval("killswitch clear", "max_notional_sol=0.2")],
        )
        assert r.returncode == 0, r.stderr


class TestOneApprovalPerAction:
    def test_one_statement_matching_three_patterns_needs_one_approval(self, rollback_gate):
        cmd = 'sqlite3 var/ledger.sqlite "DELETE FROM events;"'
        destructive, problems = rollback_gate.check_destructive(
            [{"cmd": cmd, "exit_code": 0}], [_approval(cmd)]
        )
        assert len(destructive) == 1  # one command is one action ...
        assert len(destructive[0]["descs"]) == 3  # ... though three patterns matched it
        assert problems == []  # ... with one approval

    def test_one_statement_with_one_approval_passes_end_to_end(self, tmp_path):
        cmd = 'sqlite3 var/ledger.sqlite "DELETE FROM events;"'
        r = _run(tmp_path, [cmd], [_approval(cmd)])
        assert r.returncode == 0, r.stderr

    def test_two_actions_need_two_approvals(self, tmp_path):
        r = _run(
            tmp_path,
            ["rm -rf var/a", "git reset --hard"],
            [_approval("git reset --hard")],
        )
        assert r.returncode == 1
        assert "rm -rf var/a" in r.stderr

    def test_two_actions_with_two_approvals_pass(self, tmp_path):
        r = _run(
            tmp_path,
            ["rm -rf var/a", "git reset --hard"],
            [_approval("rm -rf var/a"), _approval("git reset --hard")],
        )
        assert r.returncode == 0, r.stderr

    def test_one_approval_cannot_cover_two_identical_commands(self, tmp_path):
        r = _run(
            tmp_path,
            ["git reset --hard", "git reset --hard"],
            [_approval("git reset --hard")],
        )
        assert r.returncode == 1

    def test_non_object_approval_is_refused_not_crashed(self, tmp_path):
        r = _run(tmp_path, ["git reset --hard HEAD"], ["git reset --hard HEAD"])
        assert r.returncode == 1
        assert "approvals[0]" in r.stderr


class TestRound2UnrelatedApprovalAndQuotedReason:
    def test_unrelated_approval_with_quoted_reason_does_not_count(self, tmp_path):
        r = _run(
            tmp_path,
            ['git reset --hard --reason "cleanup"'],
            [_approval("cache cleanup")],
        )
        assert r.returncode == 1
        assert "no approval whose operation names this command" in r.stderr

    def test_unquoted_reason_cannot_hide_a_second_command(self, tmp_path):
        r = _run(
            tmp_path,
            ["git reset --hard --reason x;rm -rf var/cache"],
            [_approval("git reset --hard")],
        )
        assert r.returncode == 1

    def test_quoted_reason_cannot_hide_a_second_command(self, tmp_path):
        r = _run(
            tmp_path,
            ['git reset --hard --reason "x" ; rm -rf var/cache'],
            [_approval("git reset --hard")],
        )
        assert r.returncode == 1

    def test_double_quoted_reason_with_spaces_authorizes_the_command(self, tmp_path):
        r = _run(
            tmp_path,
            ['uv run pumpgrok killswitch clear --by human:op --reason "reviewed with operator"'],
            [_approval("killswitch clear", "max_notional_sol=0.2")],
        )
        assert r.returncode == 0, r.stderr

    def test_single_quoted_reason_with_spaces_authorizes_the_command(self, tmp_path):
        r = _run(
            tmp_path,
            ["uv run pumpgrok killswitch clear --by 'human:op' --reason 'reviewed with operator'"],
            [_approval("killswitch clear", "max_notional_sol=0.2")],
        )
        assert r.returncode == 0, r.stderr

    def test_quoted_reason_keeps_the_command_match_exact(self, rollback_gate):
        assert (
            rollback_gate.operation_key('uv run pumpgrok killswitch clear --reason "a b c"')
            == "killswitch clear"
        )
        assert (
            rollback_gate.operation_key('uv run pumpgrok killswitch clear --reason "a" extra')
            != "killswitch clear"
        )
        assert (
            rollback_gate.operation_key('git reset --hard --reason "x" ; rm -rf var/cache')
            != "git reset --hard"
        )


class TestShellExpansionInProvenance:
    def test_exact_receipt_with_command_substitution_in_reason_is_refused(self, tmp_path):
        r = _run(
            tmp_path,
            ['uv run pumpgrok killswitch clear --by human:op --reason "$(rm -rf var/ledger)"'],
            [_approval("killswitch clear", "max_notional_sol=0.2")],
        )
        assert r.returncode == 1
        assert "shell expansion" in r.stderr

    def test_bare_command_substitution_in_reason_is_refused(self, tmp_path):
        r = _run(
            tmp_path,
            ["git reset --hard --reason $(rm)"],
            [_approval("git reset --hard")],
        )
        assert r.returncode == 1
        assert "shell expansion" in r.stderr

    def test_backtick_in_bare_reason_is_refused(self, tmp_path):
        r = _run(
            tmp_path,
            ["git reset --hard --reason `rm`"],
            [_approval("git reset --hard")],
        )
        assert r.returncode == 1
        assert "shell expansion" in r.stderr

    def test_backtick_in_double_quoted_reason_is_refused(self, tmp_path):
        r = _run(
            tmp_path,
            ['git reset --hard --reason "`rm -rf var`"'],
            [_approval("git reset --hard")],
        )
        assert r.returncode == 1
        assert "shell expansion" in r.stderr

    def test_quoted_then_bare_substitution_is_refused(self, tmp_path):
        r = _run(
            tmp_path,
            ["git reset --hard --reason 'a'$(rm)"],
            [_approval("git reset --hard")],
        )
        assert r.returncode == 1
        assert "shell expansion" in r.stderr

    def test_plain_double_quoted_reason_with_spaces_still_authorizes(self, tmp_path):
        r = _run(
            tmp_path,
            ['uv run pumpgrok killswitch clear --by human:op --reason "reviewed with operator"'],
            [_approval("killswitch clear", "max_notional_sol=0.2")],
        )
        assert r.returncode == 0, r.stderr

    def test_single_quoted_literal_substitution_still_authorizes(self, tmp_path):
        r = _run(
            tmp_path,
            ["uv run pumpgrok killswitch clear --by human:op --reason '$(x)'"],
            [_approval("killswitch clear", "max_notional_sol=0.2")],
        )
        assert r.returncode == 0, r.stderr
