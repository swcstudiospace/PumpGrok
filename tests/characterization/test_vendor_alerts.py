"""Characterization: edge-triggered alert transitions (STRUCT-004).

Pins ``engine/alerts.py`` against
``vendor/grokbot-pumpfun/src/pipeline.py:334-368`` (``_check_transitions``)
and ``vendor/grokbot-pumpfun/tests/test_pipeline.py:598-675`` (breaker,
halt, blind announcement rows; the stalled edge has no dedicated vendor row
and is pinned here by symmetry). The vendor oracle is kept byte-identical
per R53.

Adaptations from the oracle (deliberate):

- The vendor fires through a webhook notifier with Russian on/off texts and
  an ``enabled`` gate. The port returns bare ``EdgeTransition`` records; the
  supervisor and notifier in plan 04-08 own delivery and wording. These
  tests therefore assert (name, active) sequences, never prose.
- Status computation (``breaker == "open"``, stall timers, blind counts)
  stays with the pipeline/supervisor. The tests feed plain booleans, which
  is exactly what the vendor ``_alerted`` comparisons reduce the statuses
  to.
- All prose is English; the vendor text is Russian.
"""

from __future__ import annotations

import pytest

from pumpgrok.engine.alerts import ALERT_EDGES, AlertEdges


@pytest.fixture
def edges() -> AlertEdges:
    return AlertEdges()


def test_all_edges_start_silent(edges: AlertEdges) -> None:
    assert edges.check({}) == []
    assert edges.armed == {"breaker": False, "halted": False, "stalled": False, "blind": False}


def test_edges_follow_vendor_check_order() -> None:
    assert ALERT_EDGES == ("breaker", "halted", "stalled", "blind")


def test_breaker_fires_once_per_transition(edges: AlertEdges) -> None:
    assert [(t.name, t.active) for t in edges.check({"breaker": True})] == [("breaker", True)]

    first = edges.check({"breaker": True})
    assert first == []
    assert edges.check({"breaker": True}) == []
    cleared = edges.check({"breaker": False})
    assert [(t.name, t.active) for t in cleared] == [("breaker", False)]


def test_breaker_on_text_transition_shape(edges: AlertEdges) -> None:
    (fired,) = edges.check({"breaker": True})
    assert (fired.name, fired.active) == ("breaker", True)


def test_halt_is_announced(edges: AlertEdges) -> None:
    (fired,) = edges.check({"halted": True})
    assert (fired.name, fired.active) == ("halted", True)
    assert edges.check({"halted": True}) == []


def test_stalled_edge_fires_once(edges: AlertEdges) -> None:
    (fired,) = edges.check({"stalled": True})
    assert (fired.name, fired.active) == ("stalled", True)
    assert edges.check({"stalled": True}) == []
    (cleared,) = edges.check({"stalled": False})
    assert (cleared.name, cleared.active) == ("stalled", False)


def test_blind_edge_fires_once(edges: AlertEdges) -> None:
    (fired,) = edges.check({"blind": True})
    assert (fired.name, fired.active) == ("blind", True)
    assert edges.check({"blind": True}) == []


def test_simultaneous_edges_fire_in_check_order(edges: AlertEdges) -> None:
    fired = edges.check({"blind": True, "breaker": True, "halted": True})
    assert [(t.name, t.active) for t in fired] == [
        ("breaker", True),
        ("halted", True),
        ("blind", True),
    ]


def test_held_state_never_refires(edges: AlertEdges) -> None:
    edges.check({"breaker": True, "halted": True})
    for _ in range(5):
        assert edges.check({"breaker": True, "halted": True}) == []


def test_refire_after_clear(edges: AlertEdges) -> None:
    assert [(t.name, t.active) for t in edges.check({"blind": True})] == [("blind", True)]
    assert [(t.name, t.active) for t in edges.check({"blind": False})] == [("blind", False)]
    assert [(t.name, t.active) for t in edges.check({"blind": True})] == [("blind", True)]


def test_unknown_edge_raises(edges: AlertEdges) -> None:
    with pytest.raises(KeyError, match="unknown alert edge"):
        edges.check({"meltdown": True})
