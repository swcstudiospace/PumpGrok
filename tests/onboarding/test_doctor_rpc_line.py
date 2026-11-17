"""ONB-08 doctor line: default versus explicit RPC, from ``operator_choices.rpc_status``.

A default is never a recorded choice. An explicit choice shows only scheme, host and port.
Anything the ledger or the operator key cannot vouch for is a warning, never an ok line.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.config.settings import load_settings
from pumpgrok.doctor import doctor_report
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.store import LedgerStore

LEDGER = Path("var") / "ledger.sqlite"
OPERATOR = Path("var") / "operator"
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test runs in its own working directory, so var/ never touches the repo."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _onb08() -> str:
    lines = doctor_report(load_settings())
    matches = [line for line in lines if "ONB-08" in line]
    assert len(matches) == 1, lines
    assert lines[-1].startswith("doctor:"), lines[-1]
    return matches[0]


def _record_rpc(url: str) -> None:
    store = LedgerStore(LEDGER)
    try:
        oc.record_rpc_choice(
            store,
            url=url,
            configured_urls=[DEFAULT_RPC],
            operator_dir=OPERATOR,
            now=NOW,
        )
    finally:
        store.close()


def test_fresh_install_reports_default_without_creating_authority() -> None:
    line = _onb08()
    assert line.startswith("ok"), line
    assert "rpc=default" in line
    assert not OPERATOR.exists()
    assert not LEDGER.exists()


def test_key_without_choices_reports_default() -> None:
    oc.init_key(OPERATOR)
    line = _onb08()
    assert line.startswith("ok"), line
    assert "rpc=default" in line


def test_authenticated_explicit_choice_reports_endpoint_without_secrets() -> None:
    oc.init_key(OPERATOR)
    secret_url = "https://user:hunter2@api.mainnet-beta.solana.com:443/v1?api-key=sekrit#top"
    _record_rpc(secret_url)

    line = _onb08()
    assert line.startswith("ok"), line
    assert "rpc=explicit" in line
    assert "endpoint=https://api.mainnet-beta.solana.com:443" in line
    for leaked in ("hunter2", "sekrit", "user:", "/v1", "api-key", "#top"):
        assert leaked not in line


def test_choice_not_bound_to_the_ledger_is_a_warning() -> None:
    oc.init_key(OPERATOR)
    _record_rpc(DEFAULT_RPC)
    LEDGER.unlink()  # the protected record no longer matches any ledger row

    line = _onb08()
    assert line.startswith("warn"), line
    assert "rpc=unbound" in line
    assert "rpc=explicit" not in line


def test_corrupt_choices_file_is_a_warning_not_a_default() -> None:
    oc.init_key(OPERATOR)
    (OPERATOR / oc.CHOICES_NAME).write_text("not a protected record\n", encoding="utf-8")

    line = _onb08()
    assert line.startswith("warn"), line
    assert "rpc=unavailable" in line


def test_deleted_key_with_choices_on_disk_is_a_warning_not_a_default() -> None:
    oc.init_key(OPERATOR)
    _record_rpc(DEFAULT_RPC)
    (OPERATOR / oc.KEY_NAME).unlink()

    line = _onb08()
    assert line.startswith("warn"), line
    assert "rpc=unavailable" in line
    assert "rpc=default" not in line
