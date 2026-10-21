"""Grok agents: auditor, narrative, timing, and the adversarial checker.

Ported from ``vendor/grokbot-pumpfun/src/agents/`` (oracle, kept
byte-identical per R53). Every agent runs on the injected clock with seeded
randomness only, posts to the x.ai base URL plus ``/chat/completions``, and
selects its model from settings per R48: the checker uses the strong model
at low effort, the rest use the fast model.
"""

from pumpgrok.engine.agents.auditor import AuditorAgent
from pumpgrok.engine.agents.base import GrokAgent, GrokAgentError
from pumpgrok.engine.agents.checker import CheckerAgent
from pumpgrok.engine.agents.narrative import NarrativeAgent
from pumpgrok.engine.agents.timing import TimingAgent

__all__ = [
    "AuditorAgent",
    "CheckerAgent",
    "GrokAgent",
    "GrokAgentError",
    "NarrativeAgent",
    "TimingAgent",
]
