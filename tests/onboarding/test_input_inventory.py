"""ONB-01: the onboarding inventory per mode, pinned as a snapshot, with presence and source only.

Policy-supported cells are fixed: paper never reads the wallet; an enabled Grok seat needs a
nonempty x.ai key; live forbids the HMAC confirmation key; roster tool choices need an
authenticated explicit decision; an unselected RPC is a default, not consent.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.config.settings import load_settings
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.doctor import INPUT_NAMES, InputRecord, failing_inputs, input_inventory
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# RFC 8032 section 7.1, TEST 1 public key: a valid Ed25519 point.
RFC8032_TEST1_PUBLIC = bytes.fromhex(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)

EXPECTED_MATRIX: dict[str, dict[str, str]] = {
    "paper": {
        "xai_api_key": "optional",
        "wallet_public_address": "not-read",
        "rpc_endpoint": "optional",
        "seat_tool_access": "required",
        "hmac_confirmation_key": "optional",
    },
    "live": {
        "xai_api_key": "optional",
        "wallet_public_address": "required",
        "rpc_endpoint": "required",
        "seat_tool_access": "required",
        "hmac_confirmation_key": "forbidden",
    },
}


def _b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    digits = ""
    while number:
        number, remainder = divmod(number, 58)
        digits = _B58[remainder] + digits
    leading_zeros = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * leading_zeros + digits


VALID_ADDRESS = _b58encode(RFC8032_TEST1_PUBLIC)


class _RecordingEnv(Mapping[str, str]):
    """Environment stand-in that records every key looked up or tested."""

    def __init__(self, data: Mapping[str, str]) -> None:
        self._data = dict(data)
        self.touched: list[str] = []

    def __getitem__(self, key: str) -> str:
        self.touched.append(key)
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        self.touched.append(str(key))
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


@pytest.fixture(autouse=True)
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Own working directory and a PUMPGROK_*-free environment for every test."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PUMPGROK_"):
            monkeypatch.delenv(name)
    return tmp_path


def _by_name(records: list[InputRecord]) -> dict[str, InputRecord]:
    return {record.name: record for record in records}


def _record_rpc_default_url() -> None:
    oc.init_key(oc.OPERATOR_DIR)
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        oc.record_rpc_choice(
            store,
            url=DEFAULT_RPC,
            configured_urls=[DEFAULT_RPC],
            operator_dir=oc.OPERATOR_DIR,
            now=NOW,
        )
    finally:
        store.close()


def _complete_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every roster tool allowed and an explicit RPC choice, as the authority would report."""
    endpoint = oc.Endpoint("https", "api.mainnet-beta.solana.com", 443)
    monkeypatch.setattr(oc, "rpc_status", lambda *_a, **_k: ("explicit", endpoint))
    decisions: dict[str, Any] = {}
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


def test_input_names_are_the_policy_inputs_in_order() -> None:
    assert INPUT_NAMES == (
        "xai_api_key",
        "wallet_public_address",
        "rpc_endpoint",
        "seat_tool_access",
        "hmac_confirmation_key",
    )


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_inventory_snapshot_pins_required_for_mode(mode: str) -> None:
    records = input_inventory(load_settings(mode=mode), mode)
    assert [record.name for record in records] == list(INPUT_NAMES)
    assert {record.name: record.required_for_mode for record in records} == EXPECTED_MATRIX[mode]


def test_grok_key_is_required_only_when_a_grok_seat_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disabled = _by_name(input_inventory(load_settings(mode="paper"), "paper"))
    assert disabled["xai_api_key"].required_for_mode == "optional"
    monkeypatch.setenv("PUMPGROK_GROK_GATEWAY__ENABLED", "true")
    for mode in ("paper", "live"):
        enabled = _by_name(input_inventory(load_settings(mode=mode), mode))
        assert enabled["xai_api_key"].required_for_mode == "required"


