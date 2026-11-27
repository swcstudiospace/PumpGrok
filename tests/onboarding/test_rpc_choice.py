"""ONB-08: an explicit RPC choice records only scheme, host and port; defaults are never choices."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.store import LedgerStore

LEDGER = Path("var") / "ledger.sqlite"
CHOICES = Path("var") / "operator" / oc.CHOICES_NAME
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    oc.init_key(Path("var") / "operator")
    return tmp_path


def _config_rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    store = LedgerStore(LEDGER)
    try:
        return store.read(types=["ConfigChanged"], limit=None)
    finally:
        store.close()


def test_no_recorded_choice_reports_default_and_creates_no_row(operator_home: Path) -> None:
    assert oc.rpc_status(Path("var") / "operator", LEDGER) == ("default", None)
    assert _config_rows() == []
    assert not CHOICES.exists()


def test_explicit_choice_records_only_scheme_host_and_port(operator_home: Path) -> None:
    secret_url = "https://user:hunter2@api.mainnet-beta.solana.com:443/v1/abc?api-key=sekrit#top"
    store = LedgerStore(LEDGER)
    try:
        oc.record_rpc_choice(
            store,
            url=secret_url,
            configured_urls=[DEFAULT_RPC],
            operator_dir=Path("var") / "operator",
            now=NOW,
        )
    finally:
        store.close()

    status, endpoint = oc.rpc_status(Path("var") / "operator", LEDGER)
    assert status == "explicit"
    assert endpoint == oc.Endpoint("https", "api.mainnet-beta.solana.com", 443)

    evidence = json.dumps(_config_rows()) + CHOICES.read_text(encoding="utf-8")
    for leaked in ("hunter2", "sekrit", "user:", "/v1", "api-key", "#top"):
        assert leaked not in evidence


def test_default_port_is_filled_in_and_path_is_dropped() -> None:
    assert oc.canonical_endpoint("https://Example.org/x?y=1") == oc.Endpoint(
        "https", "example.org", 443
    )
    assert oc.canonical_endpoint("http://127.0.0.1:8899/") == oc.Endpoint("http", "127.0.0.1", 8899)
    with pytest.raises(ValueError, match="scheme"):
        oc.canonical_endpoint("ftp://example.org")


def test_endpoint_outside_the_configured_list_is_refused(operator_home: Path) -> None:
    store = LedgerStore(LEDGER)
    try:
        with pytest.raises(oc.OperatorChoiceError, match="not a configured endpoint"):
            oc.record_rpc_choice(
                store,
                url="https://rpc.unlisted.example",
                configured_urls=[DEFAULT_RPC],
                operator_dir=Path("var") / "operator",
                now=NOW,
            )
    finally:
        store.close()
    assert _config_rows() == []
    assert oc.rpc_status(Path("var") / "operator", LEDGER) == ("default", None)


def test_latest_explicit_choice_wins(operator_home: Path) -> None:
    second = "https://solana-rpc.example.net:8443"
    store = LedgerStore(LEDGER)
    try:
        oc.record_rpc_choice(
            store,
            url=DEFAULT_RPC,
            configured_urls=[DEFAULT_RPC, second],
            operator_dir=Path("var") / "operator",
            now=NOW,
        )
        oc.record_rpc_choice(
            store,
            url=second,
            configured_urls=[DEFAULT_RPC, second],
            operator_dir=Path("var") / "operator",
            now=NOW,
        )
    finally:
        store.close()
    assert oc.rpc_status(Path("var") / "operator", LEDGER) == (
        "explicit",
        oc.Endpoint("https", "solana-rpc.example.net", 8443),
    )
