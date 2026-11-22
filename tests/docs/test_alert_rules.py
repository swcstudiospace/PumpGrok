"""Registry-conformance test for alert expressions (OBS-03 D-04)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from pumpgrok.supervisor.metrics import NINE_FAMILIES
from pumpgrok.supervisor.metrics_events import (
    EVENT_FAMILIES,
    STRATEGY_FAMILIES,
)

METRIC_RE = re.compile(r"pumpgrok_[a-z0-9_]+")


def _registry_metrics() -> set[str]:
    return set(NINE_FAMILIES) | set(EVENT_FAMILIES) | set(STRATEGY_FAMILIES)


def _rules() -> list[dict]:
    path = Path("docs/observability/alerts.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["rules"]


def validate_rules(rules: list[dict], registry: set[str]) -> None:
    """Raise if any rule names a metric the registry does not expose."""
    for rule in rules:
        expr = str(rule.get("expr", ""))
        for metric in METRIC_RE.findall(expr):
            assert metric in registry, f"{rule.get('name')}: unknown metric {metric}"
        assert "metric" in rule or "expr" in rule
        assert "threshold" in rule or "severity" in rule or "description" in rule


def test_five_rules_cover_required_signals() -> None:
    rules = _rules()
    assert len(rules) == 5
    names = {r["name"] for r in rules}
    assert names == {
        "dead-letters",
        "stale-sources",
        "grok-budget-exhaustion",
        "strategy-kills",
        "signer-unknown",
    }
    for rule in rules:
        assert rule["expr"]
        assert "threshold" in rule
        assert rule["severity"] in ("critical", "major", "minor")
        assert rule["description"]


def test_every_expression_names_a_registry_metric() -> None:
    validate_rules(_rules(), _registry_metrics())


def test_conformance_rejects_bogus_metric() -> None:
    bogus = [
        {
            "name": "bogus",
            "expr": "pumpgrok_no_such_metric_total > 0",
            "threshold": 0,
            "severity": "major",
            "description": "deliberately wrong",
        }
    ]
    try:
        validate_rules(bogus, _registry_metrics())
    except AssertionError:
        return
    raise AssertionError("bogus metric must fail conformance")
