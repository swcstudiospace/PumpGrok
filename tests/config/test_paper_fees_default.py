"""Paper fee default stays v1 with no paper_fees key."""

from __future__ import annotations

import os

import pytest

from pumpgrok.config.settings import load_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_default_model_v1(clean_env: None) -> None:
    assert load_settings().paper_fees.model == "v1"
