<<<<<<< HEAD
"""Paper fee default is v2; v1 stays selectable with v1 arithmetic."""
=======
"""FEE-01 settings: the effective paper fee model defaults to v2; v1 stays selectable."""
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687

from __future__ import annotations

import os

import pytest

<<<<<<< HEAD
from pumpgrok.config.sections.v4 import PaperFeesSettings
from pumpgrok.config.settings import load_settings
from pumpgrok.execution.fees import FeeModel, FeeModelV2, fee_model_for
=======
from pumpgrok.config.settings import ConfigError, Settings, load_settings
from pumpgrok.execution.fees import PAPER_DEFAULT_FEE_MODEL, FeeModel, FeeModelV2
from pumpgrok.execution.paper_factory import paper_fee_model
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


<<<<<<< HEAD
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
=======
def test_effective_settings_default_fee_model_is_v2(clean_env: None) -> None:
    assert load_settings().paper_fees.model == "v2"
    assert Settings().paper_fees.model == "v2"


def test_the_default_selection_is_the_paper_default_object(clean_env: None) -> None:
    fees = paper_fee_model(load_settings())
    assert fees == PAPER_DEFAULT_FEE_MODEL
    assert isinstance(fees, FeeModelV2)


def test_v1_is_still_accepted_explicitly(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_PAPER_FEES__MODEL", "v1")
    settings = load_settings()
    assert settings.paper_fees.model == "v1"
    fees = paper_fee_model(settings)
    assert type(fees) is FeeModel


def test_an_unknown_fee_model_fails_fast(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_PAPER_FEES__MODEL", "v3")
    with pytest.raises(ConfigError):
        load_settings()
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
