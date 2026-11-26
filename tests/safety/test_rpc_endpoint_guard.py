"""Outbound URL settings refuse a credential carried in the URL; clean TLS endpoints pass.

A value that stands in for a credential must never appear in the error text, so every refusal
is asserted against the synthetic secret below.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pumpgrok.config.settings import ConfigError, DataSettings, GrokSettings, RpcSettings

# Synthetic stand-ins: never provider keys. They must not appear in any refusal message.
SECRET = "synthetic-key-7f3a9c2e1b8d"  # pragma: allowlist secret: synthetic  # gitleaks:allow
OPAQUE_TOKEN = "abcdef0123456789abcdef0123456789"  # gitleaks:allow

CLEAN_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",
    "https://rpc.example.org/",
    "https://rpc.example.org/v1?commitment=finalized",
    "https://rpc.example.org/tokenizer?monkey=banana",
    "wss://rpc.example.org/ws",
]


@pytest.mark.parametrize(
    "endpoint",
    [
        f"https://user:{SECRET}@rpc.example.org",
        f"https://{SECRET}@rpc.example.org",
    ],
)
def test_userinfo_endpoint_is_refused_without_echoing_the_secret(endpoint: str) -> None:
    with pytest.raises(ConfigError) as refused:
        RpcSettings(endpoints=[endpoint])
    assert SECRET not in str(refused.value)
    assert "rpc.endpoints" in str(refused.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        f"https://rpc.example.org/{OPAQUE_TOKEN}",
        f"https://rpc.example.org/v2/{OPAQUE_TOKEN}/",
        f"https://rpc.example.org/?api-key={SECRET}",
        f"https://rpc.example.org/?apikey={SECRET}",
        f"https://rpc.example.org/?x-api-key={SECRET}",
        f"https://rpc.example.org/?token={SECRET}",
        f"https://rpc.example.org/?access_token={SECRET}",
        f"https://rpc.example.org/?secret={SECRET}",
        f"https://rpc.example.org/?key={SECRET}",
        f"https://rpc.example.org/?password={SECRET}",
        f"https://rpc.example.org/?auth={SECRET}",
        f"https://rpc.example.org/?cluster={OPAQUE_TOKEN}",
    ],
)
def test_key_shaped_path_or_parameter_is_refused(endpoint: str) -> None:
    with pytest.raises(ConfigError) as refused:
        RpcSettings(endpoints=[endpoint])
    assert SECRET not in str(refused.value)
    assert OPAQUE_TOKEN not in str(refused.value)


@pytest.mark.parametrize("endpoint", CLEAN_ENDPOINTS)
def test_clean_endpoint_is_accepted(endpoint: str) -> None:
    assert RpcSettings(endpoints=[endpoint]).endpoints == [endpoint]


def test_default_rpc_endpoint_is_accepted() -> None:
    assert RpcSettings().endpoints == ["https://api.mainnet-beta.solana.com"]


@pytest.mark.parametrize("endpoint", ["http://rpc.example.org", "ftp://rpc.example.org"])
def test_non_tls_endpoint_is_still_refused(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        RpcSettings(endpoints=[endpoint])


def test_credential_in_grok_base_url_is_refused_without_echo() -> None:
    with pytest.raises(ConfigError) as refused:
        GrokSettings(base_url=f"https://user:{SECRET}@api.x.ai/v1")
    assert SECRET not in str(refused.value)


def test_key_parameter_in_rest_url_is_refused_without_echo() -> None:
    with pytest.raises(ConfigError) as refused:
        DataSettings(rest_url=f"https://frontend-api.pump.fun/?api-key={SECRET}")
    assert SECRET not in str(refused.value)
