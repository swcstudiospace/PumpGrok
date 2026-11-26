<<<<<<< HEAD
"""Empty x.ai key counts as missing; no empty-bearer request is sent."""

from pumpgrok.onboarding.doctor_report import doctor_records, failing_records


def test_empty_key_is_missing() -> None:
    records = doctor_records({"PUMPGROK_GROK__API_KEY": ""}, "paper")
    by_name = {record.name: record for record in records}
    assert by_name["xai_api_key"].status == "missing"
    assert failing_records(records)


def test_present_key_satisfies() -> None:
    records = doctor_records({"PUMPGROK_GROK__API_KEY": "x"}, "paper")
    by_name = {record.name: record for record in records}
    assert by_name["xai_api_key"].status == "present"
=======
"""An enabled Grok seat needs a nonempty x.ai key, checked at paper startup before any supervisor.

With the Grok gateway disabled the key stays optional. With it enabled, an empty or unset key is
refused and named, never echoed, and the startup spy is never reached.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pumpgrok.cli import verbs_state
from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_OK
from pumpgrok.cli.dispatch import main
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger import operator_choices as oc

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")
GATEWAY_ENV = "PUMPGROK_GROK_GATEWAY__ENABLED"
KEY_ENV = "PUMPGROK_GROK__API_KEY"


@pytest.fixture(autouse=True)
def clean_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Own working directory and a PUMPGROK_*-free environment for every test."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PUMPGROK_"):
            monkeypatch.delenv(name)
    yield


@pytest.fixture
def startup_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Path]]:
    calls: list[tuple[str, Path]] = []

    def fake_once(source: Path, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
        calls.append(("once", Path(source)))
        return SimpleNamespace(decision="no_trade", reason="spy", trades=())

    monkeypatch.setattr(verbs_state, "run_once_replay", fake_once)
    return calls


@pytest.fixture
def complete_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    decisions: dict[str, oc.Decision] = {}
    for seat in EXPECTED_SEAT_IDS:
        for tool in roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat):
            scope = oc.tool_scope(seat, tool)
            decisions[scope] = oc.Decision(
                scope=scope,
                decision="allow",
                by="human:operator",
                digest="digest",
                idempotency_key="key",
                payload={},
                bound=True,
            )
    monkeypatch.setattr(oc, "read_authority", lambda *_a, **_k: decisions)


def _run_once(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = main(["run", "--mode", "paper", "--once", "--replay", SMOKE])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_enabled_grok_seat_with_empty_xai_key_is_refused_at_startup(
    startup_spy: list[tuple[str, Path]],
    complete_authority: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(GATEWAY_ENV, "true")
    monkeypatch.setenv(KEY_ENV, "")
    code, text = _run_once(capsys)
    assert code == EXIT_CONFIG
    assert "xai_api_key: missing" in text
    assert startup_spy == [], "a supervisor started with an empty x.ai key"


def test_enabled_grok_seat_with_unset_xai_key_is_refused_at_startup(
    startup_spy: list[tuple[str, Path]],
    complete_authority: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(GATEWAY_ENV, "true")
    code, text = _run_once(capsys)
    assert code == EXIT_CONFIG
    assert "xai_api_key: missing" in text
    assert startup_spy == []


def test_missing_xai_key_and_missing_authority_are_listed_together(
    startup_spy: list[tuple[str, Path]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(GATEWAY_ENV, "true")
    monkeypatch.setenv(KEY_ENV, "")
    code, text = _run_once(capsys)
    assert code == EXIT_CONFIG
    assert "xai_api_key: missing" in text
    assert "seat_tool_access: missing" in text
    assert startup_spy == []


def test_enabled_grok_seat_with_a_key_passes_the_gate(
    startup_spy: list[tuple[str, Path]],
    complete_authority: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(GATEWAY_ENV, "true")
    monkeypatch.setenv(KEY_ENV, "xai-gate-test-key-present")
    code, text = _run_once(capsys)
    assert code == EXIT_OK, text
    assert startup_spy == [("once", Path(SMOKE))]


def test_disabled_grok_seat_does_not_require_an_xai_key(
    startup_spy: list[tuple[str, Path]],
    complete_authority: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, text = _run_once(capsys)
    assert code == EXIT_OK, text
    assert startup_spy == [("once", Path(SMOKE))]
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
