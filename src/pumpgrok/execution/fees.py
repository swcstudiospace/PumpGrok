"""Integer fee models for paper fills (paper-engine.md 2.3, PAPER-001, R28).

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

FEE-01 (fee model v2, :class:`FeeModelV2`) is the paper default. The ATA rent on the
first buy of each mint is a refundable deposit: the cash leaves on that buy and the
deposit is held as an asset in the position's mark until the position closes in full, when
it is refunded to cash and kept out of realized P&L. It also adds a cap on the
priority price. The ATA
rent is read at runtime from RPC by :func:`read_ata_rent`. The pinned value is an
offline replay fallback; it records its epoch and source and is never the stale
2039280. :class:`FeeModel` (v1) stays selectable through :func:`fee_model_for`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Final, Protocol

__all__ = [
    "ATA_RENT_OFFLINE_EPOCH",
    "ATA_RENT_OFFLINE_LAMPORTS",
    "ATA_RENT_OFFLINE_SOURCE",
    "ATA_TOKEN_ACCOUNT_DATA_LEN",
    "BASE_FEE_LAMPORTS",
    "COMPUTE_UNITS",
    "PAPER_DEFAULT_FEE_MODEL",
    "VENUE_FEE_BPS",
    "FeeModel",
    "FeeModelV2",
    "fee_model_for",
    "read_ata_rent",
]

#: pump.fun take in basis points (REVIEW).
VENUE_FEE_BPS = 100
#: One signature in lamports (REVIEW).
BASE_FEE_LAMPORTS = 5_000
#: Compute units per fill (REVIEW).
COMPUTE_UNITS = 200_000

#: SPL token account data length; the rent-exempt minimum is read for this size.
ATA_TOKEN_ACCOUNT_DATA_LEN: Final = 165
#: Offline replay fallback for the rent-exempt minimum of one token account. Owner
#: decision 2026-11-15: the value is read from RPC at runtime; this pin is used only
#: when no RPC read happened (offline replay). 1488440 is the active rate since epoch 1033.
ATA_RENT_OFFLINE_LAMPORTS: int = 1_488_440
ATA_RENT_OFFLINE_EPOCH: Final = 1033
ATA_RENT_OFFLINE_SOURCE: Final = (
    "offline-pinned: owner decision 2026-11-15, public docs (SIMD-0437); replay only"
)


@dataclass(frozen=True)
class FeeModel:
    """Venue, base and priority fees for one fill (v1)."""

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

    def buy_network_cost(self, *, first_buy: bool) -> int:
        """Network cost charged on a BUY fill. v1 has no first-buy term."""
        del first_buy
        return self.network_cost()

    def ata_deposit_term(self, *, first_buy: bool) -> int:
        """Refundable ATA deposit held as an asset on this fill. v1 holds none."""
        del first_buy
        return 0

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
    """Fee model v2 (FEE-01): v1 plus ATA rent and a priority cap.

    ``ata_rent_lamports`` is charged on each (re-)entry while the mint is flat
    (the caller passes ``first_buy=True`` when the ledger holds no open
    position for the mint), matching on-chain ATA recreation
    (charge_on_reentry): a close refunds the deposit, and the next entry pays
    it again. The default is the offline pin, and ``ata_rent_source`` says
    so. The priority price is
    clamped to ``priority_cap_micro_lamports_per_cu`` before the v1 formula.
    All values are integer lamports.
    """

    ata_rent_lamports: int = ATA_RENT_OFFLINE_LAMPORTS
    ata_rent_epoch: int | None = ATA_RENT_OFFLINE_EPOCH
    ata_rent_source: str = ATA_RENT_OFFLINE_SOURCE
    priority_cap_micro_lamports_per_cu: int = 20_000

    def priority_fee(self) -> int:
        """Priority cost with the price clamped to the cap (floored)."""
        capped = min(self.micro_lamports_per_cu, self.priority_cap_micro_lamports_per_cu)
        return capped * self.compute_units // 1_000_000

    def ata_rent_term(self, first_buy: bool) -> int:
        """ATA rent for this fill: charged when the entry opens a flat mint.

        ``first_buy`` is the (re-)entry flag: True whenever the mint holds no
        open position, including a re-entry after a close refunded the deposit.
        """
        return self.ata_rent_lamports if first_buy else 0

    def ata_deposit_term(self, *, first_buy: bool) -> int:
        """Refundable ATA deposit held as an asset: the rent on a first buy, else zero."""
        return self.ata_rent_term(first_buy)

    def buy_network_cost(self, *, first_buy: bool) -> int:
        """Base plus priority, plus the ATA rent on a (re-)entry of a flat mint."""
        return self.network_cost() + self.ata_rent_term(first_buy)


#: The paper default (FEE-01). Backtest and paper both select it through fee_model_for.
PAPER_DEFAULT_FEE_MODEL: Final = FeeModelV2()


def fee_model_for(model: str) -> FeeModel:
    """The fee model a settings value selects: ``v2`` (default) or ``v1``."""
    if model == "v2":
        return PAPER_DEFAULT_FEE_MODEL
    if model == "v1":
        return FeeModel()
    raise ValueError(f"unknown paper fee model: {model}")


class _RentRpc(Protocol):
    """The one read this module needs: a JSON-RPC call returning its result."""

    async def call(self, method: str, params: list[Any]) -> Any: ...


async def read_ata_rent(rpc: _RentRpc, *, base: FeeModelV2 = PAPER_DEFAULT_FEE_MODEL) -> FeeModelV2:
    """Read the rent-exempt minimum for one token account at runtime and return v2 with it.

    The RPC result replaces the offline pin. A non-integer or non-positive result is
    refused. Epoch is None because this read does not return one.
    """
    lamports = await rpc.call("getMinimumBalanceForRentExemption", [ATA_TOKEN_ACCOUNT_DATA_LEN])
    if type(lamports) is not int or lamports <= 0:
        raise ValueError("rent read is not a positive integer")
    return replace(
        base,
        ata_rent_lamports=lamports,
        ata_rent_epoch=None,
        ata_rent_source="rpc:getMinimumBalanceForRentExemption(165)",
    )
