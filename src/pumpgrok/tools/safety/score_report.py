"""safety.score_report: composable rug heuristics with BLIND semantics (TOOL-003).

Composes six readers in-process (authorities, lp_status, token_metadata,
top_holders, deployer_history, market.liquidity) and scores 0..100
(100 = safest) with per-check reasons. Thresholds come from config
(``SafetyThresholds``) with an optional caller override; any check without
data returns ``blind``, never an exception. A blind check on a required
id, or a hard top-5 veto, forces ``verdict_recommendation = KILL``.
Recommendation only: RISK issues the verdict from the journaled report.

``creator`` is caller-supplied (creation event): the mint account carries
no creator, so without it the deployer check is blind. The creator-share
veto is armed but dormant while off-chain enrichment is unwired.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.config.settings import SafetyThresholds
from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import RetryPolicy, Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.rpc import RpcClient
from pumpgrok.tools.safety.checks import ADVISORY_IDS, CHECK_IDS, REQUIRED_IDS, CheckResult

_WARN_PENALTY = Decimal(10)
_FAIL_PENALTY = Decimal(25)

_KNOWN_THRESHOLD_KEYS = tuple(SafetyThresholds.model_fields)


class Evidence(BaseModel):
    """Where one check's data came from."""

    model_config = ConfigDict(frozen=True)

    check: str
    source: str
    slot: int | None = None
    fetched_at: datetime


class ScoreReportIn(ToolInput):
    """Score ``mint`` for ``intended_size_lamports`` with optional overrides."""

    mint: MintStr
    curve_account: MintStr
    creator: MintStr | None = None
    intended_size_lamports: int = Field(default=0, ge=0)
    thresholds: dict[str, float] | None = None
    checks: list[str] | None = None


class ScoreReportOut(ToolOutput):
    """Scored report; ``blind_checks`` names every check without data."""

    score: int = Field(ge=0, le=100)
    verdict_recommendation: Literal["CLEAR", "CONDITIONAL", "KILL"]
    hard_veto: bool
    checks: list[CheckResult]
    blind_checks: list[str] = []
    evidence: list[Evidence] = []
    thresholds_used: dict[str, float] = {}


SCORE_SPEC = ToolSpec(
    name="safety.score_report",
    description=(
        "Scored rug report with per-check reasons and config thresholds; "
        "missing data yields blind, never an exception."
    ),
    input_model=ScoreReportIn,
    output_model=ScoreReportOut,
    side_effect=SideEffect.READ,
    timeout_s=45.0,
    retry=RetryPolicy.none(),
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/safety/score_report.py composing onchain/market readers",
)


def resolve_thresholds(override: dict[str, float] | None) -> SafetyThresholds:
    """Merge a caller override over config defaults; unknown keys are refused."""
    if not override:
        return SafetyThresholds()
    unknown = sorted(set(override) - set(_KNOWN_THRESHOLD_KEYS))
    if unknown:
        raise DataStale(f"safety.score_report unknown threshold keys: {unknown}")
    return SafetyThresholds(**override)


def _blind(check_id: str, weight: Decimal, reason: str) -> CheckResult:
    return CheckResult(
        id=check_id,  # type: ignore[arg-type]
        status="blind",
        value=None,
        threshold=None,
        weight=weight,
        reason=reason,
    )


