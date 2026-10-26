"""Startup accepts PUMPGROK_PAID_RPC_PROVIDER; the safety provider reads it."""

from __future__ import annotations

import os

import pytest

from pumpgrok.config import settings as settings_module
from pumpgrok.config.settings import find_unknown_env, load_settings
from pumpgrok.tools.safety.provider import PAID_RPC_PROVIDER_ENV_VAR, paid_rpc_provider_recorded

PROVIDER_VALUE = "example-paid-rpc"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_paid_rpc_provider_env_name_is_declared() -> None:
    assert PAID_RPC_PROVIDER_ENV_VAR == "PUMPGROK_PAID_RPC_PROVIDER"
    assert PAID_RPC_PROVIDER_ENV_VAR in settings_module.allowed_env_names()


def test_startup_accepts_paid_rpc_provider_env(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PAID_RPC_PROVIDER_ENV_VAR, PROVIDER_VALUE)
    settings = load_settings()
    assert settings.effective_mode == "paper"
    assert paid_rpc_provider_recorded()


def test_startup_unaffected_when_paid_rpc_provider_unset(clean_env: None) -> None:
    assert load_settings().effective_mode == "paper"
    assert not paid_rpc_provider_recorded()


def test_near_miss_paid_rpc_provider_name_still_refused() -> None:
    misspelled = "PUMPGROK_PAID_RPC_PROVIDR"
    bad = find_unknown_env({misspelled: PROVIDER_VALUE}, settings_module.allowed_env_names())
    assert bad == [f"unknown setting: {misspelled}"]
