# interfaces - Core Python interfaces for the pumpgrok desk

Tracker: SPE-17999 https://linear.app/swcstudio/issue/SPE-17999/n3-target-bot-roster-skill-manifests-tool-catalog-core-interfaces | Notion https://app.notion.com/p/3ffbc1a0c7ae8190b46ced6823fa3c90?pvs=204

Design document only. Defines the Python 3.12 signatures (D1) for `src/pumpgrok/core/`
that `docs/ROSTER.md` and `docs/TOOL_CATALOG.md` instantiate, the skills manifest shape,
the `SKILL.md` convention to apply to the 23 existing skills, the new skills list, and
the tests that prove least privilege.

Libraries: pydantic v2 for every model, `typing.Protocol` for behaviour contracts,
`abc.ABC` only where shared implementation is useful (D5). `mypy --strict` on `src/`
(D5), hence explicit return types everywhere and no `Any` in public signatures except
schema payloads.

## 1. Module map

| Module | Contents |
|---|---|
| `src/pumpgrok/core/side_effect.py` | `SideEffect` enum, ordering |
| `src/pumpgrok/core/errors.py` | `PumpgrokError`, `PermissionDenied`, `LiveGateError`, `ToolTimeout`, `ToolRateLimited`, `LedgerUnavailable`, `DataStale` |
| `src/pumpgrok/core/correlation.py` | `CorrelationId`, contextvar, `bind()`, `current()` |
| `src/pumpgrok/core/idempotency.py` | `derive_idempotency_key` |
| `src/pumpgrok/core/tool.py` | `ToolSpec`, `ToolMeta`, `RetryPolicy`, `Tool` protocol, `tool()` decorator |
| `src/pumpgrok/core/datasource.py` | `Freshness`, `Health`, `DataSource` protocol |
| `src/pumpgrok/core/adapter.py` | `ExecutionAdapter` protocol, order/fill/position models |
| `src/pumpgrok/core/skill.py` | `SkillManifest`, `Skill` protocol |
| `src/pumpgrok/core/bot.py` | `RiskBudget`, `BotManifest`, `Bot` protocol, `ApprovalRecord` |
| `src/pumpgrok/core/registry.py` | `ToolRegistry`, `GrantAudit` |
| `src/pumpgrok/core/__init__.py` | re-exports |

Everything below is presented as one listing so it can be pasted into a single file and
parsed; the implementation splits it along the table above. Ownership: `bot-02-risk`
(`docs/ROSTER.md` section 7).

## 2. The listing