async def run_score_report(
    inp: ScoreReportIn,
    rpc: RpcClient,
    *,
    thresholds: SafetyThresholds | None = None,
) -> dict:
    """Compose the readers and return a validated ``ScoreReportOut`` payload."""
    from pumpgrok.tools.market.liquidity import LiquidityIn, run_liquidity
    from pumpgrok.tools.onchain.authorities_tool import AuthoritiesIn, run_authorities
    from pumpgrok.tools.onchain.deployer_history import DeployerHistoryIn, run_deployer_history
    from pumpgrok.tools.onchain.lp_status import LpStatusIn, run_lp_status
    from pumpgrok.tools.onchain.token_metadata import TokenMetadataIn, run_token_metadata
    from pumpgrok.tools.onchain.top_holders import TopHoldersIn, run_top_holders
    from pumpgrok.tools.safety.checks.authority import (
        check_freeze_authority,
        check_mint_authority,
    )
    from pumpgrok.tools.safety.checks.readers import (
        check_deployer_history,
        check_liquidity_depth,
        check_lp_status,
        check_token2022_extensions,
        check_top10_concentration,
    )

    active = thresholds if thresholds is not None else resolve_thresholds(inp.thresholds)
    wanted = set(inp.checks) if inp.checks is not None else set(CHECK_IDS)
    unknown = sorted(wanted - set(CHECK_IDS))
    if unknown:
        raise DataStale(f"safety.score_report unknown check ids: {unknown}")
    runnable = [c for c in CHECK_IDS if c in wanted and c not in ADVISORY_IDS]

    evidence: list[Evidence] = []

    async def _fetch(reader: str, coro) -> dict | None:
        try:
            return await coro
        except DataStale:
            return None

    def _note(check_id: str) -> None:
        evidence.append(
            Evidence(
                check=check_id,
                source=SOLANA_RPC_SOURCE,
                slot=None,
                fetched_at=datetime.now(UTC),
            )
        )

    auth = (
        await _fetch("authorities", run_authorities(AuthoritiesIn(mint=inp.mint), rpc))
        if {"mint_authority", "freeze_authority"} & set(runnable)
        else None
    )
    lp = (
        await _fetch(
            "lp_status",
            run_lp_status(LpStatusIn(mint=inp.mint, curve_account=inp.curve_account), rpc),
        )
        if "lp_status" in runnable
        else None
    )
    meta = (
        await _fetch("token_metadata", run_token_metadata(TokenMetadataIn(mint=inp.mint), rpc))
        if "token2022_extensions" in runnable
        else None
    )
    top = (
        await _fetch("top_holders", run_top_holders(TopHoldersIn(mint=inp.mint), rpc))
        if "top10_concentration" in runnable
        else None
    )
    dep = (
        await _fetch(
            "deployer_history",
            run_deployer_history(DeployerHistoryIn(creator=inp.creator or ""), rpc),
        )
        if "deployer_history" in runnable and inp.creator is not None
        else None
    )
    dep_unresolved = "deployer_history" in runnable and inp.creator is None
    liq = (
        await _fetch(
            "liquidity",
            run_liquidity(
                LiquidityIn(
                    mint=inp.mint,
                    curve_account=inp.curve_account,
                    order_size_lamports=inp.intended_size_lamports,
                ),
                rpc,
            ),
        )
        if "liquidity_depth" in runnable
        else None
    )

    rows: list[CheckResult] = []
    if "mint_authority" in runnable:
        rows.append(
            check_mint_authority(auth)
            if auth is not None
            else _blind("mint_authority", Decimal("0.15"), "mint authority unreadable")
        )
        if auth is not None:
            _note("mint_authority")
    if "freeze_authority" in runnable:
        rows.append(
            check_freeze_authority(auth)
            if auth is not None
            else _blind("freeze_authority", Decimal("0.15"), "freeze authority unreadable")
        )
        if auth is not None:
            _note("freeze_authority")
    if "lp_status" in runnable:
        rows.append(
            check_lp_status(lp)
            if lp is not None
            else _blind("lp_status", Decimal("0.15"), "curve account unreadable")
        )
        if lp is not None:
            _note("lp_status")
    if "top10_concentration" in runnable:
        rows.append(
            check_top10_concentration(top, active)
            if top is not None
            else _blind("top10_concentration", Decimal("0.15"), "holder sample unreadable")
        )
        if top is not None:
            _note("top10_concentration")
    if "deployer_history" in runnable:
        if dep_unresolved:
            rows.append(
                _blind("deployer_history", Decimal("0.10"), "creator not supplied; window unscanned")
            )
        else:
            rows.append(
                check_deployer_history(dep)
                if dep is not None
                else _blind("deployer_history", Decimal("0.10"), "creator window unreadable")
            )
            if dep is not None:
                _note("deployer_history")
    if "token2022_extensions" in runnable:
        rows.append(
            check_token2022_extensions(meta)
            if meta is not None
            else _blind("token2022_extensions", Decimal("0.05"), "mint metadata unreadable")
        )
        if meta is not None:
            _note("token2022_extensions")
    if "liquidity_depth" in runnable:
        rows.append(
            check_liquidity_depth(liq, inp.intended_size_lamports, active)
            if liq is not None
            else _blind("liquidity_depth", Decimal("0.15"), "liquidity unreadable")
        )
        if liq is not None:
            _note("liquidity_depth")
    for check_id in CHECK_IDS:
        if check_id in ADVISORY_IDS and check_id in wanted:
            rows.append(
                CheckResult(
                    id=check_id,  # type: ignore[arg-type]
                    status="blind",
                    value=None,
                    threshold=None,
                    weight=Decimal(0),
                    reason="no Phase-3 data source; advisory blind",
                )
            )
            evidence.append(
                Evidence(
                    check=check_id, source="unwired", slot=None, fetched_at=datetime.now(UTC)
                )
            )

    score = Decimal(100)
    for row in rows:
        if row.status == "warn":
            score -= _WARN_PENALTY
        elif row.status == "fail":
            score -= _FAIL_PENALTY
    score = max(Decimal(0), score)

    top5 = Decimal(str((top or {}).get("top5_share", "0")))
    hard_veto = bool(top is not None and top5 > Decimal(str(active.top5_share_veto)))
    blind_required = [r.id for r in rows if r.status == "blind" and r.id in REQUIRED_IDS]
    if hard_veto or blind_required or score < Decimal(str(active.kill_below_score)):
        verdict: Literal["CLEAR", "CONDITIONAL", "KILL"] = "KILL"
    elif score < Decimal(str(active.conditional_below_score)):
        verdict = "CONDITIONAL"
    else:
        verdict = "CLEAR"

    out = {
        "score": int(score),
        "verdict_recommendation": verdict,
        "hard_veto": hard_veto,
        "checks": [r.model_dump() for r in rows],
        "blind_checks": [r.id for r in rows if r.status == "blind"],
        "evidence": [e.model_dump() for e in evidence],
        "thresholds_used": {k: float(getattr(active, k)) for k in _KNOWN_THRESHOLD_KEYS},
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
        ),
    }
    return ScoreReportOut.model_validate(out).model_dump()


def build_score_report_tool(rpc: RpcClient, thresholds: SafetyThresholds | None = None) -> Tool:
    """Bind ``safety.score_report`` to one injected RPC client and thresholds."""

    @tool(SCORE_SPEC)
    async def _score_report(payload: ScoreReportIn) -> dict:
        return await run_score_report(payload, rpc, thresholds=thresholds)

    return _score_report
