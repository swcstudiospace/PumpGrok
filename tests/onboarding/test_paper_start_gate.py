"""Paper startup gate: every missing input is listed before any supervisor starts.

A clean environment refuses the paper start, names each missing input and each seat that lacks
an authenticated decision, and never reaches the startup spy. Complete inputs reach the spy. A
no-replay run that returns not-implemented is never counted as a passed gate. The paper path
never constructs the live gate and never reads the wallet settings.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pumpgrok.cli import verbs_state
from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_NOT_IMPLEMENTED, EXIT_OK
from pumpgrok.cli.dispatch import main
from pumpgrok.config import settings as settings_mod
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")
WALLET_ENTRY = "not-a-public-key-gate-sentinel"
HEALTH_PORT = "18089"


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
    """Replace the supervisor starts. Each entry is one start that reached the supervisor."""
    calls: list[tuple[str, Path]] = []

    def fake_once(source: Path, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
        calls.append(("once", Path(source)))
        return SimpleNamespace(decision="no_trade", reason="spy", trades=())

    async def fake_serve(source: Path, *_args: Any, **_kwargs: Any) -> int:
        calls.append(("serve", Path(source)))
        return EXIT_OK

    monkeypatch.setattr(verbs_state, "run_once_replay", fake_once)
    monkeypatch.setattr(verbs_state, "serve_replay", fake_serve)
    return calls


def _decision(seat: str, tool: str, *, bound: bool) -> oc.Decision:
    return oc.Decision(
        scope=oc.tool_scope(seat, tool),
        decision="allow",
        by="human:operator",
        digest="digest",
        idempotency_key="key",
        payload={},
        bound=bound,
    )


@pytest.fixture
def complete_authority(monkeypatch: pytest.MonkeyPatch) -> dict[str, oc.Decision]:
    """Every roster tool of every seat carries a bound allow decision."""
    decisions: dict[str, oc.Decision] = {}
    for seat in EXPECTED_SEAT_IDS:
        for tool in roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat):
            decisions[oc.tool_scope(seat, tool)] = _decision(seat, tool, bound=True)
    monkeypatch.setattr(oc, "read_authority", lambda *_a, **_k: decisions)
    return decisions


def _run_paper_once(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = main(["run", "--mode", "paper", "--once", "--replay", SMOKE])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _run_paper_serve(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> tuple[int, str]:
    # The continuous desk start is gated; only the `--once --replay`
    # checkpoint bypasses the paper start gate.
    monkeypatch.setenv("PUMPGROK_HEALTH__PORT", HEALTH_PORT)
    code = main(["run", "--mode", "paper", "--serve", "--replay", SMOKE])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_clean_environment_lists_every_missing_input_before_any_start(
    startup_spy: list[tuple[str, Path]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, text = _run_paper_serve(capsys, monkeypatch)
    assert code == EXIT_CONFIG
    assert "seat_tool_access: missing" in text
    for seat in EXPECTED_SEAT_IDS:
        assert seat in text, f"seat {seat} with no authenticated decision was not listed"
    assert startup_spy == [], "a supervisor started with missing inputs"


def test_refusal_names_only_seats_that_lack_an_authenticated_decision(
    startup_spy: list[tuple[str, Path]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    decided, unbound = EXPECTED_SEAT_IDS[0], EXPECTED_SEAT_IDS[1]
    decisions: dict[str, oc.Decision] = {}
    for tool in roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, decided):
        decisions[oc.tool_scope(decided, tool)] = _decision(decided, tool, bound=True)
    for tool in roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, unbound):
        decisions[oc.tool_scope(unbound, tool)] = _decision(unbound, tool, bound=False)
    monkeypatch.setattr(oc, "read_authority", lambda *_a, **_k: decisions)

    code, text = _run_paper_serve(capsys, monkeypatch)
    assert code == EXIT_CONFIG
    assert f"seat {unbound}:" in text, "an unbound decision must not count as authenticated"
    assert f"seat {decided}:" not in text
    assert startup_spy == []


def test_complete_inputs_reach_the_startup_spy(
    startup_spy: list[tuple[str, Path]],
    complete_authority: dict[str, oc.Decision],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, text = _run_paper_once(capsys)
    assert code == EXIT_OK, text
    assert startup_spy == [("once", Path(SMOKE))]


def test_complete_inputs_reach_the_serve_spy(
    startup_spy: list[tuple[str, Path]],
    complete_authority: dict[str, oc.Decision],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PUMPGROK_HEALTH__PORT", HEALTH_PORT)
    code = main(["run", "--mode", "paper", "--serve", "--replay", SMOKE])
    assert code == EXIT_OK, capsys.readouterr().err
    assert startup_spy == [("serve", Path(SMOKE))]


def test_refused_serve_start_never_reaches_the_serve_spy(
    startup_spy: list[tuple[str, Path]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PUMPGROK_HEALTH__PORT", HEALTH_PORT)
    code = main(["run", "--mode", "paper", "--serve", "--replay", SMOKE])
    assert code == EXIT_CONFIG
    assert "seat_tool_access: missing" in capsys.readouterr().err
    assert startup_spy == []


def test_no_replay_run_is_not_counted_as_a_passed_gate(
    startup_spy: list[tuple[str, Path]],
    complete_authority: dict[str, oc.Decision],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["run", "--mode", "paper"])
    capsys.readouterr()
    assert code == EXIT_NOT_IMPLEMENTED
    assert code != EXIT_OK
    assert startup_spy == []


def test_refused_start_writes_nothing_to_disk(
    startup_spy: list[tuple[str, Path]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _text = _run_paper_serve(capsys, monkeypatch)
    assert code == EXIT_CONFIG
    assert not PAPER_LEDGER_PATH.exists()
    assert not (Path("var") / "operator").exists()


def test_paper_start_never_constructs_the_live_gate(
    startup_spy: list[tuple[str, Path]],
    complete_authority: dict[str, oc.Decision],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _forbidden(**_kwargs: Any) -> None:
        raise AssertionError("the live gate was constructed on the paper path")

    monkeypatch.setattr(verbs_state, "LiveGate", _forbidden)
    code, text = _run_paper_once(capsys)
    assert code == EXIT_OK, text
    assert startup_spy == [("once", Path(SMOKE))]


def test_paper_start_never_reads_the_wallet_settings(
    startup_spy: list[tuple[str, Path]],
    complete_authority: dict[str, oc.Decision],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The wallet section is a tripwire: any attribute read on the paper path fails the test."""
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", f'["{WALLET_ENTRY}"]')

    def _tripwire(_self: settings_mod.Settings) -> None:
        raise AssertionError("the paper path read the wallet settings")

    monkeypatch.setattr(settings_mod.Settings, "wallet", property(_tripwire), raising=False)
    code, text = _run_paper_once(capsys)
    assert code == EXIT_OK, text
    assert startup_spy == [("once", Path(SMOKE))]
