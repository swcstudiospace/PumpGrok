"""Regression tests for the G-2 receipt gate (ci/gates/check_receipt.py).

Covers four review findings:
  - a missing, null, boolean, or non-integer exit code is never evidence;
  - a bypass pattern quoted as the text of a read-only search is not a bypass, while any
    real bypass still is;
  - a path spelled with a final `/.` is a directory requirement, not the bare path;
  - a loop-ack scope must name the receipt's whole ticket id, not a prefix of it.

    python3 -m pytest ci/tests/test_review_receipt.py -q
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

GATES = Path(__file__).resolve().parents[1] / "gates"


def _load_receipt_gate():
    spec = importlib.util.spec_from_file_location("check_receipt", GATES / "check_receipt.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def receipt_gate():
    return _load_receipt_gate()


def _receipt(**overrides) -> dict:
    receipt = {
        "task_id": "PG-1",
        "bot": "bot-04-sniper",
        "approved_by": "bot-02-risk",
        "commands": [{"cmd": "uv run pytest -q", "exit_code": 0, "output_tail": "3 passed"}],
        "claims": [{"claim": "Tests pass", "evidence_command_index": 0}],
        "unverified": ["live RPC behaviour"],
    }
    receipt.update(overrides)
    return receipt


def _ack(scope: str) -> dict:
    return {
        "condition": "brief_degraded",
        "operation": "work ticket",
        "ack_id": "a1",
        "human_granted_by": "Jane Doe",
        "at": "2026-10-21T00:00:00Z",
        "scope": scope,
    }


# ---------------------------------------------------------------------------
# Missing or non-integer exit codes are not evidence
# ---------------------------------------------------------------------------


class TestExitCodeIsEvidence:
    @pytest.mark.parametrize("bad", [None, False, True, "0", "", 0.0])
    def test_non_integer_exit_code_is_refused_for_a_plain_claim(self, receipt_gate, bad):
        receipt = _receipt(commands=[{"cmd": "uv run pytest -q", "exit_code": bad}])
        problems = receipt_gate.check(receipt, "bot-04-sniper")
        assert any("must be an integer" in p for p in problems), problems
        assert any("records no integer exit_code" in p for p in problems), problems

    @pytest.mark.parametrize("bad", [None, False, True, "1"])
    def test_non_integer_exit_code_cannot_satisfy_expects_failure(self, receipt_gate, bad):
        receipt = _receipt(
            commands=[{"cmd": "uv run pytest -q", "exit_code": bad}],
            claims=[
                {
                    "claim": "reproduced the bug",
                    "evidence_command_index": 0,
                    "expects_failure": True,
                }
            ],
        )
        problems = receipt_gate.check(receipt, "bot-04-sniper")
        assert any("records no integer exit_code" in p for p in problems), problems

    def test_null_result_is_not_a_failure_under_strict(self, receipt_gate):
        receipt = _receipt(
            commands=[{"cmd": "uv run pytest -q", "exit_code": None}],
            claims=[
                {
                    "claim": "every test passes",
                    "evidence_command_index": 0,
                    "expects_failure": True,
                }
            ],
        )
        assert receipt_gate.check(receipt, "bot-04-sniper", strict=True)

    @pytest.mark.parametrize("bad", [None, False, True, "0"])
    def test_non_integer_sibling_does_not_corroborate_existence(self, receipt_gate, bad):
        probe = {"cmd": "test -f config.yaml", "exit_code": bad}
        assert receipt_gate._is_positive_existence_check(probe, "config.yaml", "f") is False

    def test_integer_zero_exit_is_still_accepted(self, receipt_gate):
        assert receipt_gate.check(_receipt(), "bot-04-sniper") == []

    def test_integer_zero_sibling_still_corroborates_existence(self, receipt_gate):
        probe = {"cmd": "test -f config.yaml", "exit_code": 0}
        assert receipt_gate._is_positive_existence_check(probe, "config.yaml", "f") is True


# ---------------------------------------------------------------------------
# Quoted search text is not a bypass; executable bypasses still are
# ---------------------------------------------------------------------------


class TestBypassSearchText:
    @pytest.mark.parametrize(
        "cmd",
        [
            'grep -n -- "--no-verify" ci/gates/check_receipt.py',
            'grep -rn "|| true" ci/gates',
            "grep -n '--skip-tests' docs/testing.md",
            'rg "PUMPGROK_LIVE_ENABLE=1" src',
            'grep -c "--i-understand-the-risk" ci/gates/check_receipt.py',
            'git grep -n "--no-gpg-sign" -- ci',
        ],
    )
    def test_quoted_search_for_bypass_text_is_not_a_bypass(self, receipt_gate, cmd):
        receipt = _receipt(
            commands=[{"cmd": cmd, "exit_code": 0, "output_tail": "1:match"}],
            claims=[{"claim": "audited the gate", "evidence_command_index": 0}],
        )
        problems = receipt_gate.check(receipt, "bot-04-sniper")
        assert not any("contains a bypass" in p for p in problems), problems

    @pytest.mark.parametrize(
        "cmd",
        [
            'git commit --no-verify -m "msg"',
            'grep -n "x" ci/gates/check_receipt.py && git commit --no-verify -m "msg"',
            'bash -c "git commit --no-verify -m msg"',
            "sh -c 'grep \"--no-verify\" ci/gates/check_receipt.py'",
            'grep "x" $(git commit --no-verify)',
            'grep "$(git commit --no-verify)" ci/gates/check_receipt.py',
            'grep -q "--no-verify" ci/gates/check_receipt.py `git commit --no-verify`',
            'grep "--no-verify" ci/gates/check_receipt.py && uv run pytest -q || true',
            'grep "x" ci/gates/check_receipt.py; bash -c "uv run pytest -q --co"',
            'grep -n "x" ci/gates/check_receipt.py; echo "--no-verify',
            'grep -n "--no-verify" ci/gates/x.py | sh',
        ],
    )
    def test_executed_bypass_is_still_refused(self, receipt_gate, cmd):
        receipt = _receipt(
            commands=[{"cmd": cmd, "exit_code": 0, "output_tail": "1:match"}],
            claims=[{"claim": "ran", "evidence_command_index": 0}],
        )
        problems = receipt_gate.check(receipt, "bot-04-sniper")
        assert any("contains a bypass" in p for p in problems), problems


# ---------------------------------------------------------------------------
# A final `/.` is a directory requirement, not the bare path
# ---------------------------------------------------------------------------


class TestDotSuffixPaths:
    def test_dot_suffix_is_not_the_bare_path(self, receipt_gate):
        assert receipt_gate._normalize_path("README.md/.", "e") != receipt_gate._normalize_path(
            "README.md", "e"
        )

    def test_dot_suffix_matches_a_trailing_slash_spelling(self, receipt_gate):
        assert receipt_gate._normalize_path("README.md/.", "e") == receipt_gate._normalize_path(
            "README.md/", "e"
        )

    def test_middle_dot_component_still_collapses(self, receipt_gate):
        assert receipt_gate._normalize_path("a/./b", "e") == "a/b"

    def test_regular_file_probe_does_not_corroborate_dot_suffix(self, receipt_gate):
        probe = {"cmd": "test -f README.md", "exit_code": 0}
        assert receipt_gate._is_positive_existence_check(probe, "README.md/.", "e") is False

    def test_directory_probe_still_corroborates_dot_suffix(self, receipt_gate):
        probe = {"cmd": "test -d src", "exit_code": 0}
        assert receipt_gate._is_positive_existence_check(probe, "src/.", "d") is True

    def test_unrun_search_behind_dot_suffix_is_refused_under_strict(self, receipt_gate):
        receipt = _receipt(
            commands=[
                {"cmd": "test -f README.md", "exit_code": 0},
                {
                    "cmd": "test -e README.md/. && grep -q deprecated README.md/.",
                    "exit_code": 1,
                    "output_tail": "",
                },
            ],
            claims=[
                {
                    "claim": "all deprecated tokens removed from README.md",
                    "evidence_command_index": 1,
                    "expects_failure": True,
                }
            ],
        )
        problems = receipt_gate.check(receipt, "bot-04-sniper", strict=True)
        assert any(p.startswith("claim[0]") for p in problems), problems


# ---------------------------------------------------------------------------
# A loop-ack scope names the whole ticket id
# ---------------------------------------------------------------------------


class TestLoopAckScopeMatchesWholeTicket:
    @pytest.mark.parametrize(
        "scope",
        [
            "SPE-180010 only",
            "SPE-18001x",
            "SUB-SPE-18001",
            "SPE-180010 and SPE-18001X",
        ],
    )
    def test_scope_naming_another_ticket_is_refused(self, receipt_gate, scope):
        receipt = _receipt(task_id="SPE-18001", loop_acks=[_ack(scope)])
        problems = receipt_gate.check(receipt, "bot-04-sniper")
        assert any("does not name this receipt's task_id" in p for p in problems), problems

    @pytest.mark.parametrize(
        "scope",
        [
            "SPE-18001 only",
            "task SPE-18001",
            "SPE-180010 and SPE-18001",
            "SPE-18001.",
        ],
    )
    def test_scope_naming_this_ticket_is_accepted(self, receipt_gate, scope):
        receipt = _receipt(task_id="SPE-18001", loop_acks=[_ack(scope)])
        problems = receipt_gate.check(receipt, "bot-04-sniper")
        assert not any("does not name" in p for p in problems), problems

    def test_empty_task_id_names_nothing(self, receipt_gate):
        receipt = _receipt(task_id="", loop_acks=[_ack("task PG-1")])
        problems = receipt_gate.check(receipt, "bot-04-sniper")
        assert any("does not name this receipt's task_id" in p for p in problems), problems

    def test_whole_ticket_helper_matches_only_identifier_boundaries(self, receipt_gate):
        assert receipt_gate._scope_names_task("SPE-18001 only", "SPE-18001") is True
        assert receipt_gate._scope_names_task("SPE-180010 only", "SPE-18001") is False
        assert receipt_gate._scope_names_task("SPE-18001", None) is False


# ---------------------------------------------------------------------------
# A boolean is not a command index
# ---------------------------------------------------------------------------


class TestEvidenceIndexIsAnInteger:
    @pytest.mark.parametrize("bad", [True, False])
    def test_boolean_evidence_index_is_refused(self, receipt_gate, bad):
        receipt = _receipt(
            commands=[
                {"cmd": "uv run pytest -q", "exit_code": 0},
                {"cmd": "uv run ruff check", "exit_code": 1},
            ],
            claims=[{"claim": "tests pass", "evidence_command_index": bad}],
        )
        problems = receipt_gate.check(receipt, "bot-04-sniper")
        assert any("which does not exist" in p for p in problems), problems

    def test_real_integer_index_still_works(self, receipt_gate):
        receipt = _receipt(
            commands=[
                {"cmd": "uv run pytest -q", "exit_code": 0, "output_tail": "3 passed"},
                {"cmd": "uv run ruff check", "exit_code": 1},
            ],
            claims=[{"claim": "tests pass", "evidence_command_index": 0}],
        )
        assert receipt_gate.check(receipt, "bot-04-sniper") == []
