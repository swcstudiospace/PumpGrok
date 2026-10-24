"""Behavioural tests for check_rollback pattern matching (G-5 deployments, G-6 destructive ops)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

GATES = Path(__file__).resolve().parents[1] / "gates"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, GATES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rollback_gate():
    return _load("check_rollback")


def _commands(*cmds: str) -> list[dict]:
    return [{"cmd": cmd, "exit_code": 0} for cmd in cmds]


@pytest.mark.parametrize(
    "cmd",
    [
        "psql -c 'drop table users'",
        "sqlite3 db.sqlite 'Drop Table orders'",
        "psql -c 'drop database staging'",
    ],
)
def test_lowercase_or_mixed_case_drop_is_flagged(rollback_gate, cmd):
    actions, _problems = rollback_gate.check_destructive(_commands(cmd), [])
    assert actions, f"destructive drop not flagged: {cmd!r}"


@pytest.mark.parametrize(
    "cmd",
    [
        "pumpgrok run --mode=live",
        "pumpgrok run --mode live",
        "PUMPGROK RUN --MODE=LIVE",
    ],
)
def test_live_mode_is_flagged_as_deployment(rollback_gate, cmd):
    deploys, _ = rollback_gate.check_deployments(_commands(cmd), {})
    assert deploys, f"live deployment not flagged: {cmd!r}"


def test_paper_mode_is_not_flagged_as_deployment(rollback_gate):
    deploys, _ = rollback_gate.check_deployments(_commands("pumpgrok run --mode=paper"), {})
    assert deploys == []
