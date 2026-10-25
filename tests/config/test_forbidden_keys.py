"""Refusal slice: forbidden names, unknown keys, key-bearing URLs, bad types."""

from __future__ import annotations

import os

import pytest

from pumpgrok.config.settings import ConfigError, load_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "name",
    [
        "PRIVATE_KEY",
        "WALLET_SECRET",
        "MY_MNEMONIC_BACKUP",
        "phantom_url",
        "PUMPGROK_SOLANA__SECRET_KEY",  # pragma: allowlist secret: forbidden env-name fixture
        "PUMPGROK_KEYPAIR_PATH",  # pragma: allowlist secret: forbidden env-name fixture
    ],
)
def test_forbidden_env_name_refuses_without_value(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    planted = "PLANTED-SECRET-9f3k7z-no-echo"  # pragma: allowlist secret: planted no-echo value
    monkeypatch.setenv(name, planted)
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    assert name in message
    assert planted not in message


def test_replay_seed_exempt(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_REPLAY__SEED", "7")
    assert load_settings().replay.seed == 7


@pytest.mark.parametrize("name", ["PUMPGROK_BOGUS", "PUMPGROK_RISK__BOGUS"])
def test_unknown_key_refuses_by_name(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "1")
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert name in str(excinfo.value)


def test_execution_mode_env_refused(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_EXECUTION__MODE", "live")
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "PUMPGROK_EXECUTION__MODE" in str(excinfo.value)


@pytest.mark.parametrize(
    "planted_value",
    [
        "https://hooks.example/notify?api-key=PLANTED-KEY-aaa111",
        "https://hooks.example/notify?key=PLANTED-KEY-bbb222",
        "https://hooks.example/notify?token=PLANTED-KEY-ccc333",
        "https://hooks.example/notify?api_key=PLANTED-KEY-ddd444",
        "https://hooks.example/notify?apikey=PLANTED-KEY-eee555",
        "https://hooks.example/notify?ref=1&secret=PLANTED-KEY-fff666",
    ],
)
def test_key_bearing_url_refuses_without_echo(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, planted_value: str
) -> None:
    monkeypatch.setenv("PUMPGROK_ALERTS__WEBHOOK_URL", planted_value)
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    assert "PUMPGROK_ALERTS__WEBHOOK_URL" in message
    assert planted_value not in message
    assert "PLANTED-KEY" not in message


@pytest.mark.parametrize(
    ("name", "value", "field"),
    [
        ("PUMPGROK_GROK__BASE_URL", "http://api.example.test/v1", "grok.base_url"),
        ("PUMPGROK_DATA__REST_URL", "http://frontend.example.test", "data.rest_url"),
        ("PUMPGROK_DATA__WS_URL", "ws://feed.example.test/api", "data.ws_url"),
        ("PUMPGROK_JUPITER__QUOTE_URL", "http://quote.example.test/order", "jupiter.quote_url"),
        ("PUMPGROK_RPC__ENDPOINTS", '["http://rpc.example.test"]', "rpc.endpoints"),
    ],
)
def test_plaintext_endpoint_refused_by_field(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, name: str, value: str, field: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    assert field in message
    assert value not in message


def test_bad_type_reports_loc_and_type_only(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUMPGROK_RISK__MAX_TRADE_FRACTION", "not-a-number-zzz")
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    assert "risk.max_trade_fraction" in message
    assert "not-a-number-zzz" not in message
