"""health.json event, strategy and promotion sections (OBS-02 D-03)."""

from __future__ import annotations

from pumpgrok.supervisor.health import build_status


def _base() -> dict:
    return build_status(
        mode="paper",
        autonomy_level="supervised",
        ledger_status="CONSISTENT",
        ledger_source="replay",
        kill_switch=False,
        seats={},
        uptime_s=1.0,
    )


def test_health_has_event_strategy_promotion_sections() -> None:
    body = _base()
    assert "events" in body
    assert body["events"] == {"depth": 0, "sources": {}, "dlq": 0}
    assert "strategies" in body
    assert body["strategies"] == {}
    assert "promotion" in body
    assert body["promotion"] == {"stages": {}, "recent": []}


def test_health_sections_carry_values() -> None:
    body = build_status(
        mode="paper",
        autonomy_level="supervised",
        ledger_status="CONSISTENT",
        ledger_source="replay",
        kill_switch=False,
        seats={},
        uptime_s=1.0,
        events={"depth": 5, "sources": {"feed": "live"}, "dlq": 2},
        strategies={"s1": {"stage": "PAPER", "slice": "ok"}},
        promotion={"stages": {"PAPER": 1}, "recent": ["s1->PAPER"]},
    )
    assert body["events"]["depth"] == 5
    assert body["events"]["sources"]["feed"] == "live"
    assert body["events"]["dlq"] == 2
    assert body["strategies"]["s1"]["stage"] == "PAPER"
    assert body["promotion"]["stages"]["PAPER"] == 1


def test_existing_fields_unchanged() -> None:
    body = _base()
    assert body["status"] == "ok"
    assert body["ledger_status"] == "CONSISTENT"
    assert body["ledger_source"] == "replay"
    assert body["kill_switch"] is False


def test_no_skipped() -> None:
    # Zero-skip rule: this module must not contain a skip marker.
    import inspect
    import pumpgrok.supervisor.health as mod

    src = inspect.getsource(mod)
    assert "pytest.skip" not in src
    assert "pytest.mark.skip" not in src
