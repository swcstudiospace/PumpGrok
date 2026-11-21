"""Datafeed/recorder settings load off with bounded caps."""

from __future__ import annotations

import os

import pytest

from pumpgrok.config.sections import v4
from pumpgrok.config.settings import load_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_defaults_off() -> None:
    feed = v4.DatafeedSettings()
    assert feed.enabled is False
    assert feed.allowlist == ()
    assert 1 <= feed.watch_cap <= 1000
    assert 1 <= feed.rate_limit_per_10s <= 1000
    rec = v4.RecorderSettings()
    assert rec.enabled is False
    assert rec.dataset_root == "var/desk/datasets"


def test_absent_toml_keeps_off(clean_env: None) -> None:
    settings = load_settings()
    assert settings.datafeed.enabled is False
    assert settings.recorder.enabled is False
    assert settings.datafeed.watch_cap == 32
    assert settings.paper_fees.model == "v2"
