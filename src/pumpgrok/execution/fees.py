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

__all__ = [
    "ATA_RENT_LAMPORTS",
    "BASE_FEE_LAMPORTS",
    "BUILDER_FEE_BPS",
    "COMPUTE_UNITS",
    "PRIORITY_FEE_CAP_LAMPORTS",
    "VENUE_FEE_BPS",
    "FeeModel",
    "FeeModelV2",
    "fee_model_for",
]

#: pump.fun take in basis points (REVIEW).
VENUE_FEE_BPS = 100
#: One signature in lamports (REVIEW).
BASE_FEE_LAMPORTS = 5_000
#: Compute units per fill (REVIEW).
COMPUTE_UNITS = 200_000
#: PumpPortal builder fee in bps when that builder is used (v2 only, REVIEW).
BUILDER_FEE_BPS = 50
#: ATA rent lamports on the first buy of a mint (v2 only, REVIEW).
ATA_RENT_LAMPORTS = 2_039_280
#: Signer priority-fee cap in lamports (v2 only, REVIEW).
PRIORITY_FEE_CAP_LAMPORTS = 1_000_000


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


@dataclass(frozen=True)
class FeeModelV2(FeeModel):
    """v2: venue 100 bps plus builder fee when used, ATA rent first-buy, capped priority.

    Integer lamports with flooring throughout. v1 numbers are untouched.
    The builder-fee condition is the ``use_builder`` argument pinned by tests.
    """

    builder_fee_bps: int = BUILDER_FEE_BPS
    ata_rent_lamports: int = ATA_RENT_LAMPORTS
    priority_fee_cap_lamports: int = PRIORITY_FEE_CAP_LAMPORTS

    def builder_fee(self, size_lamports: int, *, use_builder: bool) -> int:
        """PumpPortal builder fee when that builder is used; 0 otherwise."""
        if not use_builder:
            return 0
        return size_lamports * self.builder_fee_bps // 10_000

    def first_buy_extra(self, *, is_first_buy: bool) -> int:
        """ATA rent on the first buy of a mint only."""
        return self.ata_rent_lamports if is_first_buy else 0

    def priority_fee(self) -> int:
        """Priority cost capped at the signer priority-fee cap."""
        return min(super().priority_fee(), self.priority_fee_cap_lamports)

    def buy_debit(self, filled_lamports: int, *, use_builder: bool = False) -> int:
        """Cash debited for a v2 buy: filled plus builder fee and network."""
        return (
            filled_lamports
            + self.builder_fee(filled_lamports, use_builder=use_builder)
            + self.network_cost()
        )


def fee_model_for(model_name: str) -> FeeModel:
    """Build the configured fee model; the paper default is v2, v1 stays selectable."""
    if model_name == "v2":
        return FeeModelV2()
    if model_name != "v1":
        raise ValueError(f"unknown fee model: {model_name!r}")
    return FeeModel()