def test_empty_grok_key_counts_as_missing_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_GROK_GATEWAY__ENABLED", "true")
    monkeypatch.setenv("PUMPGROK_GROK__API_KEY", "")
    record = _by_name(input_inventory(load_settings(mode="paper"), "paper"))["xai_api_key"]
    assert (record.status, record.source) == ("missing", "none")
    assert record in failing_inputs(input_inventory(load_settings(mode="paper"), "paper"))


def test_present_grok_key_reports_env_source_and_never_its_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "xai-inventory-sentinel-7f3a"
    monkeypatch.setenv("PUMPGROK_GROK_GATEWAY__ENABLED", "true")
    monkeypatch.setenv("PUMPGROK_GROK__API_KEY", secret)
    records = input_inventory(load_settings(mode="paper"), "paper")
    record = _by_name(records)["xai_api_key"]
    assert (record.status, record.source) == ("present", "env")
    assert secret not in repr(records)


def test_paper_never_reads_the_wallet(monkeypatch: pytest.MonkeyPatch) -> None:
    # Malformed on purpose: paper must neither parse nor look up the wallet input.
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", "not-a-public-key")
    settings = load_settings(mode="paper")
    env = _RecordingEnv(os.environ)
    record = _by_name(input_inventory(settings, "paper", environ=env))["wallet_public_address"]
    assert (record.required_for_mode, record.status, record.source) == (
        "not-read",
        "not-read",
        "none",
    )
    assert [key for key in env.touched if key.startswith("PUMPGROK_WALLET")] == []


def test_live_wallet_is_missing_until_a_valid_public_address_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _by_name(input_inventory(load_settings(mode="live"), "live"))["wallet_public_address"]
    assert (record.required_for_mode, record.status, record.source) == (
        "required",
        "missing",
        "none",
    )
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", json.dumps([VALID_ADDRESS]))
    record = _by_name(input_inventory(load_settings(mode="live"), "live"))["wallet_public_address"]
    assert (record.status, record.source) == ("present", "env")
    assert VALID_ADDRESS not in repr(record)


def test_unselected_rpc_is_a_default_not_consent() -> None:
    paper = _by_name(input_inventory(load_settings(mode="paper"), "paper"))["rpc_endpoint"]
    live = _by_name(input_inventory(load_settings(mode="live"), "live"))["rpc_endpoint"]
    assert (paper.status, paper.source) == ("absent", "default")
    assert (live.status, live.source) == ("missing", "default")


def test_authenticated_rpc_choice_is_present_from_the_ledger() -> None:
    _record_rpc_default_url()
    for mode in ("paper", "live"):
        record = _by_name(input_inventory(load_settings(mode=mode), mode))["rpc_endpoint"]
        assert (record.status, record.source) == ("present", "ledger")


def test_seat_tools_need_a_decision_for_every_roster_tool() -> None:
    oc.init_key(oc.OPERATOR_DIR)
    seat = EXPECTED_SEAT_IDS[0]
    tool = sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat))[0]
    record = _by_name(input_inventory(load_settings(mode="paper"), "paper"))["seat_tool_access"]
    assert (record.status, record.source) == ("missing", "none")
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        oc.record_tool_choice(
            store,
            seat=seat,
            tool=tool,
            decision="allow",
            now=NOW,
            operator_dir=oc.OPERATOR_DIR,
        )
    finally:
        store.close()
    record = _by_name(input_inventory(load_settings(mode="paper"), "paper"))["seat_tool_access"]
    assert (record.status, record.source) == ("missing", "ledger")


def test_complete_paper_and_live_states_have_no_failing_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_authority(monkeypatch)
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", json.dumps([VALID_ADDRESS]))
    paper = input_inventory(load_settings(mode="paper"), "paper")
    live = input_inventory(load_settings(mode="live"), "live")
    assert failing_inputs(paper) == []
    assert failing_inputs(live) == []
    assert _by_name(live)["seat_tool_access"].status == "present"