```python
"""pumpgrok core interfaces (design listing; split per docs/design/interfaces.md section 1)."""

from __future__ import annotations

import contextvars
import enum
import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

log = logging.getLogger("pumpgrok.core")


# ---------------------------------------------------------------------------
# 2.1 Side effects
# ---------------------------------------------------------------------------


class SideEffect(enum.StrEnum):
    """Side-effect class of a tool. Ordered: READ < PAPER_WRITE < LIVE_WRITE.

    LIVE_WRITE exists only so the registry can name what it refuses (D3, D4).
    """

    READ = "read"
    PAPER_WRITE = "paper-write"
    LIVE_WRITE = "live-write"

    @property
    def rank(self) -> int:
        return _SIDE_EFFECT_RANK[self]

    def exceeds(self, other: SideEffect) -> bool:
        return self.rank > other.rank


_SIDE_EFFECT_RANK: dict[SideEffect, int] = {
    SideEffect.READ: 0,
    SideEffect.PAPER_WRITE: 1,
    SideEffect.LIVE_WRITE: 2,
}

# The highest side effect any seat may ever be granted. Not configurable.
MAX_GRANTABLE_SIDE_EFFECT: SideEffect = SideEffect.PAPER_WRITE


# ---------------------------------------------------------------------------
# 2.2 Errors
# ---------------------------------------------------------------------------


class PumpgrokError(Exception):
    """Base class. `code` is stable and machine-readable; it is what the journal stores."""

    code: ClassVar[str] = "pumpgrok_error"

    def __init__(self, message: str, **fields: Any) -> None:
        super().__init__(message)
        self.message = message
        self.fields: dict[str, Any] = fields


class PermissionDenied(PumpgrokError):
    """Registry refused to hand a tool to a bot (not in roster, or side effect too high)."""

    code = "permission_denied"


class LiveGateError(PermissionDenied):
    """A live-write path was reached. Always raised; never caught by trading code."""

    code = "live_gate"


class ToolTimeout(PumpgrokError):
    code = "tool_timeout"


class ToolRateLimited(PumpgrokError):
    code = "tool_rate_limited"


class LedgerUnavailable(PumpgrokError):
    code = "ledger_unavailable"


class DataStale(PumpgrokError):
    code = "data_stale"


# ---------------------------------------------------------------------------
# 2.3 Correlation id propagation
# ---------------------------------------------------------------------------


class CorrelationId(str):
    """Opaque id spanning signal -> decision -> order -> fill (spec OBSERVABILITY).

    Format: `<ticket or 'desk'>:<uuid4 hex[:16]>`. Children append `/<step>`.
    """

    __slots__ = ()

    @classmethod
    def new(cls, root: str = "desk") -> CorrelationId:
        return cls(f"{root}:{uuid.uuid4().hex[:16]}")

    def child(self, step: str) -> CorrelationId:
        return CorrelationId(f"{self}/{step}")


_correlation: contextvars.ContextVar[CorrelationId | None] = contextvars.ContextVar(
    "pumpgrok_correlation", default=None
)


def current_correlation() -> CorrelationId:
    """Return the ambient id, creating a desk-rooted one if none is bound."""
    cid = _correlation.get()
    if cid is None:
        cid = CorrelationId.new()
        _correlation.set(cid)
    return cid


class bind_correlation:
    """Context manager: bind an id for the dynamic extent of a bot cycle or tool call.

    The JSON log formatter (src/pumpgrok/logging) reads `_correlation` and stamps every
    record with `correlation_id`; the registry stamps every tool input and output.
    """

    def __init__(self, cid: CorrelationId) -> None:
        self._cid = cid
        self._token: contextvars.Token[CorrelationId | None] | None = None

    def __enter__(self) -> CorrelationId:
        self._token = _correlation.set(self._cid)
        return self._cid

    def __exit__(self, *exc: object) -> None:
        assert self._token is not None
        _correlation.reset(self._token)


# ---------------------------------------------------------------------------
# 2.4 Idempotency keys
# ---------------------------------------------------------------------------


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def derive_idempotency_key(
    tool: str,
    bot: str,
    payload: Mapping[str, Any],
    *,
    scope: str | None = None,
) -> str:
    """sha256 over (tool, bot, scope, canonical payload) -> 32 hex chars.

    `scope` is the logical unit that must be executed at most once: for exec.place it is
    `f"{ticket_id}:{side}"`; for journal.append it is `ticket_id`; for notify.alert it is
    the UTC minute. Fields named `correlation_id` and `idempotency_key` are excluded so
    that a retry under a new correlation id still collapses onto the first attempt.
    """
    body = {k: v for k, v in payload.items() if k not in ("correlation_id", "idempotency_key")}
    digest = hashlib.sha256(
        canonical_json({"tool": tool, "bot": bot, "scope": scope, "payload": body}).encode()
    ).hexdigest()
    return digest[:32]


# ---------------------------------------------------------------------------
# 2.5 Tool
# ---------------------------------------------------------------------------


class RetryPolicy(BaseModel):
    """tenacity policy (D5). `attempts=1` means no retry."""

    model_config = ConfigDict(frozen=True)

    attempts: int = Field(default=1, ge=1, le=10)
    base_s: float = Field(default=0.5, ge=0.0)
    max_s: float = Field(default=5.0, ge=0.0)
    jitter: bool = True
    retry_on: tuple[str, ...] = ("timeout", "5xx", "429")

    @classmethod
    def none(cls) -> RetryPolicy:
        return cls(attempts=1)


class ToolMeta(BaseModel):
    """Envelope every tool output carries (docs/TOOL_CATALOG.md section 0)."""

    source: str
    fetched_at: datetime
    freshness_s: float = Field(ge=0.0)
    correlation_id: str
    stale: bool = False
    reason: str | None = None


class ToolInput(BaseModel):
    """Base for every tool input model. `extra='forbid'` mirrors additionalProperties: false."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_id: str | None = None


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: ToolMeta


class ToolSpec(BaseModel):
    """Static description of one tool. One instance per entry in docs/TOOL_CATALOG.md."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$")
    description: str = Field(min_length=10, max_length=1000)
    input_model: type[ToolInput]
    output_model: type[ToolOutput]
    side_effect: SideEffect
    timeout_s: float = Field(gt=0.0, le=300.0)
    retry: RetryPolicy = Field(default_factory=RetryPolicy.none)
    rate_limit_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    requires_approval: bool = False  # roster gate g6: approval_id required in input
    idempotent: bool = False  # True for every write; input carries or derives a key
    backend: str = Field(min_length=1)  # endpoint or module path, for the audit log

    @property
    def capability(self) -> str:
        """Namespace prefix: 'market' for 'market.price'."""
        return self.name.split(".", 1)[0]

    @property
    def roster_name(self) -> str:
        """Gateway spelling: 'market_price' (G-7 TOOL_NAME_RE)."""
        return self.name.replace(".", "_")

    @model_validator(mode="after")
    def _writes_are_idempotent(self) -> Self:
        if self.side_effect is not SideEffect.READ and not self.idempotent:
            raise ValueError(f"{self.name}: write tools must be idempotent")
        if self.side_effect is SideEffect.READ and self.requires_approval:
            raise ValueError(f"{self.name}: read tools cannot require approval")
        return self

    def input_json_schema(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema["additionalProperties"] = False
        return schema


@runtime_checkable
class Tool(Protocol):
    """A callable with a spec. Implementations are plain async functions wrapped by `tool()`."""

    spec: ToolSpec

    async def __call__(self, payload: ToolInput, /) -> ToolOutput: ...


def tool(spec: ToolSpec) -> Callable[[Callable[[Any], Awaitable[Any]]], Tool]:
    """Decorator that attaches a ToolSpec to an async function and validates I/O.

    The registry is the only caller of the returned object; it applies timeout, retry,
    rate limit, correlation stamping and the audit log around it.
    """

    def wrap(fn: Callable[[Any], Awaitable[Any]]) -> Tool:
        class _BoundTool:
            def __init__(self) -> None:
                self.spec = spec

            async def __call__(self, payload: ToolInput, /) -> ToolOutput:
                if not isinstance(payload, spec.input_model):
                    raise TypeError(f"{spec.name}: expected {spec.input_model.__name__}")
                result = await fn(payload)
                return spec.output_model.model_validate(result)

        return _BoundTool()

    return wrap


# ---------------------------------------------------------------------------
# 2.6 DataSource
# ---------------------------------------------------------------------------


class Freshness(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    age_s: float = Field(ge=0.0)
    max_age_s: float = Field(gt=0.0)

    @property
    def stale(self) -> bool:
        return self.age_s > self.max_age_s


class HealthStatus(enum.StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class Health(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: HealthStatus
    checked_at: datetime
    consecutive_failures: int = Field(ge=0)
    breaker_open: bool = False
    cooldown_until: datetime | None = None
    detail: str | None = None


@runtime_checkable
class DataSource(Protocol):
    """A market, on-chain, or social feed (D8 sources only).

    `fetch` must never raise on upstream failure; it returns the cached value with
    `Freshness.stale == True` or raises DataStale when no cache exists.
    """

    name: str  # 'pumpfun_rest' | 'pumpportal_ws' | 'jupiter_lite' | 'solana_rpc' | 'xai_grok'
    rate_limit_key: str

    async def fetch(self, request: Mapping[str, Any], *, max_age_s: float) -> tuple[Any, Freshness]: ...

    def freshness(self, key: str) -> Freshness | None: ...

    async def health(self) -> Health: ...

    async def aclose(self) -> None: ...


# ---------------------------------------------------------------------------
# 2.7 ExecutionAdapter
# ---------------------------------------------------------------------------


class Side(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str = Field(pattern=r"^SOL-\d{8}-\d{3}$")
    mint: str = Field(min_length=32, max_length=44)
    side: Side
    size_sol: float | None = Field(default=None, gt=0.0)
    token_amount: float | None = Field(default=None, gt=0.0)
    max_slippage_bps: int = Field(ge=1, le=10_000)
    approval_id: str = Field(pattern=r"^apr-[a-f0-9]{16}$")
    quote_id: str | None = None
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{32}$")
    correlation_id: str

    @model_validator(mode="after")
    def _size_matches_side(self) -> Self:
        if self.side is Side.BUY and self.size_sol is None:
            raise ValueError("buy requires size_sol")
        if self.side is Side.SELL and self.token_amount is None:
            raise ValueError("sell requires token_amount")
        return self


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    quote_id: str
    in_amount: int
    out_amount: int
    other_amount_threshold: int
    price_impact_pct: float
    route_plan: list[dict[str, Any]]
    context_slot: int | None
    source: Literal["jupiter", "curve"]
    expires_at: datetime


class SimulationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    would_fill: bool
    fill_kind: Literal["full", "partial", "rejected"]
    expected_price: float
    expected_out: float
    price_impact_pct: float
    fee_sol: float
    priority_fee_sol: float
    liquidity_ratio: float
    rejection_reason: str | None
    latency_ms_estimate: int


class FillStatus(enum.StrEnum):
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class Fill(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    status: FillStatus
    signature: str = Field(pattern=r"^paper:[a-f0-9]{32}$")  # never a real signature
    filled_sol: float
    filled_tokens: float
    avg_price: float
    realised_slippage_bps: int
    fee_sol: float
    priority_fee_sol: float
    route: str
    ledger_event_id: int
    reason: str | None = None


class Position(BaseModel):
    """Mirror of vendor models.Position (vendor/grokbot-pumpfun/src/models.py:243) plus marks."""

    model_config = ConfigDict(frozen=True)

    ticket_id: str
    mint: str
    entry_price: float
    peak_price: float
    sol_spent: float
    token_amount: float
    opened_at: datetime
    mark_price: float | None = None
    unrealised_pnl_sol: float | None = None
    unrealised_pnl_pct: float | None = None
    hold_seconds: int = 0


class ExecutionMode(enum.StrEnum):
    PAPER = "paper"
    LIVE = "live"


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Common interface for PaperAdapter (enabled) and live stubs (disabled)."""

    mode: ClassVar[ExecutionMode]
    venue: ClassVar[str]  # 'paper' | 'jupiter' | 'pumpfun'

    async def quote(self, input_mint: str, output_mint: str, amount: int, slippage_bps: int) -> Quote: ...

    async def simulate(self, request: OrderRequest) -> SimulationResult: ...

    async def place(self, request: OrderRequest) -> Fill: ...

    async def cancel(self, order_id: str, ticket_id: str, idempotency_key: str) -> bool: ...

    async def positions(self, mint: str | None = None) -> Sequence[Position]: ...


class LiveAdapterStub:
    """Base for every live adapter. Every method raises; nothing here can be reached in
    paper mode because ToolRegistry refuses LIVE_WRITE, and nothing here submits a
    transaction even in live mode until LiveGate.check() is empty (D4).

    Subclasses: LiveJupiterAdapter, LivePumpfunAdapter under src/pumpgrok/execution/live/.
    """

    mode: ClassVar[ExecutionMode] = ExecutionMode.LIVE
    venue: ClassVar[str] = "disabled"

    def __init__(self, gate: LiveGate) -> None:
        unmet = gate.check()
        if unmet:
            raise LiveGateError("live adapter construction refused", unmet=list(unmet))
        raise LiveGateError("live adapters are not implemented in this release", unmet=[])

    async def quote(self, input_mint: str, output_mint: str, amount: int, slippage_bps: int) -> Quote:
        raise LiveGateError("live quote disabled")

    async def simulate(self, request: OrderRequest) -> SimulationResult:
        raise LiveGateError("live simulate disabled")

    async def place(self, request: OrderRequest) -> Fill:
        raise LiveGateError("live place disabled")

    async def cancel(self, order_id: str, ticket_id: str, idempotency_key: str) -> bool:
        raise LiveGateError("live cancel disabled")

    async def positions(self, mint: str | None = None) -> Sequence[Position]:
        raise LiveGateError("live positions disabled")


class LiveGate(Protocol):
    """D4 preconditions. `check()` returns the names of every UNMET precondition; the
    startup path prints the list and exits non-zero when mode == live and it is non-empty.
    Precondition ids: min_paper_days, performance_thresholds, PUMPGROK_LIVE_ENABLE,
    wallet_allowlist, notional_cap, signed_human_confirmation.
    """

    def check(self) -> Sequence[str]: ...


# ---------------------------------------------------------------------------
# 2.8 Skill
# ---------------------------------------------------------------------------


class SkillPermissions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_side_effect: SideEffect = SideEffect.READ
    network: bool = True
    filesystem: Literal["none", "var", "repo"] = "none"

    @field_validator("max_side_effect")
    @classmethod
    def _never_live(cls, v: SideEffect) -> SideEffect:
        if v is SideEffect.LIVE_WRITE:
            raise ValueError("a skill may never declare live-write")
        return v


class SkillManifest(BaseModel):
    """Frontmatter of skills/<name>/SKILL.md (section 3) parsed into a model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,60}$")
    description: str = Field(min_length=1, max_length=1024)  # scripts/check.sh:48-52
    bots: list[str] = Field(min_length=1)  # seat ids or ['all']
    gates: list[str] = Field(default_factory=list)  # ['G-2', ...]
    required_tools: list[str] = Field(default_factory=list)  # catalog names
    required_data: list[str] = Field(default_factory=list)  # DataSource names
    permissions: SkillPermissions = Field(default_factory=SkillPermissions)
    fixtures: list[str] = Field(default_factory=list)  # tests/fixtures/** used by the skill tests

    @field_validator("bots")
    @classmethod
    def _bot_ids(cls, v: list[str]) -> list[str]:
        for b in v:
            if b != "all" and not b.startswith("bot-0"):
                raise ValueError(f"bad bot id {b!r}")
        return v


@runtime_checkable
class Skill(Protocol):
    """Tools plus decision logic. Unit-testable with recorded fixtures and no network:
    the registry handed to `run` is a fixture registry in tests.
    """

    manifest: ClassVar[SkillManifest]

    async def run(self, registry: ToolRegistry, bot: BotManifest, context: Mapping[str, Any]) -> Mapping[str, Any]: ...


# ---------------------------------------------------------------------------
# 2.9 Bot
# ---------------------------------------------------------------------------


class RiskBudget(BaseModel):
    """Per-seat ceilings. Desk-level values come from config (D6, all REVIEW)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_position_pct: float = Field(ge=0.0, le=100.0)
    max_token_pct: float = Field(ge=0.0, le=100.0)
    max_daily_loss_pct: float = Field(ge=0.0, le=100.0)
    max_drawdown_pct: float = Field(ge=0.0, le=100.0)
    max_open_positions: int = Field(ge=0)

    @property
    def may_open_exposure(self) -> bool:
        return self.max_position_pct > 0.0 and self.max_open_positions > 0


class Schedule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["cron", "interval", "event"]
    expr: str  # cron expression, 'every 15m', or event kind


class ToolGrant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str  # catalog name, e.g. 'exec.place'
    side_effect: SideEffect  # the class the seat is granted for this tool

    @field_validator("side_effect")
    @classmethod
    def _never_live(cls, v: SideEffect) -> SideEffect:
        if v.exceeds(MAX_GRANTABLE_SIDE_EFFECT):
            raise ValueError("live-write can never be granted")
        return v


class BotManifest(BaseModel):
    """One per seat (docs/ROSTER.md section 5). Loaded from contracts/tool-rosters/<seat>.yaml
    (allowed_tools) plus prompts/bot-0N-<seat>.xml metadata (the rest).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^bot-0[0-9]-[a-z]+$")
    display: str
    channel: Literal["Trading Floor", "DM"]
    purpose: str
    inputs: list[str]
    outputs: list[str]
    skills: list[str]
    allowed_tools: list[ToolGrant]
    risk_budget: RiskBudget
    forbidden: list[str]
    fail_safe: str
    schedule: list[Schedule]
    escalation: list[str]
    owned_paths: list[str]
    receipts_dir: str
    prompt_source: str
    writes_to_exchange: bool = False

    def grant_for(self, tool_name: str) -> ToolGrant | None:
        for g in self.allowed_tools:
            if g.name == tool_name:
                return g
        return None

    @model_validator(mode="after")
    def _exec_writes_only_for_writers(self) -> Self:
        paper_writers = {"bot-04-sniper", "bot-06-exit"}
        for g in self.allowed_tools:
            if g.name.startswith("exec.") and g.side_effect is SideEffect.PAPER_WRITE:
                if self.id not in paper_writers:
                    raise ValueError(f"{self.id} may not hold paper-write exec tools")
                if not self.writes_to_exchange:
                    raise ValueError(f"{self.id} holds exec writes but writes_to_exchange is false")
            if g.name == "risk.kill_switch" and self.id != "bot-02-risk":
                raise ValueError(f"{self.id} may not hold risk.kill_switch")
            if g.name == "portfolio.ledger_write":
                raise ValueError("portfolio.ledger_write is adapter-only, never a seat grant")
        return self


@runtime_checkable
class Bot(Protocol):
    manifest: ClassVar[BotManifest]

    async def cycle(self, registry: ToolRegistry, trigger: Mapping[str, Any]) -> Mapping[str, Any]: ...

    async def heartbeat(self) -> Health: ...


class ApprovalRecord(BaseModel):
    """Parsed human approval phrase `approve <ticket> <mint> <size> <slippage>`
    (rules/pumpgrok-team.mdc:28; agents/sniper.md:42), or a pre-authorised exit rule,
    or the kill-switch clear signature. `id` is what exec.place / risk.kill_switch
    receive as approval_id. Stored as a ledger event; never editable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^apr-[a-f0-9]{16}$")
    kind: Literal["human_buy", "human_sell", "exit_rule", "killswitch_clear", "live_gate"]
    ticket_id: str | None = Field(default=None, pattern=r"^SOL-\d{8}-\d{3}$")
    mint: str | None = None
    size_sol: float | None = None
    max_slippage_bps: int | None = None
    approved_by: str  # 'human:<name>' or exit rule id; never a seat id for human_* kinds
    raw_message: str
    at: datetime
    consumed: bool = False  # single-send: one approval, one order

    @classmethod
    def derive_id(cls, raw_message: str, at: datetime) -> str:
        return "apr-" + hashlib.sha256(f"{raw_message}|{at.isoformat()}".encode()).hexdigest()[:16]

    @model_validator(mode="after")
    def _human_kinds_need_human(self) -> Self:
        if self.kind in ("human_buy", "human_sell", "killswitch_clear", "live_gate"):
            if not self.approved_by.startswith("human:"):
                raise ValueError("human approval must be signed by a human, not a seat")
            if self.kind in ("human_buy", "human_sell") and (
                self.ticket_id is None or self.mint is None or self.size_sol is None or self.max_slippage_bps is None
            ):
                raise ValueError("human trade approval must carry ticket, mint, size, slippage")
        return self

    def matches(self, request: OrderRequest) -> bool:
        return (
            self.ticket_id == request.ticket_id
            and self.mint == request.mint
            and self.max_slippage_bps == request.max_slippage_bps
            and (self.size_sol == request.size_sol if request.side is Side.BUY else True)
            and not self.consumed
        )


# ---------------------------------------------------------------------------
# 2.10 ToolRegistry
# ---------------------------------------------------------------------------


class GrantAudit(BaseModel):
    """One row per resolution attempt. Every LIVE_WRITE attempt is a row with
    `allowed=False` and is also emitted as a critical alert (spec SECURITY_AND_VALIDATION).
    """

    at: datetime
    bot: str
    tool: str
    requested_side_effect: SideEffect
    allowed: bool
    reason: str
    correlation_id: str


class ToolRegistry:
    """Bots discover tools by capability and permission (spec TOOL_QUALITY_BAR).

    Invariants (tests/test_registry_least_privilege.py):
      R1 find() raises PermissionDenied unless the tool is in the bot's allowed_tools.
      R2 find() raises PermissionDenied if the tool's side_effect exceeds the grant's.
      R3 find() raises LiveGateError for any LIVE_WRITE tool regardless of roster,
         max_side_effect, or config mode. There is no argument that unlocks it.
      R4 Every refusal is appended to the audit log before the exception propagates.
      R5 A tool whose spec.requires_approval is True is wrapped so that
         risk.check_limits runs and the ApprovalRecord is matched and consumed
         before the underlying callable executes.
    """

    def __init__(self, *, audit_sink: Callable[[GrantAudit], None], limits_checker: Callable[[OrderRequest, str], Awaitable[bool]]) -> None:
        self._tools: dict[str, Tool] = {}
        self._audit = audit_sink
        self._check_limits = limits_checker

    # -- registration -------------------------------------------------------

    def register(self, tool_obj: Tool) -> None:
        name = tool_obj.spec.name
        if name in self._tools:
            raise ValueError(f"duplicate tool {name}")
        if tool_obj.spec.side_effect is SideEffect.LIVE_WRITE:
            # Registered so attempts can be audited; never resolvable (R3).
            log.warning("registering live-write tool %s as refuse-only", name)
        self._tools[name] = tool_obj

    def register_all(self, tools: Iterable[Tool]) -> None:
        for t in tools:
            self.register(t)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def spec(self, name: str) -> ToolSpec:
        return self._tools[name].spec

    # -- resolution ---------------------------------------------------------

    def find(
        self,
        capability: str,
        *,
        max_side_effect: SideEffect,
        bot: BotManifest,
    ) -> Tool:
        """Resolve `capability` ('market.price' or a namespace prefix 'market') for `bot`.

        A namespace prefix returns the first granted tool in that namespace whose side
        effect does not exceed `max_side_effect`; an exact name must match exactly.
        """
        cid = current_correlation()
        candidates = [t for n, t in self._tools.items() if n == capability or n.startswith(capability + ".")]
        if not candidates:
            self._refuse(bot, capability, max_side_effect, "unknown_tool", cid)
        for t in sorted(candidates, key=lambda t: t.spec.name):
            spec = t.spec
            if spec.side_effect is SideEffect.LIVE_WRITE:
                self._refuse(bot, spec.name, spec.side_effect, "live_write_never_resolvable", cid, live=True)
            grant = bot.grant_for(spec.name)
            if grant is None:
                if capability == spec.name:
                    self._refuse(bot, spec.name, spec.side_effect, "not_in_roster", cid)
                continue
            if spec.side_effect.exceeds(grant.side_effect):
                self._refuse(bot, spec.name, spec.side_effect, "exceeds_grant", cid)
            if spec.side_effect.exceeds(max_side_effect):
                self._refuse(bot, spec.name, spec.side_effect, "exceeds_requested_max", cid)
            self._audit(GrantAudit(at=datetime.now(UTC), bot=bot.id, tool=spec.name, requested_side_effect=spec.side_effect, allowed=True, reason="ok", correlation_id=cid))
            return self._wrap(t, bot)
        self._refuse(bot, capability, max_side_effect, "no_granted_tool_in_namespace", cid)
        raise AssertionError("unreachable")

    def _refuse(self, bot: BotManifest, tool_name: str, se: SideEffect, reason: str, cid: str, *, live: bool = False) -> None:
        self._audit(GrantAudit(at=datetime.now(UTC), bot=bot.id, tool=tool_name, requested_side_effect=se, allowed=False, reason=reason, correlation_id=cid))
        if live:
            raise LiveGateError(f"{bot.id} attempted live-write tool {tool_name}", tool=tool_name, bot=bot.id)
        raise PermissionDenied(f"{bot.id} may not resolve {tool_name}: {reason}", tool=tool_name, bot=bot.id, reason=reason)

    def _wrap(self, t: Tool, bot: BotManifest) -> Tool:
        """Apply timeout, retry, rate limit, correlation stamping, idempotency and, for
        approval-gated tools, the limits/approval check (R5). Returns a Tool.
        """
        spec = t.spec
        check_limits = self._check_limits

        class _Guarded:
            def __init__(self) -> None:
                self.spec = spec

            async def __call__(self, payload: ToolInput, /) -> ToolOutput:
                cid = current_correlation().child(spec.name)
                with bind_correlation(cid):
                    if spec.requires_approval:
                        req = OrderRequest.model_validate(payload.model_dump() | {"correlation_id": str(cid)})
                        if not await check_limits(req, bot.id):
                            raise PermissionDenied("risk.check_limits refused", tool=spec.name, bot=bot.id)
                    # timeout / retry / rate limit applied here by the implementation
                    return await t(payload)

        return _Guarded()
```

