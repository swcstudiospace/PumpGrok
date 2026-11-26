<<<<<<< HEAD
"""Paper never reads the wallet field."""

from pumpgrok.onboarding.doctor_report import doctor_records


def test_wallet_is_not_read_in_paper() -> None:
    records = doctor_records({"PUMPGROK_WALLET": "anything"}, "paper")
    by_name = {record.name: record for record in records}
    assert by_name["wallet_public_address"].status == "not-read"


def test_wallet_is_required_in_live() -> None:
    records = doctor_records({}, "live")
    by_name = {record.name: record for record in records}
    assert by_name["wallet_public_address"].required_for_mode
    assert by_name["wallet_public_address"].status == "missing"
=======
"""ONB-07: paper needs no wallet, so the wallet input is never read on the paper path.

A paper start with no address, or with a malformed one, is not blocked by the wallet. The
sentinel below records every call into the wallet validators; the paper tests fail if any
call happens. Live still validates the wallet input.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config import settings as settings_mod
from pumpgrok.config.sections import core as core_mod
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools import ensure_paper_genesis

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")

# Malformed on purpose: '0', 'O', 'I' and 'l' are outside the base58 alphabet.
MALFORMED_ENTRY = "0OIl"
MALFORMED_ALLOWLIST_ENV = f'["{MALFORMED_ENTRY}"]'
MALFORMED_SECTION_ENV = "{not json"


AUTHORITY_AT = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _record_complete_authority() -> None:
    """Real operator authority for every seat, recorded as the onboarding verbs record it.

    The paper genesis is written first, as ``_record_tool`` does, then the operator key and an
    allow per roster tool. Each allow is an HMAC-authenticated protected record bound to a
    ConfigChanged row in the paper ledger, the same records the startup gate reads.
    """
    oc.init_key(oc.OPERATOR_DIR)
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        ensure_paper_genesis(store, settings_mod.load_settings(mode="paper").risk)
        for seat in EXPECTED_SEAT_IDS:
            for tool in sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat)):
                oc.record_tool_choice(
                    store,
                    seat=seat,
                    tool=tool,
                    decision="allow",
                    now=AUTHORITY_AT,
                    operator_dir=oc.OPERATOR_DIR,
                )
    finally:
        store.close()


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def wallet_sentinel(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple]]:
    """Fail the test if any wallet validator runs; keep a record for assertions."""
    calls: list[tuple] = []

    def boom(*args: object, **kwargs: object) -> None:
        calls.append(args)
        raise AssertionError("wallet input was read")

    for name in ("_base58_decode", "_is_public_key_text", "decode_public_point"):
        monkeypatch.setattr(core_mod, name, boom, raising=False)
    yield calls


def _toml(tmp_path: Path, body: str) -> str:
    path = tmp_path / "operator.toml"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_paper_default_ignores_malformed_wallet_env(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, wallet_sentinel: list[tuple]
) -> None:
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", MALFORMED_ALLOWLIST_ENV)
    settings = settings_mod.load_settings()
    assert settings.effective_mode == "paper"
    assert settings.wallet.allowlist == ()
    assert wallet_sentinel == []


@pytest.mark.parametrize(
    "setup",
    ["wallet_env_key", "wallet_env_section", "toml_wallet", "init_wallet"],
)
def test_paper_ignores_every_wallet_input_form(
    setup: str,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    wallet_sentinel: list[tuple],
) -> None:
    kwargs: dict[str, object] = {}
    if setup == "wallet_env_key":
        monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", MALFORMED_ALLOWLIST_ENV)
    elif setup == "wallet_env_section":
        monkeypatch.setenv("PUMPGROK_WALLET", MALFORMED_SECTION_ENV)
    elif setup == "toml_wallet":
        monkeypatch.setenv(
            "PUMPGROK_CONFIG", _toml(tmp_path, f'[wallet]\nallowlist = ["{MALFORMED_ENTRY}"]\n')
        )
    else:
        kwargs = {"wallet": {"allowlist": [MALFORMED_ENTRY]}}
    settings = settings_mod.load_settings(mode="paper", **kwargs)
    assert settings.effective_mode == "paper"
    assert settings.wallet.allowlist == ()
    assert wallet_sentinel == []


def test_paper_run_starts_with_malformed_wallet_env(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", MALFORMED_ALLOWLIST_ENV)
    monkeypatch.chdir(tmp_path)
    _record_complete_authority()
    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0
    out, err = capsys.readouterr()
    assert MALFORMED_ENTRY not in out + err


def test_paper_with_explicit_mode_source_ignores_wallet(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, wallet_sentinel: list[tuple]
) -> None:
    monkeypatch.setenv("PUMPGROK_MODE", "paper")
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", MALFORMED_ALLOWLIST_ENV)
    assert settings_mod.load_settings().effective_mode == "paper"
    assert wallet_sentinel == []


def test_unresolvable_mode_fails_closed_and_validates_wallet(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, wallet_sentinel: list[tuple]
) -> None:
    """A mode that cannot be resolved is never treated as paper: wallet input is validated."""
    monkeypatch.setenv("PUMPGROK_MODE", "bogus")
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", MALFORMED_ALLOWLIST_ENV)
    with pytest.raises(settings_mod.ConfigError):
        settings_mod.load_settings()
    assert wallet_sentinel


def test_live_still_validates_wallet_input(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, wallet_sentinel: list[tuple]
) -> None:
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", MALFORMED_ALLOWLIST_ENV)
    with pytest.raises(settings_mod.ConfigError) as excinfo:
        settings_mod.load_settings()
    assert wallet_sentinel, "live must validate the wallet input"
    assert MALFORMED_ENTRY not in str(excinfo.value)


@pytest.mark.parametrize(
    ("init_mode", "env_mode", "toml", "expected"),
    [
        (None, None, None, "paper"),
        (None, "live", None, "live"),
        ("paper", "live", None, "paper"),
        (None, None, '[execution]\nmode = "live"\n', "live"),
        (None, "paper", '[execution]\nmode = "live"\n', "paper"),
        (None, None, 'mode = "live"\n', "live"),
    ],
)
def test_mode_is_resolved_before_wallet_and_agrees_with_settings(
    init_mode: str | None,
    env_mode: str | None,
    toml: str | None,
    expected: str,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if env_mode is not None:
        monkeypatch.setenv("PUMPGROK_MODE", env_mode)
    if toml is not None:
        monkeypatch.setenv("PUMPGROK_CONFIG", _toml(tmp_path, toml))
    kwargs = {} if init_mode is None else {"mode": init_mode}
    assert settings_mod.resolve_effective_mode(**kwargs) == expected
    assert settings_mod.load_settings(**kwargs).effective_mode == expected


def test_paper_settings_section_is_default_not_parsed(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, wallet_sentinel: list[tuple]
) -> None:
    """The paper wallet is the default section; nothing from the environment is parsed into it."""
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", MALFORMED_ALLOWLIST_ENV)
    settings = settings_mod.load_settings()
    assert settings.wallet == settings_mod.WalletSettings()
    assert wallet_sentinel == []
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
