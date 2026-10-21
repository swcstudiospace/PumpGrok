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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.config.settings import SafetyThresholds
from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import RetryPolicy, Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import SOLANA_RPC_SOURCE, MintStr, meta_now, utcnow
from pumpgrok.tools.market.liquidity import LiquidityIn, run_liquidity
from pumpgrok.tools.onchain.authorities_tool import AuthoritiesIn, run_authorities
from pumpgrok.tools.onchain.deployer_history import DeployerHistoryIn, run_deployer_history
from pumpgrok.tools.onchain.lp_status import LpStatusIn, run_lp_status
from pumpgrok.tools.onchain.rpc import RpcClient
from pumpgrok.tools.onchain.token_metadata import TokenMetadataIn, run_token_metadata
from pumpgrok.tools.onchain.top_holders import TopHoldersIn, run_top_holders
from pumpgrok.tools.safety.checks import (
    ADVISORY_IDS,
    CHECK_IDS,
    REQUIRED_IDS,
    CheckId,
    CheckResult,
)
from pumpgrok.tools.safety.checks.authority import check_freeze_authority, check_mint_authority
from pumpgrok.tools.safety.checks.readers import (
    check_deployer_history,
    check_liquidity_depth,
    check_lp_status,
    check_token2022_extensions,
    check_top10_concentration,
)

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
    blind_checks: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    thresholds_used: dict[str, float] = Field(default_factory=dict)


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


@dataclass(frozen=True, slots=True)
class _Readings:
    """Typed reader payloads; ``None`` marks a reader that was skipped or degraded."""

    auth: dict[str, Any] | None
    lp: dict[str, Any] | None
    meta: dict[str, Any] | None
    top: dict[str, Any] | None
    dep: dict[str, Any] | None
    liq: dict[str, Any] | None


def resolve_thresholds(override: dict[str, float] | None) -> SafetyThresholds:
    """Merge a caller override over config defaults; unknown keys are refused."""
    if not override:
        return SafetyThresholds()
    unknown = sorted(set(override) - set(_KNOWN_THRESHOLD_KEYS))
    if unknown:
        raise DataStale(f"safety.score_report unknown threshold keys: {unknown}")
    return SafetyThresholds(**override)


def _blind(check_id: CheckId, weight: Decimal, reason: str) -> CheckResult:
    return CheckResult(
        id=check_id,
        status="blind",
        value=None,
        threshold=None,
        weight=weight,
        reason=reason,
    )


async def _fetch(call: Awaitable[dict[str, Any]]) -> dict[str, Any] | None:
    """Await one reader; a ``DataStale`` degrades to ``None`` (blind), never raises."""
    try:
        return await call
    except DataStale:
        return None


async def _read_all(inp: ScoreReportIn, rpc: RpcClient, runnable: list[CheckId]) -> _Readings:
    """Run only the readers the runnable checks need, in the fixed reader order."""
    needed: set[str] = set(runnable)
    auth = (
        await _fetch(run_authorities(AuthoritiesIn(mint=inp.mint), rpc))
        if {"mint_authority", "freeze_authority"} & needed
        else None
    )
    lp = (
        await _fetch(run_lp_status(LpStatusIn(mint=inp.mint, curve_account=inp.curve_account), rpc))
        if "lp_status" in needed
        else None
    )
    meta = (
        await _fetch(run_token_metadata(TokenMetadataIn(mint=inp.mint), rpc))
        if "token2022_extensions" in needed
        else None
    )
    top = (
        await _fetch(run_top_holders(TopHoldersIn(mint=inp.mint), rpc))
        if "top10_concentration" in needed
        else None
    )
    dep = (
        await _fetch(run_deployer_history(DeployerHistoryIn(creator=inp.creator or ""), rpc))
        if "deployer_history" in needed and inp.creator is not None
        else None
    )
    liq = (
        await _fetch(
            run_liquidity(
                LiquidityIn(
                    mint=inp.mint,
                    curve_account=inp.curve_account,
                    order_size_lamports=inp.intended_size_lamports,
                ),
                rpc,
            )
        )
        if "liquidity_depth" in needed
        else None
    )
    return _Readings(auth=auth, lp=lp, meta=meta, top=top, dep=dep, liq=liq)


def _reader_row(
    check_id: CheckId,
    reading: dict[str, Any] | None,
    evaluate: Callable[[dict[str, Any]], CheckResult],
    *,
    weight: Decimal,
    blind_reason: str,
    evidence: list[Evidence],
) -> CheckResult:
    """Score a check from its reader, or blind it; a live reading leaves evidence."""
    if reading is None:
        return _blind(check_id, weight, blind_reason)
    evidence.append(
        Evidence(check=check_id, source=SOLANA_RPC_SOURCE, slot=None, fetched_at=utcnow())
    )
    return evaluate(reading)