## 3. Skills manifest YAML shape and the SKILL.md convention

The frontmatter of `skills/<name>/SKILL.md` IS the manifest; it is parsed into
`SkillManifest` by `pumpgrok doctor` and by `tests/test_skill_manifests.py`. This keeps
`scripts/check.sh` rules intact: `name` equals the directory basename
(`scripts/check.sh:44-46`), `description` non-empty and at most 1024 chars
(`check.sh:48-52`), body at most 350 lines (`check.sh:53-55`), no emoji
(`check.sh:140-146`). The programming-desk fields `bots` and `gates`
(`programming-desk/skills/verification-receipts/SKILL.md:1-6`) are added; pumpgrok adds
`required_tools`, `required_data`, `permissions`, `fixtures`.

```yaml
---
name: paper-broker
description: How SNIPER and EXIT place exactly one paper order per approved ticket through exec.quote, exec.simulate and exec.place, and how to report UNKNOWN RESULT. Never a live transaction.
bots: [bot-04-sniper, bot-06-exit]
gates: [G-2, G-6]
required_tools: [exec.quote, exec.simulate, exec.place, exec.cancel, exec.positions, market.price, onchain.priority_fee]
required_data: [jupiter_lite, pumpfun_rest, solana_rpc]
permissions:
  max_side_effect: paper-write
  network: true
  filesystem: var
fixtures: [tests/fixtures/replay/pumpfun-2026-09-01/, tests/fixtures/tools/exec/]
---
```

