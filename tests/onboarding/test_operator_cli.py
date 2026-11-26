"""`pumpgrok onboarding` workflow: only an interactive operator-account terminal records choices.

Each refusal asserts that nothing was written and that no key material reached stdout or stderr.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pumpgrok.cli import EXIT_CONFIG, EXIT_OK, main
from pumpgrok.cli import onboarding as onboarding_cli
from pumpgrok.core.manifests import roster_tool_names
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.store import LedgerStore

REPO_ROSTERS = Path(__file__).resolve().parents[2] / "contracts" / "tool-rosters"
SEAT = "bot-01-scout"
LEDGER = Path("var") / "ledger.sqlite"
CHOICES = Path("var") / "operator" / oc.CHOICES_NAME
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"


@pytest.fixture
def operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    oc.init_key(Path("var") / "operator")
    return tmp_path


def _tool() -> str:
    return sorted(roster_tool_names(REPO_ROSTERS, SEAT))[0]


def _terminal(monkeypatch: pytest.MonkeyPatch, typed: str | None = None) -> None:
    """Simulate an operator terminal that types `typed` at the confirmation prompt."""
    monkeypatch.setattr(onboarding_cli, "_stdio_is_interactive", lambda: True)
    if typed is not None:
        monkeypatch.setattr("builtins.input", lambda _prompt="": typed)


def _no_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(onboarding_cli, "_stdio_is_interactive", lambda: False)


def _key_text() -> str:
    return (Path("var") / "operator" / oc.KEY_NAME).read_text(encoding="utf-8")


def _assert_nothing_written() -> None:
    assert not LEDGER.exists()
    assert not CHOICES.exists()


def _config_rows() -> list[dict]:
    store = LedgerStore(LEDGER)
    try:
        return store.read(types=["ConfigChanged"], limit=None)
    finally:
        store.close()


def _list(capsys: pytest.CaptureFixture[str]) -> dict:
    capsys.readouterr()  # discard output of earlier commands
    assert main(["onboarding", "list"]) == EXIT_OK
    return json.loads(capsys.readouterr().out)


def test_noninteractive_access_is_refused_and_writes_nothing(
    operator_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _no_terminal(monkeypatch)
    code = main(["onboarding", "access", "--seat", SEAT, "--tool", _tool(), "--allow"])
    captured = capsys.readouterr()
    assert code == EXIT_CONFIG
    assert "interactive terminal" in captured.err
    assert _key_text() not in captured.out + captured.err
    _assert_nothing_written()


def test_access_without_an_operator_key_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _terminal(monkeypatch, typed=f"allow {SEAT} {_tool()}")
    code = main(["onboarding", "access", "--seat", SEAT, "--tool", _tool(), "--allow"])
    assert code == EXIT_CONFIG
    assert "unavailable" in capsys.readouterr().err
    _assert_nothing_written()


def test_wrong_confirmation_phrase_is_refused(
    operator_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _terminal(monkeypatch, typed="yes")
    code = main(["onboarding", "access", "--seat", SEAT, "--tool", _tool(), "--allow"])
    assert code == EXIT_CONFIG
    assert "did not match" in capsys.readouterr().err
    _assert_nothing_written()


def test_interactive_operator_grants_revokes_and_lists(
    operator_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tool = _tool()
    key = _key_text()

    before = _list(capsys)
    assert before["authority"] == "ok"
    states = {row["tool"]: row["state"] for row in before["seats"][SEAT]}
    assert set(states.values()) == {"not_granted"}
    assert before["rpc"]["status"] == "default"

    _terminal(monkeypatch, typed=f"allow {SEAT} {tool}")
    assert main(["onboarding", "access", "--seat", SEAT, "--tool", tool, "--allow"]) == EXIT_OK
    granted = {row["tool"]: row["state"] for row in _list(capsys)["seats"][SEAT]}
    assert granted[tool] == "granted"

    _terminal(monkeypatch, typed=f"revoke {SEAT} {tool}")
    assert main(["onboarding", "revoke", "--seat", SEAT, "--tool", tool]) == EXIT_OK
    revoked = {row["tool"]: row["state"] for row in _list(capsys)["seats"][SEAT]}
    assert revoked[tool] != "granted"

    out_err = capsys.readouterr()
    assert key not in out_err.out + out_err.err


def test_rpc_choice_records_scheme_host_port_only(
    operator_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = "https://user:pw-sentinel@api.mainnet-beta.solana.com/v1/abc?cluster=mainnet#frag"
    _terminal(monkeypatch, typed="rpc https://api.mainnet-beta.solana.com:443")
    assert main(["onboarding", "rpc", "--endpoint", raw]) == EXIT_OK
    capsys.readouterr()

    # A token-bearing flag is refused by the CLI argv policy before anything is written.
    _terminal(monkeypatch, typed="rpc https://api.mainnet-beta.solana.com:443")
    assert (
        main(["onboarding", "rpc", "--endpoint", "https://api.mainnet-beta.solana.com/?token=x"])
        == EXIT_CONFIG
    )
    assert "key-bearing" in capsys.readouterr().err
    assert len(_config_rows()) == 1

    assert main(["onboarding", "rpc"]) == EXIT_OK
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "explicit"
    assert status["endpoint"] == {
        "scheme": "https",
        "host": "api.mainnet-beta.solana.com",
        "port": 443,
    }
    recorded = json.dumps(_config_rows()) + CHOICES.read_text(encoding="utf-8")
    assert "pw-sentinel" not in recorded and "tok-sentinel" not in recorded
    assert len(_config_rows()) == 1


def test_key_creation_needs_a_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _no_terminal(monkeypatch)
    assert main(["onboarding", "init-key"]) == EXIT_CONFIG
    assert not (Path("var") / "operator" / oc.KEY_NAME).exists()

    _terminal(monkeypatch, typed="create operator key")
    assert main(["onboarding", "init-key"]) == EXIT_OK
    key = Path("var") / "operator" / oc.KEY_NAME
    assert key.stat().st_mode & 0o077 == 0
    out_err = capsys.readouterr()
    assert key.read_text(encoding="utf-8") not in out_err.out + out_err.err


def test_module_entrypoint_without_terminal_writes_nothing(tmp_path: Path) -> None:
    """A real subprocess has no terminal on stdin: the agent-style path is refused."""
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pumpgrok.cli import main; sys.exit(main(sys.argv[1:]))",
            "onboarding",
            "access",
            "--seat",
            SEAT,
            "--tool",
            _tool(),
            "--allow",
        ],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == EXIT_CONFIG
    assert "unavailable" in result.stderr or "interactive terminal" in result.stderr
    assert not (tmp_path / "var" / "operator").exists()
