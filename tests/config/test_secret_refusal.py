"""STRUCT-008 / SEC-002 slice: no wallet or Jito material, CLI secret refusal."""

from __future__ import annotations

import os

import pytest
from pydantic import BaseModel

import pumpgrok.config.settings as settings_module
from pumpgrok.config.settings import (
    ConfigError,
    Settings,
    load_settings,
    mask,
    refuse_cli_secrets,
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def _all_field_names(model: type[BaseModel]) -> set[str]:
    names: set[str] = set()
    for field_name, field in model.model_fields.items():
        names.add(field_name)
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            names.update(_all_field_names(annotation))
    return names


def test_no_jito_or_wallet_material_in_model(clean_env: None) -> None:
    assert not hasattr(settings_module, "JitoConfig")
    assert "wallet_private_key" not in _all_field_names(Settings)
    assert "JitoConfig" not in dir(settings_module)
    settings = load_settings()
    dumped = settings.model_dump_json()
    assert "wallet_private_key" not in dumped
    assert "jito" not in dumped.lower()


def test_mask_never_returns_full_secret() -> None:
    assert mask("") == "<empty>"
    assert mask("short") == "***"
    assert mask("0123456789abcdef") != "0123456789abcdef"


def test_cli_flag_with_key_bearing_url_refused() -> None:
    argv = ["--rpc", "https://api.example/x?api-key=PLANTED-CLI-KEY-1"]
    with pytest.raises(ConfigError) as excinfo:
        refuse_cli_secrets(argv)
    message = str(excinfo.value)
    assert "--rpc" in message
    assert "PLANTED-CLI-KEY-1" not in message


def test_clean_cli_passes() -> None:
    refuse_cli_secrets(["run", "--mode", "paper", "--once"])
