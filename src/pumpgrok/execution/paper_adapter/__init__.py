"""Curve-faithful paper fills (paper-engine.md 2, PAPER-001, PAPER-005, R6, R38).

Every pre-graduation fill prices from curve reserves, never from a quote.
The Jupiter quote is informational only: it is stored on ``OrderPlaced``
with ``source="curve"`` and never enters the fill math (T-04-08).

One order flows NEW -> ACCEPTED -> CONFIRMING -> FILLED | PARTIAL |
REJECTED (paper-engine.md 2.8). ``RiskEngine.check`` runs first with the
order hash bound (R24); no fill exists without a passing ``RiskDecision``.
``OrderPlaced`` shares one ``append_batch`` transaction with the approval
consumption row (the shared-transaction shape; autonomous-mint persistence
lands in plan 04-07). Seeded confirmation latency runs on the injected
clock; CONFIRMING re-reads the curve and re-runs the stop checks before
any fill is computed. Idempotency is on ``(ticket_id, side, decision_id)``
(R23): a repeated decision returns the first Fill.
"""

from pumpgrok.core.errors import OrderRejectedError, OrderUnknownError
from pumpgrok.execution.paper_adapter.adapter import PaperAdapter
from pumpgrok.execution.paper_adapter.models import CurveSnapshot, PriceSource

__all__ = [
    "CurveSnapshot",
    "OrderRejectedError",
    "OrderUnknownError",
    "PaperAdapter",
    "PriceSource",
]