def _reader_rows(
    inp: ScoreReportIn,
    runnable: list[CheckId],
    readings: _Readings,
    active: SafetyThresholds,
    evidence: list[Evidence],
) -> list[CheckResult]:
    """Rows for the data-backed checks, in the stable report order."""
    rows: list[CheckResult] = []
    if "mint_authority" in runnable:
        rows.append(
            _reader_row(
                "mint_authority",
                readings.auth,
                check_mint_authority,
                weight=Decimal("0.15"),
                blind_reason="mint authority unreadable",
                evidence=evidence,
            )
        )
    if "freeze_authority" in runnable:
        rows.append(
            _reader_row(
                "freeze_authority",
                readings.auth,
                check_freeze_authority,
                weight=Decimal("0.15"),
                blind_reason="freeze authority unreadable",
                evidence=evidence,
            )
        )
    if "lp_status" in runnable:
        rows.append(
            _reader_row(
                "lp_status",
                readings.lp,
                check_lp_status,
                weight=Decimal("0.15"),
                blind_reason="curve account unreadable",
                evidence=evidence,
            )
        )
    if "top10_concentration" in runnable:
        rows.append(
            _reader_row(
                "top10_concentration",
                readings.top,
                lambda top: check_top10_concentration(top, active),
                weight=Decimal("0.15"),
                blind_reason="holder sample unreadable",
                evidence=evidence,
            )
        )
    if "deployer_history" in runnable:
        if inp.creator is None:
            rows.append(
                _blind(
                    "deployer_history",
                    Decimal("0.10"),
                    "creator not supplied; window unscanned",
                )
            )
        else:
            rows.append(
                _reader_row(
                    "deployer_history",
                    readings.dep,
                    check_deployer_history,
                    weight=Decimal("0.10"),
                    blind_reason="creator window unreadable",
                    evidence=evidence,
                )
            )
    if "token2022_extensions" in runnable:
        rows.append(
            _reader_row(
                "token2022_extensions",
                readings.meta,
                check_token2022_extensions,
                weight=Decimal("0.05"),
                blind_reason="mint metadata unreadable",
                evidence=evidence,
            )
        )
    if "liquidity_depth" in runnable:
        rows.append(
            _reader_row(
                "liquidity_depth",
                readings.liq,
                lambda liq: check_liquidity_depth(liq, inp.intended_size_lamports, active),
                weight=Decimal("0.15"),
                blind_reason="liquidity unreadable",
                evidence=evidence,
            )
        )
    return rows


def _advisory_rows(wanted: set[str], evidence: list[Evidence]) -> list[CheckResult]:
    """Advisory checks are blind by construction in Phase 3 and carry no weight."""
    rows: list[CheckResult] = []
    for check_id in CHECK_IDS:
        if check_id in ADVISORY_IDS and check_id in wanted:
            rows.append(
                CheckResult(
                    id=check_id,
                    status="blind",
                    value=None,
                    threshold=None,
                    weight=Decimal(0),
                    reason="no Phase-3 data source; advisory blind",
                )
            )
            evidence.append(
                Evidence(check=check_id, source="unwired", slot=None, fetched_at=utcnow())
            )
    return rows


def _score(rows: list[CheckResult]) -> Decimal:
    score = Decimal(100)
    for row in rows:
        if row.status == "warn":
            score -= _WARN_PENALTY
        elif row.status == "fail":
            score -= _FAIL_PENALTY
    return max(Decimal(0), score)


def _verdict(
    score: Decimal, forced_kill: bool, active: SafetyThresholds
) -> Literal["CLEAR", "CONDITIONAL", "KILL"]:
    if forced_kill or score < Decimal(str(active.kill_below_score)):
        return "KILL"
    if score < Decimal(str(active.conditional_below_score)):
        return "CONDITIONAL"
    return "CLEAR"


async def run_score_report(
    inp: ScoreReportIn,
    rpc: RpcClient,
    *,
    thresholds: SafetyThresholds | None = None,
) -> dict[str, Any]:
    """Compose the readers and return a validated ``ScoreReportOut`` payload."""
    active = thresholds if thresholds is not None else resolve_thresholds(inp.thresholds)
    wanted: set[str] = set(inp.checks) if inp.checks is not None else set(CHECK_IDS)
    unknown = sorted(wanted - set(CHECK_IDS))
    if unknown:
        raise DataStale(f"safety.score_report unknown check ids: {unknown}")
    runnable = [c for c in CHECK_IDS if c in wanted and c not in ADVISORY_IDS]

    evidence: list[Evidence] = []
    readings = await _read_all(inp, rpc, runnable)
    rows = _reader_rows(inp, runnable, readings, active, evidence)
    rows.extend(_advisory_rows(wanted, evidence))

    score = _score(rows)
    top = readings.top
    top5 = Decimal(str((top or {}).get("top5_share", "0")))
    hard_veto = bool(top is not None and top5 > Decimal(str(active.top5_share_veto)))
    blind_required = [r.id for r in rows if r.status == "blind" and r.id in REQUIRED_IDS]
    verdict = _verdict(score, hard_veto or bool(blind_required), active)

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
    async def _score_report(payload: ScoreReportIn) -> dict[str, Any]:
        return await run_score_report(payload, rpc, thresholds=thresholds)

    return _score_report
