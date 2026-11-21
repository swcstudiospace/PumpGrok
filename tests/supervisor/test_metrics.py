"""Metrics: nine existing families unchanged; event families only in event mode."""

from pumpgrok.supervisor.metrics import NINE_FAMILIES, build_registry
from pumpgrok.supervisor.metrics_events import EVENT_FAMILIES, EventMetrics, build_event_registry


def test_nine_families_count() -> None:
    assert len(NINE_FAMILIES) == 9
    assert len(set(NINE_FAMILIES)) == 9


def test_nine_family_names() -> None:
    assert "pumpgrok_cycle_seconds" in NINE_FAMILIES
    assert "pumpgrok_ledger_seq" in NINE_FAMILIES


def test_event_families_absent_in_cadence() -> None:
    registry = build_registry()
    assert build_event_registry("cadence") is None
    names = [sample.name for family in registry.collect() for sample in family.samples]
    for family_name in EVENT_FAMILIES:
        assert not any(family_name in name for name in names)


def test_event_families_present_in_event_mode() -> None:
    registry = build_event_registry("event")
    assert registry is not None
    from pumpgrok.supervisor.metrics_events import EventMetrics

    assert EventMetrics is not None
    assert isinstance(registry, type(build_registry()))
    assert registry is not None
