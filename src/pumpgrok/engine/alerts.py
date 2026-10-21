"""Edge-triggered alert transitions for the supervisor.

Port of the ``_check_transitions`` half of the retired oracle
``src/pipeline.py:334-368``. All prose is English;
the vendor text is Russian.

Deliberate divergences from the oracle:

- The vendor couples edge memory to the pipeline status snapshot and the
  webhook notifier (Russian on/off texts, ``enabled`` gate). The port keeps
  only the edge memory: given the current on/off state of each edge,
  return the transitions that newly fired. Text building and delivery stay
  with the supervisor and the notifier in plan 04-08, which own the
  operator-facing wording.
- Statuses arrive as plain booleans. The ``breaker`` half-open probe state
  counts as closed here (no alert); only a fully open breaker raises the
  edge, exactly like the vendor ``status["breaker"] == "open"`` check.
- Unknown edge names raise ``KeyError``: the four edges are the whole
  contract, and a misspelled caller must fail loudly rather than stay
  silent forever.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# The four state changes worth waking an operator for, in vendor check order.
ALERT_EDGES = ("breaker", "halted", "stalled", "blind")


@dataclass(frozen=True)
class EdgeTransition:
    """One edge that newly fired. ``active`` tells on from off."""

    name: str
    active: bool


class AlertEdges:
    """Remembers which alert edges are currently raised.

    Call :meth:`check` on every supervisor tick with the current edge
    states; each transition (rising or falling) is reported exactly once,
    no matter how long the state holds.
    """

    def __init__(self) -> None:
        self._alerted: dict[str, bool] = dict.fromkeys(ALERT_EDGES, False)

    @property
    def armed(self) -> dict[str, bool]:
        """Currently raised edges, for status snapshots and tests."""
        return dict(self._alerted)

    def check(self, active: Mapping[str, bool]) -> list[EdgeTransition]:
        """Report the edges that changed since the last call.

        Missing names count as not raised; unknown names raise
        ``KeyError``. Returned transitions follow :data:`ALERT_EDGES` order.
        """
        unknown = set(active) - set(self._alerted)
        if unknown:
            raise KeyError(f"unknown alert edge: {sorted(unknown)}")
        fired: list[EdgeTransition] = []
        for name in ALERT_EDGES:
            now = bool(active.get(name, False))
            if now != self._alerted[name]:
                fired.append(EdgeTransition(name, now))
            self._alerted[name] = now
        return fired
