"""Safety check result envelope and check-id vocabulary (TOOL-003).

Every check returns a reasoned row; a check without data returns
``status="blind"`` instead of raising. ``REQUIRED_IDS`` force a KILL
verdict when blind; ``ADVISORY_IDS`` are blind by construction in Phase 3
(no data source wired) and never force the verdict on their own.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckId = Literal[
    "mint_authority",
    "freeze_authority",
    "lp_status",
    "transfer_tax",
    "honeypot",
    "top10_concentration",
    "bundler_cluster",
    "deployer_history",
    "token2022_extensions",
    "liquidity_depth",
]

CHECK_IDS: tuple[str, ...] = (
    "mint_authority",
    "freeze_authority",
    "lp_status",
    "transfer_tax",
    "honeypot",
    "top10_concentration",
    "bundler_cluster",
    "deployer_history",
    "token2022_extensions",
    "liquidity_depth",
)

REQUIRED_IDS: frozenset[str] = frozenset(
    {
        "mint_authority",
        "freeze_authority",
        "lp_status",
        "top10_concentration",
        "deployer_history",
        "token2022_extensions",
        "liquidity_depth",
    }
)

ADVISORY_IDS: frozenset[str] = frozenset({"transfer_tax", "honeypot", "bundler_cluster"})


class CheckResult(BaseModel):
    """One scored check with a human-readable reason (never a bare boolean)."""

    model_config = ConfigDict(frozen=True)

    id: CheckId
    status: Literal["pass", "warn", "fail", "blind"]
    value: str | float | bool | None = None
    threshold: str | float | None = None
    weight: Decimal = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
