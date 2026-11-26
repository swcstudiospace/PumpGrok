"""Grok agents: auditor, narrative, timing, and the adversarial checker.

Ported from the retired oracle ``src/agents/`` (pin 409e74c,
byte-identical per R53). Every agent runs on the injected clock and admits
each model call through the shared ``GrokGateway``; the agents hold no HTTP
client. Each agent selects its model from settings per R48: the checker uses
the strong model at low effort, the rest use the fast model.
"""

from pumpgrok.engine.agents.auditor import AuditorAgent
from pumpgrok.engine.agents.base import GrokAgent
from pumpgrok.engine.agents.checker import CheckerAgent
from pumpgrok.engine.agents.narrative import NarrativeAgent
from pumpgrok.engine.agents.rug import RugSeat
from pumpgrok.engine.agents.scout import ScoutSeat
from pumpgrok.engine.agents.signal import SignalSeat
from pumpgrok.engine.agents.timing import TimingAgent
from pumpgrok.engine.agents.whale import WhaleSeat

__all__ = [
    "AuditorAgent",
    "CheckerAgent",
    "GrokAgent",
    "NarrativeAgent",
    "RugSeat",
    "ScoutSeat",
    "SignalSeat",
    "TimingAgent",
    "WhaleSeat",
]
