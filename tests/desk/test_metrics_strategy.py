"""Per-strategy P and live L metric families (OBS-02 D-03)."""

from __future__ import annotations

import inspect

from prometheus_client import generate_latest

import pumpgrok.supervisor.metrics_events as mod
from pumpgrok.supervisor.metrics import NINE_FAMILIES, build_registry
from pumpgrok.supervisor.metrics_events import (
    STRATEGY_FAMILIES,
    STRATEGY_LIVE_L_TOTAL,
    STRATEGY_P_TOTAL,
    STRATEGY_STAGE,
    EventMetrics,
    build_event_registry,
)


def test_strategy_families_registered_in_event_mode() -> None:
    registry = build_registry()
    metrics = EventMetrics(registry=registry)
    metrics.strategy_p_total.labels(strategy="s1").inc()
    metrics.strategy_l_total.labels(strategy="s1").inc()
    metrics.strategy_stage.labels(strategy="s1", stage="PAPER").inc()
    names = {sample.name for family in registry.collect() for sample in family.samples}
    assert any(STRATEGY_P_TOTAL in n for n in names)
    assert any(STRATEGY_LIVE_L_TOTAL in n for n in names)
    assert any(STRATEGY_STAGE in n for n in names)


def test_nine_families_unchanged() -> None:
    assert len(NINE_FAMILIES) == 9
    assert len(set(NINE_FAMILIES)) == 9
    assert set(STRATEGY_FAMILIES) == {STRATEGY_P_TOTAL, STRATEGY_LIVE_L_TOTAL, STRATEGY_STAGE}
    assert not (set(STRATEGY_FAMILIES) & set(NINE_FAMILIES))


def test_strategy_labels_are_ids_only() -> None:
    registry = build_registry()
    metrics = EventMetrics(registry=registry)
    metrics.strategy_p_total.labels(strategy="s1").inc()
    metrics.strategy_l_total.labels(strategy="s1").inc()
    metrics.strategy_stage.labels(strategy="s1", stage="PAPER").inc()
    text = generate_latest(registry).decode("utf-8")
    assert STRATEGY_P_TOTAL in text
    assert STRATEGY_LIVE_L_TOTAL in text
    assert STRATEGY_STAGE in text
    assert "strategy" in text


def test_strategy_families_absent_in_cadence() -> None:
    assert build_event_registry("cadence") is None


def test_no_skipped() -> None:
    src = inspect.getsource(mod)
    assert "pytest.skip" not in src
    assert "pytest.mark.skip" not in src
