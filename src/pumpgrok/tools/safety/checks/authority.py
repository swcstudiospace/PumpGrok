"""Authority checks: mint and freeze flags (TOOL-003).

A live authority is a fail: whoever holds it can dilute or freeze holders.
"""

from __future__ import annotations

from decimal import Decimal

from pumpgrok.tools.safety.checks import CheckResult


def check_mint_authority(auth: dict) -> CheckResult:
    """Pass when the mint authority is revoked; fail while one is live."""
    live = bool(auth.get("has_mint_authority"))
    return CheckResult(
        id="mint_authority",
        status="fail" if live else "pass",
        value=live,
        threshold="revoked",
        weight=Decimal("0.15"),
        reason=(
            "mint authority is live and can dilute holders"
            if live
            else "mint authority revoked; supply is fixed"
        ),
    )


def check_freeze_authority(auth: dict) -> CheckResult:
    """Pass when the freeze authority is revoked; fail while one is live."""
    live = bool(auth.get("has_freeze_authority"))
    return CheckResult(
        id="freeze_authority",
        status="fail" if live else "pass",
        value=live,
        threshold="revoked",
        weight=Decimal("0.15"),
        reason=(
            "freeze authority is live and can lock holder accounts"
            if live
            else "freeze authority revoked; accounts cannot be frozen"
        ),
    )
