"""Secret boundary at paper startup: a sentinel secret never reaches stdout, stderr, logs or disk.

Each run plants sentinel values in the environment, then scans captured stdout and stderr, the
log records and every file the run left in its working directory, including the ledger when one
exists. The sentinels are checked on both the refused and the passed start.
"""

from __future__ import annotations

import logging
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
XAI_SENTINEL = "xai-sentinel-no-echo-5c1e9a"
HMAC_SENTINEL = "hmac-sentinel-no-echo-88d2f0"
WALLET_SENTINEL = "wallet-sentinel-no-echo-4b7a13"


@pytest.fixture(autouse=True)
def clean_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PUMPGROK_"):
            monkeypatch.delenv(name)
    yield


@pytest.fixture
def startup_spy(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    calls: list[Path] = []

    def fake_once(source: Path, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
        calls.append(Path(source))
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


def _every_file_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def _assert_no_sentinel(
    sentinels: tuple[str, ...],
    captured: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    root: Path,
) -> None:
    streams = captured.out + captured.err + caplog.text
    for sentinel in sentinels:
        assert sentinel not in streams, f"secret reached stdout, stderr or logs: {sentinel[:6]}"
        for name, data in _every_file_bytes(root).items():
            assert sentinel.encode() not in data, f"secret persisted in {name}"


def test_refused_start_never_echoes_the_xai_key(
    startup_spy: list[Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("PUMPGROK_GROK_GATEWAY__ENABLED", "true")
    monkeypatch.setenv("PUMPGROK_GROK__API_KEY", XAI_SENTINEL)
    code = main(["run", "--mode", "paper", "--once", "--replay", SMOKE])
    captured = capsys.readouterr()
    assert code == EXIT_CONFIG
    assert startup_spy == []
    _assert_no_sentinel((XAI_SENTINEL,), captured, caplog, tmp_path)


def test_passed_start_never_echoes_any_secret(
    startup_spy: list[Path],
    complete_authority: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("PUMPGROK_GROK_GATEWAY__ENABLED", "true")
    monkeypatch.setenv("PUMPGROK_GROK__API_KEY", XAI_SENTINEL)
    monkeypatch.setenv("PUMPGROK_CONFIRMATION_KEY", HMAC_SENTINEL)
    code = main(["run", "--mode", "paper", "--once", "--replay", SMOKE])
    captured = capsys.readouterr()
    assert code == EXIT_OK, captured.err
    assert startup_spy == [Path(SMOKE)]
    _assert_no_sentinel((XAI_SENTINEL, HMAC_SENTINEL), captured, caplog, tmp_path)


def test_paper_wallet_input_is_never_echoed_or_read(
    startup_spy: list[Path],
    complete_authority: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", f'["{WALLET_SENTINEL}"]')
    code = main(["run", "--mode", "paper", "--once", "--replay", SMOKE])
    captured = capsys.readouterr()
    assert code == EXIT_OK, captured.err
    assert startup_spy == [Path(SMOKE)]
    _assert_no_sentinel((WALLET_SENTINEL,), captured, caplog, tmp_path)
