"""Event metric families appear only in event mode (GRK-10)."""

from prometheus_client import CollectorRegistry

from pumpgrok.supervisor.metrics import NINE_FAMILIES
from pumpgrok.supervisor.metrics_events import EVENT_FAMILIES, build_event_registry


def _family_names(registry: CollectorRegistry) -> set[str]:
    return {family.name for family in registry.collect()}


def test_nine_families_unchanged() -> None:
    assert len(NINE_FAMILIES) == 9


def test_event_registry_has_five_new_families() -> None:
    registry = build_event_registry("event")
    assert registry is not None
    names = _family_names(registry)
    for family_name in EVENT_FAMILIES:
        stem = family_name[: -len("_total")] if family_name.endswith("_total") else family_name
        assert family_name in names or stem in names


def test_cadence_has_no_event_families() -> None:
    assert build_event_registry("cadence") is None
    registry = build_event_registry("event")
    assert registry is not None
    names = _family_names(registry)
    for nine in NINE_FAMILIES:
        assert nine not in names or nine in EVENT_FAMILIES
