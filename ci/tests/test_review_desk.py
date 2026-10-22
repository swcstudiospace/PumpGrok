"""Regression tests for ci/gates/check_desk_integrity.py (review findings 16, 17, 19).

python3 -m pytest ci/tests/test_review_desk.py -q
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

GATES = Path(__file__).resolve().parents[1] / "gates"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_desk_integrity", GATES / "check_desk_integrity.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load()


def _tool(name="desk.state_status", kind="read", gates=None, required=None, properties=None):
    required = list(required or [])
    declared = required if properties is None else list(properties)
    return {
        "name": name,
        "kind": kind,
        "gates": list(gates or []),
        "description": "fixture tool",
        "input": {
            "type": "object",
            "additionalProperties": False,
            "properties": {field: {"type": "string"} for field in declared},
            "required": required,
        },
    }


# ---------------------------------------------------------------------------
# finding 16: unfilled seat placeholders must be reported
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "placeholder",
    [
        "{{DESK_CHANNEL_ID}}",
        "{{SEAT_UUID:bot-01-chief}}",
        "{{SEAT_UUID:bot-08-signal}}",
    ],
)
def test_unfilled_placeholder_in_assembled_prompt_is_reported(tmp_path, placeholder):
    path = tmp_path / "CHIEF.xml"
    path.write_text(f"<prompt>\n  route to {placeholder} now\n</prompt>\n")
    problems = gate.check_assembled_prompt(path)
    assert problems, f"{placeholder} passed the assembled-prompt check"
    assert any(placeholder in p and "line 2" in p for p in problems)


def test_filled_assembled_prompt_passes(tmp_path):
    path = tmp_path / "CHIEF.xml"
    path.write_text("<prompt>\n  route to 3f2a9c1e-0000-4000-8000-000000000001 now\n</prompt>\n")
    assert gate.check_assembled_prompt(path) == []


# ---------------------------------------------------------------------------
# finding 17: hyphenated app names must be accepted when valid
# ---------------------------------------------------------------------------


def _write_pack(tmp_path, doc):
    path = tmp_path / "pack.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return path


def test_hyphenated_app_with_matching_tools_passes(tmp_path):
    path = _write_pack(
        tmp_path,
        {"app": "my-app", "tools": [_tool("my_app_status.read")]},
    )
    assert gate.check_pack(path) == []


def test_hyphenated_app_rejects_tool_without_app_prefix(tmp_path):
    path = _write_pack(
        tmp_path,
        {"app": "my-app", "tools": [_tool("other_status.read")]},
    )
    problems = gate.check_pack(path)
    assert any("not prefixed" in p and "other_status.read" in p for p in problems)


def test_hyphenated_app_rejects_hyphenated_tool_name(tmp_path):
    # Tool names are [a-z][a-z0-9_]* per namespace, so a hyphen can only be
    # normalised in the prefix, never kept in the tool name itself.
    path = _write_pack(
        tmp_path,
        {"app": "my-app", "tools": [_tool("my-app_status.read")]},
    )
    problems = gate.check_pack(path)
    assert any("my-app_status.read" in p and "does not match" in p for p in problems)


def test_plain_app_still_requires_its_prefix(tmp_path):
    path = _write_pack(
        tmp_path,
        {"app": "scout", "tools": [_tool("scout_pulse.read")]},
    )
    assert gate.check_pack(path) == []
    bad = _write_pack(tmp_path, {"app": "scout", "tools": [_tool("pulse.read")]})
    assert any("not prefixed" in p for p in gate.check_pack(bad))


# ---------------------------------------------------------------------------
# finding 19: an approved schema must accept the calls it approves
# ---------------------------------------------------------------------------


def test_required_fields_missing_from_properties_are_refused():
    # additionalProperties: false with required fields that are not declared
    # accepts no call at all: every call that supplies the field is refused.
    tool = _tool(
        "exec.place",
        kind="write",
        gates=["g6"],
        required=["approval_id", "rollback_plan"],
        properties=[],
    )
    problems = gate.check_tool(tool, 0)
    assert any("approval_id" in p and "does not declare" in p for p in problems)
    assert any("rollback_plan" in p and "does not declare" in p for p in problems)


def test_approved_schema_with_declared_required_fields_passes():
    tool = _tool(
        "exec.place",
        kind="write",
        gates=["g6"],
        required=["approval_id", "rollback_plan"],
        properties=["approval_id", "rollback_plan", "symbol"],
    )
    assert gate.check_tool(tool, 0) == []


def test_undeclared_required_field_is_refused_without_a_gate():
    tool = _tool("journal.append", kind="write", gates=[], required=["body"], properties=[])
    problems = gate.check_tool(tool, 0)
    assert any("'body'" in p and "does not declare" in p for p in problems)


def test_non_string_required_entry_is_reported_not_raised():
    tool = _tool("journal.append", kind="write", gates=[], required=[], properties=[])
    tool["input"]["required"] = [["nested"]]
    problems = gate.check_tool(tool, 0)
    assert problems, "a non-string required entry must be reported"