Body convention (programming-desk, `scout-programming-desk.md:154`), applied to every
existing and new skill:

```
# <Title>

## L1 - Summary
One paragraph plus a decision tree in a fenced block.

## L2 - Method
### S1 ... ### Sn   numbered steps; every command is a `pumpgrok ...` CLI or a catalog tool name.

## Failure modes
| Symptom | Cause | Action |

## References
file:line citations into docs/, contracts/, src/.
```

### 3.1 Upgrade table for the 23 existing skills

Sizes and stub flags from `scout-pumpgrok-pack.md:47-71`. `bots` lists are the union of
`agents/*.md` frontmatter and `hermes/profiles.yaml` (`scout-pumpgrok-pack.md:41,43`),
renamed to seat ids. Every skill gains the four new frontmatter fields and the L1/L2 body.

| Skill | bots | gates | required_tools | Upgrade |
|---|---|---|---|---|
| browser-ops | bot-07-shill | [] | [] | Keep 4 rules + NEVERs; add untrusted-content handling for metadata URLs |
| desk-execution-protocol | bot-04-sniper, bot-06-exit | [G-2, G-6] | [exec.quote, exec.simulate, exec.place, onchain.priority_fee] | Replace `tools/jupiter_quote.py`/`priority_fee.py` commands with `pumpgrok paper buy|sell` and tool names; keep 6-item checklist and UNKNOWN RESULT |
| desk-folders-and-journal | bot-00-chief, bot-09-journal | [G-2] | [journal.append, portfolio.ledger_read] | Replace `/workspace/trading-desk/` tree with `var/` ledger + JSONL export; append-only rule enforced by ledger |
| desk-incident-response | bot-00-chief, bot-02-risk | [G-2] | [risk.kill_switch, risk.halt_status, notify.alert] | Expand the 6 one-line playbooks into L2 steps citing runbooks |
| desk-monitoring | bot-00-chief, bot-05-rug | [] | [risk.halt_status, portfolio.exposure, exec.positions] | DESK STATUS block sourced from tools, not memory |
| desk-operating-model | all | [] | [] | Keep constitution verbatim; roles become 10 seats; engagement levels research/paper/live with the live gate reference |
| desk-post-trade-review | bot-09-journal, bot-06-exit | [G-2] | [portfolio.ledger_read, portfolio.pnl, journal.append] | Grades A/B/C/F and Win/Scratch/Loss become `journal.append kind=review` fields |
| desk-risk-limits | bot-02-risk, bot-00-chief | [G-2] | [risk.check_limits] | 6-question interview writes `config/paper.toml` risk section via a human-signed change, not free text |
| desk-strategy-lab | bot-06-exit, bot-08-signal | [G-2] | [exec.simulate, journal.append] | Paper mode is the default; rule changes go through `replay-and-backtest` first |
| desk-trade-lifecycle | bot-00-chief, bot-01-scout | [G-2] | [journal.append] | `tools/ticket_helper.py next|create` -> `pumpgrok ticket next|create|list`; 9 stages map to event kinds |
| discovery-tools | bot-01-scout, bot-03-whale, bot-07-shill | [] | [market.trades, market.liquidity, onchain.token_metadata] | LEAD schema unchanged; add data-source freshness rules |
| grokbot-pipeline | all | [] | [] | Shrink: engine is ported into `src/pumpgrok/engine`; keep provenance/pin, 9-stage to seat mapping, evidence discipline; `pipeline_evidence.py` retired |
| hermes-cron-desk | bot-00-chief, bot-01-scout, bot-02-risk, bot-05-rug, bot-09-journal | [] | [desk.brief, risk.halt_status] | Cron prompts become thin wrappers over `pumpgrok <seat> <verb>` |
| holder-and-flow-analysis | bot-03-whale, bot-02-risk | [] | [onchain.top_holders, onchain.large_transfers, market.holders_snapshot] | `holder_check.py` -> tools; LP exclusion documented |
| jupiter-routing | bot-04-sniper, bot-06-exit | [G-6] | [exec.quote, onchain.priority_fee] | Commands -> tools; `--max-micro` cap now real (`max_micro_lamports`) |
| position-monitoring | bot-05-rug, bot-06-exit | [] | [onchain.lp_status, onchain.large_transfers, onchain.authorities, exec.positions] | 5 red flags -> `pumpgrok rug watch` checks; alert schema -> `alert.schema.json` |
| pumpgrok-setup | bot-00-chief | [G-7] | [desk.doctor] | Pointer to SETUP.md stays; receipt schema -> verification-receipts |
| risk-audit | bot-02-risk, bot-05-rug | [G-2] | [safety.score_report, onchain.authorities, onchain.top_holders] | `authority_check.py` -> `safety.score_report`; verdict schema unchanged; RUG runs, RISK rules |
| social-sentiment | bot-07-shill | [] | [onchain.token_metadata, market.trades] | Add detection method, D7 boundary, no posting |
| solana-api-reference | bot-04-sniper | [] | [] | Keep as reference; link to catalog backends |
| solana-market-data | bot-01-scout, bot-02-risk, bot-03-whale, bot-04-sniper, bot-05-rug, bot-08-signal | [] | [market.price, market.liquidity, market.trades] | 4 sources -> D8 sources with endpoints |
| solana-rpc-and-wallet | bot-02-risk, bot-04-sniper | [G-3] | [onchain.priority_fee] | Wallet rules unchanged; RPC failover + rate limits documented; cross-link key-custody |
| tool-connections | bot-00-chief | [] | [] | 7 sites stay; wallet hand-off stays human-only |

