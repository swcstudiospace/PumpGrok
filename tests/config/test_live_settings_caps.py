"""The 1 SOL notional ceiling still refuses a larger cap. LiveSettings is read, not edited."""

from __future__ import annotations

import os

import pytest

from pumpgrok.config.settings import ConfigError, LiveSettings, load_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_notional_cap_above_one_sol_refuses_on_load(clean_env: None) -> None:
    default = LiveSettings.model_fields["notional_cap_lamports"].default
    assert isinstance(default, int)
    above = default + 1
    with pytest.raises(ConfigError) as excinfo:
        load_settings(live={"notional_cap_lamports": above})
    text = "\n".join(excinfo.value.problems)
    assert "notional_cap_lamports" in text
    assert str(above) not in text
