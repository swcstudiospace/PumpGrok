"""HOST-01: absolute state directory, all runtime paths resolve under it."""

from __future__ import annotations

from pumpgrok.config.settings import (
    collect_startup_problems,
    resolve_state_path,
    state_root,
)


def test_relative_state_dir_refused_at_startup() -> None:
    problems = collect_startup_problems({"PUMPGROK_STATE_DIR": "var/state"})
    assert any("PUMPGROK_STATE_DIR" in p for p in problems)


def test_empty_state_dir_refused_at_startup() -> None:
    problems = collect_startup_problems({"PUMPGROK_STATE_DIR": "  "})
    assert any("PUMPGROK_STATE_DIR" in p for p in problems)


def test_absolute_state_dir_accepted() -> None:
    problems = collect_startup_problems({"PUMPGROK_STATE_DIR": "/srv/pumpgrok/state"})
    assert not any("PUMPGROK_STATE_DIR" in p for p in problems)


def test_runtime_paths_resolve_under_root() -> None:
    env = {"PUMPGROK_STATE_DIR": "/srv/pumpgrok/state"}
    assert state_root(env) is not None
    for rel in ("var/ledger.sqlite", "var/desk", "var/replay", "var/reputation.json"):
        resolved = resolve_state_path(rel, environ=env)
        assert str(resolved).startswith("/srv/pumpgrok/state/"), resolved
        assert ".." not in resolved.name


def test_unset_root_keeps_relative_defaults() -> None:
    assert state_root({}) is None
    assert str(resolve_state_path("var/ledger.sqlite", environ={})) == "var/ledger.sqlite"