### 3.2 New skills

| Skill | bots | gates | required_tools | Purpose |
|---|---|---|---|---|
| verification-receipts | all | [G-2] | [desk.receipt_check] | Receipt before any completion claim; copied from programming-desk and extended with ledger-query evidence |
| paper-broker | bot-04-sniper, bot-06-exit | [G-2, G-6] | [exec.*, market.price, onchain.priority_fee] | One paper order per approved ticket; UNKNOWN RESULT handling |
| replay-and-backtest | bot-08-signal, bot-06-exit | [G-2] | [portfolio.ledger_read] | `pumpgrok run --replay <dir>` against `tests/fixtures/replay/`; deterministic, same code path |
| live-gate-procedure | bot-02-risk, bot-00-chief | [G-2, G-6] | [risk.halt_status] | The documented, separate procedure for D4 preconditions; nothing in it flips a flag |
| kill-switch | bot-02-risk, bot-00-chief | [G-2, G-6] | [risk.kill_switch, risk.halt_status, notify.alert] | Set/clear/flatten via env, file, command; who may clear |
| rpc-hygiene | bot-01-scout, bot-02-risk, bot-03-whale, bot-04-sniper, bot-05-rug, bot-06-exit | [] | [onchain.*] | Failover list, commitment, rate limits, never log keys in URLs |
| key-custody | bot-02-risk, bot-04-sniper, bot-06-exit | [G-3] | [] | Constitution clause 1 made procedural; `forbidden_env_keys` (`hermes/profiles.yaml:18`); paper keys only in env |
| safety-scoring | bot-05-rug, bot-02-risk | [G-2] | [safety.score_report] | Reading and tuning the scored report; thresholds table; blind handling |
| momentum-signals | bot-08-signal, bot-01-scout | [G-2] | [market.ohlcv, market.trades, market.holders_snapshot] | Component scores, weights, checker; signal is evidence not clearance |
| portfolio-ledger | bot-09-journal, bot-02-risk | [G-2] | [portfolio.ledger_read, portfolio.exposure, portfolio.pnl] | Event kinds, snapshots, restart reconciliation, JSONL export |
| daily-report | bot-09-journal | [G-2] | [journal.render_report] | What the 2-4 week evaluation reads; fields and delivery |
| desk-doctor | all | [G-7] | [desk.doctor] | `pumpgrok doctor`: prompt SHA, skills, roster, registry grants, mode == paper |

