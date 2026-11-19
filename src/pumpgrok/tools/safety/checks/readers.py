"""Concentration, deployer, LP, extension and depth checks (TOOL-003).

Pure functions over the typed reader payloads; thresholds come from
``SafetyThresholds`` (config), never from literals.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any, Literal

from pumpgrok.config.settings import SafetyThresholds
from pumpgrok.tools.safety.checks import CheckResult


def check_lp_status(lp: dict[str, Any]) -> CheckResult:
    """Pass on an open curve; warn once graduated (lock state unwired)."""
    stage = str(lp.get("stage", "unknown"))
    if stage == "bonding_curve":
        return CheckResult(
            id="lp_status",
            status="pass",
            value=stage,
            threshold="bonding_curve",
            reason="token still on the bonding curve; no LP to lock",
        )
    if stage == "graduated":
        return CheckResult(
            id="lp_status",
            status="warn",
            value=stage,
            threshold="bonding_curve",
            reason="graduated to a pool; lock/burn state is unwired in Phase 3",
        )
    return CheckResult(
        id="lp_status",
        status="blind",
        value=stage,
        threshold="bonding_curve",
        reason="liquidity stage could not be determined",
    )


def check_top10_concentration(top: dict[str, Any], thresholds: SafetyThresholds) -> CheckResult:
    """Fail/warn/pass the top-10 supply share against configured pcts."""
    share = Decimal(str(top.get("top10_share", "0"))) * Decimal(100)
    pct = float(share)
    status: Literal["fail", "warn", "pass"]
    if pct >= thresholds.top10_concentration_fail_pct:
        status = "fail"
    elif pct >= thresholds.top10_concentration_warn_pct:
        status = "warn"
    else:
        status = "pass"
    return CheckResult(
        id="top10_concentration",
        status=status,
        value=pct,
        threshold=thresholds.top10_concentration_fail_pct,
        reason=f"top-10 holders own {pct:.2f}% of supply",
    )


def check_deployer_history(dep: dict[str, Any]) -> CheckResult:
    """Fail adjudicated-bad creators; warn prolific ones; pass the rest."""
    if bool(dep.get("is_known_bad")) or int(dep.get("rugs", 0)) > 0:
        return CheckResult(
            id="deployer_history",
            status="fail",
            value=True,
            threshold="no known rugs",
            reason="creator record shows known-bad history",
        )
    seen = int(dep.get("tokens_seen", 0))
    if seen >= 3:
        return CheckResult(
            id="deployer_history",
            status="warn",
            value=seen,
            threshold=3,
            reason=f"creator has launched {seen} tokens in the window; serial-launcher caution",
        )
    return CheckResult(
        id="deployer_history",
        status="pass",
        value=seen,
        threshold=3,
        reason="no known-bad creator history in the window",
    )


def check_token2022_extensions(meta: dict[str, Any]) -> CheckResult:
    """Warn when transfer-hook-style extensions are present."""
    extensions = meta.get("extensions") or []
    count = len(extensions)
    return CheckResult(
        id="token2022_extensions",
        status="warn" if count else "pass",
        value=float(count),
        threshold="none",
        reason=(
            f"{count} token-2022 extensions present; review transfer hooks"
            if count
            else "no token-2022 extensions"
        ),
    )


def check_liquidity_depth(
    liq: dict[str, Any], intended_size_lamports: int, thresholds: SafetyThresholds
) -> CheckResult:
    """Fail/warn/pass the liquidity multiple against configured floors."""
    liquidity = int(liq.get("liquidity_lamports", 0))
    if liquidity <= 0:
        return CheckResult(
            id="liquidity_depth",
            status="fail",
            value=0.0,
            threshold=thresholds.liquidity_multiple_min,
            reason="no measurable liquidity for the intended size",
        )
    if intended_size_lamports <= 0:
        return CheckResult(
            id="liquidity_depth",
            status="pass",
            value=float("inf"),
            threshold=thresholds.liquidity_multiple_min,
            reason="no intended size; depth check vacuous",
        )
    # Exact rational ratio: a float division rounds near 2**53 and can lift a sub-floor
    # depth onto the floor.
    multiple = Fraction(liquidity, intended_size_lamports)
    status: Literal["fail", "warn", "pass"]
    if multiple < Fraction(str(thresholds.liquidity_multiple_min)):
        status = "fail"
    elif multiple < Fraction(str(thresholds.liquidity_multiple_recommended)):
        status = "warn"
    else:
        status = "pass"
    return CheckResult(
        id="liquidity_depth",
        status=status,
        value=float(multiple),
        threshold=thresholds.liquidity_multiple_min,
        reason=f"liquidity is {float(multiple):.1f}x the intended size",
    )
