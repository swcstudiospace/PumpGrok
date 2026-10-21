"""Integer fee model for paper fills (paper-engine.md 2.3, PAPER-001, R28).

All lamports, integer arithmetic with flooring. The venue fee prices the
pump.fun take (100 bps, REVIEW); the base fee prices one signature (5000
lamports, REVIEW); the priority fee prices compute
(``micro_lamports_per_cu * compute_units // 1_000_000``, CU 200000 REVIEW).
There is no tip term (vendor ``JitoConfig`` is not carried, R3).

Buy: ``x_net = size - venue_fee`` enters the curve; the cash debit is
``filled + network_cost``. Sell: ``proceeds = gross - venue_fee - network``.
A rejected-then-broadcast transaction still pays the network cost, so
``slippage_exceeded`` records ``network_cost`` while ``tx_dropped`` (never
sent) records nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BASE_FEE_LAMPORTS", "COMPUTE_UNITS", "VENUE_FEE_BPS", "FeeModel"]

#: pump.fun take in basis points (REVIEW).
VENUE_FEE_BPS = 100
#: One signature in lamports (REVIEW).
BASE_FEE_LAMPORTS = 5_000
#: Compute units per fill (REVIEW).
COMPUTE_UNITS = 200_000


@dataclass(frozen=True)
class FeeModel:
    """Venue, base and priority fees for one fill."""

    venue_fee_bps: int = VENUE_FEE_BPS
    base_fee_lamports: int = BASE_FEE_LAMPORTS
    compute_units: int = COMPUTE_UNITS
    micro_lamports_per_cu: int = 20_000

    def venue_fee(self, size_lamports: int) -> int:
        """Venue take on ``size_lamports`` (floored)."""
        return size_lamports * self.venue_fee_bps // 10_000

    def priority_fee(self) -> int:
        """Priority cost for one transaction (floored)."""
        return self.micro_lamports_per_cu * self.compute_units // 1_000_000

    def network_cost(self) -> int:
        """Base plus priority: the cost of landing (or failing) one transaction."""
        return self.base_fee_lamports + self.priority_fee()

    def buy_net(self, filled_lamports: int) -> int:
        """Lamports that enter the curve for a buy fill."""
        return filled_lamports - self.venue_fee(filled_lamports)

    def buy_debit(self, filled_lamports: int) -> int:
        """Cash debited for a buy fill: filled plus network cost."""
        return filled_lamports + self.network_cost()

    def sell_proceeds(self, gross_lamports: int) -> int:
        """Cash credited for a sell: gross minus venue fee minus network cost."""
        return gross_lamports - self.venue_fee(gross_lamports) - self.network_cost()