Total after upgrade: 23 + 12 = 35 skills.

## 4. Tests that prove least privilege

| Test file | Asserts |
|---|---|
| `tests/test_registry_least_privilege.py::test_no_bot_resolves_live_write` | For every `BotManifest` loaded from `contracts/tool-rosters/*.yaml`, `registry.find(name, max_side_effect=PAPER_WRITE, bot=m)` raises `LiveGateError` for every tool whose spec is `LIVE_WRITE`; the audit sink received a row with `allowed=False, reason=live_write_never_resolvable` (R3, R4) |
| `...::test_sniper_cannot_resolve_kill_switch` | `find("risk.kill_switch", max_side_effect=PAPER_WRITE, bot=sniper)` raises `PermissionDenied` with `reason=not_in_roster` |
| `...::test_only_sniper_and_exit_resolve_exec_place` | `find("exec.place", ...)` succeeds for sniper and exit, raises for the other eight |
| `...::test_exit_cannot_place_buy` | `exec.place` wrapped for exit rejects `OrderRequest(side=BUY)` via `risk.check_limits` rule `seat_may_trade` |
| `...::test_chief_has_no_exposure_tools` | chief resolves no `exec.place`, `exec.cancel`, `market.*` tools |
| `...::test_shill_has_no_write_except_journal` | shill's only paper-write grant is `journal.append` |
| `...::test_nobody_resolves_ledger_write` | `portfolio.ledger_write` is `PermissionDenied` for all ten seats |
| `...::test_manifest_tools_subset_of_registry` | every `allowed_tools[].name` exists in the registry (spec Wave 1 `test_manifest_tools_subset_of_registry_grants`) |
| `...::test_grant_side_effect_never_exceeds_spec` | no manifest grants `PAPER_WRITE` on a `READ` tool or vice versa |
| `...::test_live_write_audited_and_alerted` | a live-write attempt produces an audit row and a `notify.alert` severity critical |
| `tests/test_skill_manifests.py::test_every_skill_frontmatter_parses` | all `skills/*/SKILL.md` parse into `SkillManifest`; `name == dirname` |
| `...::test_skill_required_tools_granted_to_its_bots` | every `required_tools` entry is in the roster of every bot listed in `bots` |
| `...::test_skill_permissions_never_live` | `SkillManifest.permissions.max_side_effect != LIVE_WRITE` (validator) |
| `tests/test_bot_manifests.py::test_ten_manifests_validate` | exactly ten manifests; ids `bot-00-chief` .. `bot-09-journal`; `writes_to_exchange` true only for sniper and exit |
| `...::test_roster_tool_count_10_to_15` | core 8 + seat tools within G-7 bounds (`check_desk_integrity.py:41-42`) |
| `tests/safety/test_no_signing_outside_live_stub.py` | AST walk: no `sign`, `send_transaction`, `sendTransaction`, `Keypair` symbol outside `src/pumpgrok/execution/live/` (spec n7) |
| `tests/safety/test_live_adapter_raises.py` | constructing any `LiveAdapterStub` subclass under default config raises `LiveGateError` listing every unmet precondition |
| `tests/safety/test_no_manipulation_tools.py` | no registered tool name matches `post|reply|like|follow|dm|broadcast|wash|volume` and no module under `src/pumpgrok/tools/social/` imports an HTTP method other than GET (D7) |
| `tests/test_correlation.py::test_correlation_id_chain` | a cycle bound with `bind_correlation` yields child ids `<root>/<tool>` on every tool call and every log record |
| `tests/test_idempotency.py::test_exec_place_same_key_returns_first_fill` | two `exec.place` calls with the same key produce one ledger event |

