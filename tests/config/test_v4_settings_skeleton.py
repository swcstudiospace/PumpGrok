"""PRC-11: the ten v4 sections exist once and load off when TOML omits them."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pumpgrok.config.sections import v4
from pumpgrok.config.settings import Settings, load_settings

V4_FIELDS: tuple[tuple[str, str], ...] = (
    ("events", "EventsSettings"),
    ("grok_gateway", "GrokGatewaySettings"),
    ("datafeed", "DatafeedSettings"),
    ("recorder", "RecorderSettings"),
    ("strategies", "StrategiesSettings"),
    ("backtest_v2", "BacktestV2Settings"),
    ("risk_strategy", "RiskStrategySettings"),
    ("promotion", "PromotionSettings"),
    ("signer", "SignerSettings"),
    ("paper_fees", "PaperFeesSettings"),
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_each_v4_section_class_exists_once() -> None:
    source = (REPO_ROOT / "src" / "pumpgrok" / "config" / "sections" / "v4.py").read_text(
        encoding="utf-8"
    )
    for _field, class_name in V4_FIELDS:
        assert source.count(f"class {class_name}(") == 1
        assert getattr(v4, class_name).__name__ == class_name


def test_each_v4_section_defaults_off() -> None:
    for field_name, class_name in V4_FIELDS:
        section = getattr(v4, class_name)()
        assert section.enabled is False
        assert section.allowlist == ()
        bound = Settings.model_fields[field_name].annotation
        assert bound is getattr(v4, class_name)


def test_absent_toml_leaves_v4_sections_off(clean_env: None) -> None:
    settings = load_settings()
    for field_name, _class_name in V4_FIELDS:
        section = getattr(settings, field_name)
        assert section.enabled is False
        assert section.allowlist == ()
    assert settings.paper_fees.model == "v1"
    assert "interval" not in v4.PromotionSettings.model_fields
