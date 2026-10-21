"""onchain.deployer_history: creator wallet history from RPC (TOOL-002).

WHALE-only grant (R35); ``safety.score_report`` composes it in-process for
RUG. Counts come from ``getSignaturesForAddress`` inside the lookback
window: ``tokens_seen`` is a signature count, not an adjudicated token
count, and ``rugs``/``worst_pnl_pct`` stay unwired until the reputation
book lands (Phase 4+).
"""
from datetime import UTC, datetime

from pydantic import Field

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J5, SOLANA_RPC_SOURCE, MintStr, meta_now, utcnow
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError

_SIG_LIMIT = 100
_DAY_S = 86_400


class DeployerHistoryIn(ToolInput):
    """History for ``creator`` over the trailing ``lookback_days``."""

    creator: MintStr
    lookback_days: int = Field(default=30, ge=1, le=90)


class DeployerHistoryOut(ToolOutput):
    """Signature-window history; adjudicated fields stay unwired."""

    tokens_seen: int = Field(ge=0)
    tokens_bought: int = Field(ge=0)
    rugs: int = Field(ge=0)
    worst_pnl_pct: float | None = None
    is_known_bad: bool = False
    first_seen_at: datetime | None = None
    recent_signatures: list[str] = []


DEPLOYER_HISTORY_SPEC = ToolSpec(
    name="onchain.deployer_history",
    description=(
        "Creator wallet history from the RPC signature window; "
        "adjudicated rug fields are unwired pending the reputation book."
    ),
    input_model=DeployerHistoryIn,
    output_model=DeployerHistoryOut,
    side_effect=SideEffect.READ,
    timeout_s=20.0,
    retry=J5,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/deployer_history.py via getSignaturesForAddress",
)


async def run_deployer_history(inp: DeployerHistoryIn, rpc: RpcClient) -> dict:
    """Scan the signature window and return a validated typed payload."""
    try:
        sigs = await rpc.call("getSignaturesForAddress", [inp.creator, {"limit": _SIG_LIMIT}])
    except RpcError as exc:
        raise DataStale(f"onchain.deployer_history upstream failed creator={inp.creator}") from exc
    if not isinstance(sigs, list):
        raise DataStale(f"onchain.deployer_history malformed creator={inp.creator}")
    cutoff = utcnow().timestamp() - inp.lookback_days * _DAY_S
    kept: list[dict] = []
    for entry in sigs:
        if not isinstance(entry, dict) or not isinstance(entry.get("signature"), str):
            continue
        block_time = entry.get("blockTime")
        if isinstance(block_time, int) and block_time < cutoff:
            continue
        kept.append(entry)
    stamps = [e["blockTime"] for e in kept if isinstance(e.get("blockTime"), int)]
    out = {
        "tokens_seen": len(kept),
        "tokens_bought": 0,
        "rugs": 0,
        "worst_pnl_pct": None,
        "is_known_bad": False,
        "first_seen_at": datetime.fromtimestamp(min(stamps), UTC) if stamps else None,
        "recent_signatures": [e["signature"] for e in kept[:10]],
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
        ),
    }
    return DeployerHistoryOut.model_validate(out).model_dump()


def build_deployer_history_tool(rpc: RpcClient) -> Tool:
    """Bind ``onchain.deployer_history`` to one injected RPC client."""

    @tool(DEPLOYER_HISTORY_SPEC)
    async def _deployer_history(payload: DeployerHistoryIn) -> dict:
        return await run_deployer_history(payload, rpc)

    return _deployer_history