## 5. Decisions recorded here

- `SideEffect` is a `StrEnum` with explicit ranks rather than `IntEnum` so that YAML and
  JSON carry readable values (`paper-write`), matching the catalog.
- `ToolInput.model_config.extra = "forbid"` is the pydantic equivalent of the roster's
  `additionalProperties: false` (`programming-desk/contracts/README.md:59`).
- `ApprovalRecord.approved_by` must start with `human:` for human kinds; this is the
  code form of G-2's "approved_by never self" and of constitution clause 3.
- `ToolRegistry.find` has no `allow_live` argument on purpose (R3). The only live path is
  `LiveAdapterStub.__init__`, which itself raises in this release.
- `BotManifest` validators encode D3 structurally: paper-write `exec.*` only for sniper
  and exit, `risk.kill_switch` only for risk, `portfolio.ledger_write` for nobody.

## Unverified Items

| Item | Default assumed |
|---|---|
| `programming-desk/skills/verification-receipts/SKILL.md:1-6` frontmatter (`bots`, `gates`) was read; the L1/L2 body headings beyond line 43 come from `scout-programming-desk.md:154` | Headings `L1 - Summary`, `L2 - Method`, `Failure modes`, `References` |
| pydantic v2 `Self` return on `model_validator(mode="after")` under `mypy --strict` | Accepted pattern; falls back to the class name if mypy objects |
| Whether the gateway (`services/desk-gateway/`) needs `approval_id` patterns to be JSON-Schema `pattern` (as written) or free strings | `pattern` as written |
| The 35-skill total assumes no existing skill is merged or deleted during upgrade | 23 kept + 12 new |
| Python listing was composed for `python3.12 -m py_compile`; the design-only wave does not run it | Main agent runs the parse check |
