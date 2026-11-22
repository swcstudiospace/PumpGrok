"""Paper fee default is v2; v1 stays selectable with v1 arithmetic."""

from __future__ import annotations

import os

import pytest

from pumpgrok.config.sections.v4 import PaperFeesSettings
from pumpgrok.config.settings import load_settings
from pumpgrok.execution.fees import FeeModel, FeeModelV2, fee_model_for


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_default_model_v2(clean_env: None) -> None:
    assert load_settings().paper_fees.model == "v2"


def test_default_builds_v2_model(clean_env: None) -> None:
    settings = load_settings()
    assert isinstance(fee_model_for(settings.paper_fees.model), FeeModelV2)


def test_explicit_v1_still_yields_v1() -> None:
    assert PaperFeesSettings(model="v1").model == "v1"
    fees = fee_model_for(PaperFeesSettings(model="v1").model)
    assert isinstance(fees, FeeModel)
    assert not isinstance(fees, FeeModelV2)
    assert fees.network_cost() == 9_000
