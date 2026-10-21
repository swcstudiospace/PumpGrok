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

Placement follows R31 (single truth for module paths); the listing below is split into
exactly these four files. Ownership: `bot-02-risk` for all of `src/pumpgrok/core/**`
(R36, `docs/ROSTER.md` section 7).

| Module | Contents |
|---|---|
| `src/pumpgrok/core/interfaces.py` | `SideEffect`, errors (`PumpgrokError`, `PermissionDenied`, `LiveGateError`, `ToolTimeout`, `ToolRateLimited`, `LedgerUnavailable`, `DataStale`), `canonical_json`, `derive_idempotency_key`, `ToolSpec`, `ToolMeta`, `RetryPolicy`, `Tool` protocol, `tool()` decorator, `Freshness`, `Health`, `DataSource` protocol, `ExecutionAdapter` protocol and the order/quote/fill/position models, `LiveAdapterStub`, `LiveGate` protocol, `SkillManifest`, `Skill` protocol, `RiskBudget`, `BotManifest`, `Bot` protocol; re-exports `Clock`, `PriceSource`, `LedgerStore` for docs/design/paper-engine.md |
| `src/pumpgrok/core/ids.py` | `ULID_RE`, `IdFactory` (ULIDs from Clock + seeded rng, R29), `CorrelationId`, contextvar, `bind_correlation`, `current_correlation`, `next_span` |
| `src/pumpgrok/core/approvals.py` | `ApprovalRecord` (kinds per R33), phrase parser for `approve <ticket> <mint> <size> <slippage>` |
| `src/pumpgrok/core/registry.py` | `ToolRegistry`, `GrantAudit` |
| `src/pumpgrok/core/__init__.py` | re-export facade only (`from .interfaces import *` plus `ids`, `approvals`, `registry`); defines nothing. `core/interfaces.py` is the module; code imports `pumpgrok.core`. Stated identically in docs/design/paper-engine.md section 10 |

Everything below is presented as one listing so it can be pasted into a single file and
parsed; the implementation splits it along the table above. Batch placement: all four
modules are batch 1 (Phase 1 Foundation, R37).

## 2. The listing

```python
"""pumpgrok core interfaces (design listing; split per docs/design/interfaces.md section 1)."""

from __future__ import annotations

import contextvars
import enum
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar, Literal, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# No `uuid`, no `time`, no `asyncio.sleep`/`asyncio.timeout` in this package (R27, R29).

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
# 2.3 Ids and correlation id propagation (src/pumpgrok/core/ids.py)
# ---------------------------------------------------------------------------

ULID_RE = r"^[0-9A-HJKMNP-TV-Z]{26}$"  # Crockford base32, 48-bit ms time + 80-bit rng


class Clock(Protocol):
    """Defined in src/pumpgrok/replay/clock.py (docs/design/paper-engine.md 4.2) and
    re-exported here because every id, audit row, timeout and retry wait reads it (R27).
    """

    def now(self) -> float: ...  # epoch seconds (UTC); the only time source

    def monotonic(self) -> float: ...

    def utc_iso(self) -> str: ...

    async def sleep(self, seconds: float) -> None: ...

    def timeout(self, seconds: float) -> Any: ...  # async context manager; virtual in replay


class IdFactory:
    """The only ULID source in the package (R29). Time from the injected Clock, the
    80 random bits from the single seeded `random.Random` (paper-engine.md 4.2), so a
    replay reproduces every correlation_id, decision_id, order_id, event id and
    approval id byte-for-byte. The `uuid` module is banned in src/pumpgrok
    (`tests/safety/test_no_uuid.py`).
    """

    def __init__(self, clock: Clock, rng: Any) -> None:  # rng: random.Random from replay/rng.py
        self._clock = clock
        self._rng = rng

    def ulid(self) -> str:
        ms = int(self._clock.now() * 1000)
        rand = self._rng.getrandbits(80)
        return _crockford((ms << 80) | rand, 26)


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _crockford(value: int, width: int) -> str:
    out = []
    for _ in range(width):
        out.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(out))


class CorrelationId(str):
    """Opaque id spanning signal -> decision -> order -> fill (spec OBSERVABILITY).

    Format (R29): the root is a ULID; child spans are `<ulid>.<n>` with `n` the
    1-based span counter of the root's dynamic extent. The ledger `correlation_id`
    column stores the root.
    """

    __slots__ = ()

    @classmethod
    def new(cls, ids: IdFactory) -> CorrelationId:
        return cls(ids.ulid())

    @property
    def root(self) -> str:
        return self.split(".", 1)[0]

    def child(self, n: int) -> CorrelationId:
        return CorrelationId(f"{self.root}.{n}")


_correlation: contextvars.ContextVar[CorrelationId | None] = contextvars.ContextVar(
    "pumpgrok_correlation", default=None
)
_span_counter: contextvars.ContextVar[int] = contextvars.ContextVar("pumpgrok_span", default=0)


def current_correlation() -> CorrelationId:
    """Return the ambient id. The supervisor binds one per cycle (cli.py builds the
    IdFactory); an unbound call is a programming error, never a silent new id."""
    cid = _correlation.get()
    if cid is None:
        raise PumpgrokError("no correlation id bound")
    return cid


def next_span(cid: CorrelationId) -> CorrelationId:
    n = _span_counter.get() + 1
    _span_counter.set(n)
    return cid.child(n)


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
    """Sorted keys, no whitespace, ints and strings only (Decimal is serialised as str).
    This is also the byte form the ledger hash chain is computed over (R28)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def derive_idempotency_key(
    tool: str,
    bot: str,
    payload: Mapping[str, Any],
    *,
    scope: str | None = None,
) -> str:
    """sha256 over (tool, bot, scope, canonical payload) -> 32 hex chars.

    `scope` is the logical unit that must be executed at most once. For exec.place it is
    `OrderRequest.idempotency_scope` = `f"{ticket_id}:{side}:{decision_id}"` (R23),
    derived by PaperAdapter.place, never supplied by the caller; for journal.append it
    is `ticket_id`; for notify.alert it is the UTC minute of the Clock. Fields named
    `correlation_id` are excluded so that a retry under a new correlation id still
    collapses onto the first attempt.
    """
    body = {k: v for k, v in payload.items() if k != "correlation_id"}
    digest = hashlib.sha256(
        canonical_json({"tool": tool, "bot": bot, "scope": scope, "payload": body}).encode()
    ).hexdigest()
    return digest[:32]


# ---------------------------------------------------------------------------
# 2.5 Tool
# ---------------------------------------------------------------------------


class RetryPolicy(BaseModel):
    """tenacity policy (D5). `attempts=1` means no retry. The registry builds the
    tenacity retrier with `sleep=clock.sleep` and wraps the call in
    `clock.timeout(spec.timeout_s)` so replay drives every wait virtually (R27);
    `asyncio.sleep`, `asyncio.timeout` and `time.time` are forbidden in src/pumpgrok
    (static test `tests/safety/test_virtual_time_only.py`).
    """

    model_config = ConfigDict(frozen=True)

    attempts: int = Field(default=1, ge=1, le=10)
    base_s: float = Field(default=0.5, ge=0.0)  # seconds, not money
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

    # The MCP/gateway transport name is this id with "." replaced by "_", derived by
    # services/desk-gateway at exposure time; it is never stored or used as an alias (R19).

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

    async def fetch(
        self, request: Mapping[str, Any], *, max_age_s: float
    ) -> tuple[Any, Freshness]: ...

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
    """Input of exec.place / exec.simulate. Money is integer base units (R28): a BUY
    names `size_lamports`, a SELL names `token_units`. The idempotency key is NOT a
    caller field: PaperAdapter derives it from `(ticket_id, side, decision_id)` (R23);
    `decision_id` is a ULID minted per decision by `core/ids.py`, so a remainder sell or
    a re-decided buy is a new key, never a replay of the first order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str = Field(pattern=r"^SOL-\d{8}-\d{3}$")
    mint: str = Field(min_length=32, max_length=44)
    side: Side
    decision_id: str = Field(pattern=ULID_RE)
    size_lamports: int | None = Field(default=None, gt=0)
    token_units: int | None = Field(default=None, gt=0)
    max_slippage_bps: int = Field(ge=1, le=10_000)
    approval_id: str = Field(pattern=r"^apr-[0-9A-HJKMNP-TV-Z]{26}$")
    quote_id: str | None = None
    correlation_id: str

    @model_validator(mode="after")
    def _size_matches_side(self) -> Self:
        if self.side is Side.BUY and self.size_lamports is None:
            raise ValueError("buy requires size_lamports")
        if self.side is Side.SELL and self.token_units is None:
            raise ValueError("sell requires token_units")
        return self

    @property
    def idempotency_scope(self) -> str:
        return f"{self.ticket_id}:{self.side}:{self.decision_id}"


class Quote(BaseModel):
    """`source="curve"` quotes are the fill basis; `source="jupiter"` quotes are
    informational (route, priority) and never the fill price (R38)."""

    model_config = ConfigDict(frozen=True)

    quote_id: str
    in_amount: int  # lamports (BUY) or token base units (SELL)
    out_amount: int  # token base units (BUY) or lamports (SELL)
    other_amount_threshold: int  # same unit as out_amount
    price_impact_pct: Decimal
    route_plan: list[dict[str, Any]]
    context_slot: int | None
    source: Literal["jupiter", "curve"]
    expires_at: datetime


class SimulationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    would_fill: bool
    fill_kind: Literal["full", "partial", "rejected"]
    price_expected: Decimal  # lamports per token base unit
    expected_out: int  # token base units (BUY) or lamports (SELL)
    price_impact_pct: Decimal
    venue_fee_lamports: int
    network_cost_lamports: int  # base fee + priority fee
    liquidity_ratio: Decimal  # S0 / size_lamports
    rejection_reason: str | None
    latency_ms_estimate: int


class FillStatus(enum.StrEnum):
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class Fill(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str = Field(pattern=ULID_RE)
    decision_id: str = Field(pattern=ULID_RE)
    status: FillStatus
    venue_tx_ref: str = Field(pattern=r"^dry_run:[0-9A-HJKMNP-TV-Z]{26}$")  # never a real signature
    filled_lamports: int
    filled_units: int  # token base units
    filled_fraction: Decimal
    price_avg: Decimal  # lamports per token base unit
    realised_slippage_bps: int
    venue_fee_lamports: int
    network_cost_lamports: int
    route: str
    ledger_seq: int
    reason: str | None = None


class Position(BaseModel):
    """Mirror of vendor models.Position (vendor/grokbot-pumpfun/src/models.py:243) in
    integer base units plus marks. `mtm_frozen` is set by the `graduated` and
    `blind_flatten` paths (R8, R25)."""

    model_config = ConfigDict(frozen=True)

    ticket_id: str
    mint: str
    correlation_id: str
    price_entry: Decimal  # lamports per token base unit
    price_peak: Decimal
    cost_basis_lamports: int  # cash debited incl. all fees
    token_units: int
    opened_at: datetime
    price_mark: Decimal | None = None
    last_mtm_lamports: int | None = None
    unrealised_pnl_lamports: int | None = None
    unrealised_pnl_pct: Decimal | None = None
    mtm_source: Literal["live", "last_good"] = "live"
    mtm_frozen: bool = False
    hold_seconds: int = 0


class ExecutionMode(enum.StrEnum):
    PAPER = "paper"
    LIVE = "live"


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Common interface for PaperAdapter (src/pumpgrok/execution/paper_adapter.py,
    enabled) and the live stub (src/pumpgrok/execution/live/live_adapter.py, disabled)
    (R31)."""

    mode: ClassVar[ExecutionMode]
    venue: ClassVar[str]  # 'paper' | 'disabled'

    async def quote(
        self, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> Quote: ...

    async def simulate(self, request: OrderRequest) -> SimulationResult: ...

    async def place(self, request: OrderRequest) -> Fill: ...

    async def cancel(self, order_id: str, ticket_id: str, decision_id: str) -> bool: ...

    # True only while the order is ACCEPTED; appends OrderRejected(reason=cancelled, stage=ACCEPTED).
    # False (and no event) once the latency sleep has completed.

    async def positions(self, mint: str | None = None) -> Sequence[Position]: ...


class LiveAdapterStub:
    """Base of `LiveAdapter` in src/pumpgrok/execution/live/live_adapter.py (R31; owned by
    bot-02-risk via the ownership rule placed after src/pumpgrok/execution/**). Every
    method raises; nothing here can be reached in paper mode because ToolRegistry
    refuses LIVE_WRITE, and nothing here submits a transaction even in live mode until
    LiveGate.check() is empty (D4). No venue implementation ships in this release, so
    precondition 8 (adapter_registered) is always unmet (R21).
    """

    mode: ClassVar[ExecutionMode] = ExecutionMode.LIVE
    venue: ClassVar[str] = "disabled"

    def __init__(self, gate: LiveGate) -> None:
        unmet = gate.check()
        if unmet:
            raise LiveGateError("live adapter construction refused", unmet=list(unmet))
        raise LiveGateError(
            "live adapters are not implemented in this release", unmet=["adapter_registered"]
        )

    async def quote(
        self, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> Quote:
        raise LiveGateError("live quote disabled")

    async def simulate(self, request: OrderRequest) -> SimulationResult:
        raise LiveGateError("live simulate disabled")

    async def place(self, request: OrderRequest) -> Fill:
        raise LiveGateError("live place disabled")

    async def cancel(self, order_id: str, ticket_id: str, decision_id: str) -> bool:
        raise LiveGateError("live cancel disabled")

    async def positions(self, mint: str | None = None) -> Sequence[Position]:
        raise LiveGateError("live positions disabled")


class LiveGate(Protocol):
    """src/pumpgrok/execution/live/live_gate.py (R31). `check()` returns the ids of
    every UNMET precondition; the startup path prints every unmet item and exits 3
    when the effective mode is live and the list is non-empty (R21, R30).

    The ONE precondition list (R21), identical to docs/design/paper-engine.md 7.2:
      1. mode_live: effective execution.mode == live (R30 precedence: CLI --mode > env PUMPGROK_MODE > TOML execution.mode)
      2. live_enable_env: env PUMPGROK_LIVE_ENABLE=1
      3. min_paper_days: live.min_paper_days >= 14 elapsed, measured ONLY on ledger events with source=paper (never replay)
      4. performance_thresholds: on the same source=paper events: closed_trades >= 50, profit_factor >= 1.2, max_drawdown <= drawdown_halt_fraction
      5. wallet_allowlist: live.wallet_allowlist non-empty (public addresses only)
      6. notional_cap: 0 < live.notional_cap_sol <= 1.0
      7. confirmation_record: live.confirmation_record = HMAC-signed human confirmation produced by `pumpgrok live confirm` with an operator secret that no seat/tool can read, bound to the config hash
      8. adapter_registered: live.adapter explicitly named AND an implementation registered (none ships -> always unmet)
      9. no_active_stop: no active kill switch, halt, or open breaker
    Any unmet -> startup exits 3 printing every unmet item. Replay runs write
    var/replay/<dataset>/ledger.sqlite; every ledger event carries `source` in
    {paper, replay, manual}; LiveGate refuses any ledger containing source=replay for
    its metrics (ids 3 and 4 report `unmet: replay ledger`).
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

    async def run(
        self, registry: ToolRegistry, bot: BotManifest, context: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


# ---------------------------------------------------------------------------
# 2.9 Bot
# ---------------------------------------------------------------------------


class RiskBudget(BaseModel):
    """Per-seat ceilings and the desk-level budget. The ONLY risk-budget schema (R20):
    the same keys appear in docs/ROSTER.md risk_budget, the TOML [risk] block and
    risk.check_limits output. Fractions are of equity in 0..1 (never percent). Every
    default is REVIEW (D6). `paper_equity_sol` is the one SOL-denominated config value;
    it is converted to lamports once at load (R28).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_trade_fraction: Decimal = Field(default=Decimal("0.02"), ge=0, le=1)
    max_token_fraction: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    daily_loss_halt_fraction: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    drawdown_halt_fraction: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)
    max_open_positions: int = Field(default=3, ge=0)
    max_trades_per_day: int = Field(default=20, ge=0)
    liquidity_floor_multiple: int = Field(default=10, ge=1)
    partial_fill_fraction: Decimal = Field(default=Decimal("0.02"), gt=0, le=1)
    paper_equity_sol: Decimal = Field(default=Decimal("10"), gt=0)

    @property
    def paper_equity_lamports(self) -> int:
        return int(self.paper_equity_sol * 1_000_000_000)

    @property
    def may_open_exposure(self) -> bool:
        return self.max_trade_fraction > 0 and self.max_open_positions > 0


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

    id: str = Field(pattern=r"^bot-0[0-9]-[a-z-]+$")  # SEAT_RE (R19)
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
            if g.name == "notify.alert" and self.id in ("bot-02-risk", "bot-05-rug"):
                raise ValueError(
                    f"{self.id} escalates via desk.event_emit kind=escalation; the supervisor relays to notify.alert (R35)"
                )
            if g.name == "portfolio.ledger_write":
                raise ValueError("portfolio.ledger_write is adapter-only, never a seat grant")
        return self


@runtime_checkable
class Bot(Protocol):
    manifest: ClassVar[BotManifest]

    async def cycle(
        self, registry: ToolRegistry, trigger: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    async def heartbeat(self) -> Health: ...


class ApprovalRecord(BaseModel):
    """src/pumpgrok/core/approvals.py (R31). Parsed human approval phrase
    `approve <ticket> <mint> <size> <slippage>` (rules/pumpgrok-team.mdc:28;
    agents/sniper.md:42; size is written in SOL by the human and converted to
    lamports once, here), or a per-ticket exit-rule approval under manual-ticket
    (R17), or the RiskEngine's autonomous-paper approval, or the kill-switch / halt
    clear signature, or the live-gate confirmation. `id` is what exec.place /
    the CLI receive as approval_id.

    Persisted in the ledger as an `ApprovalRecorded` event (R33), never as a
    JournalNote. Consumption (single-send) is a second `ApprovalRecorded` row with
    `consumed=True` written inside the same `BEGIN IMMEDIATE` transaction as the
    `OrderPlaced` it authorises (R23, R26); `consumed` here is the reduced view of
    those rows, never a process-local flag.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^apr-[0-9A-HJKMNP-TV-Z]{26}$")  # 'apr-' + ULID (R29)
    kind: Literal[
        "human_buy",
        "human_sell",
        "exit_rule",
        "autonomous_paper",
        "killswitch_clear",
        "halt_clear",
        "live_gate",
    ]
    ticket_id: str | None = Field(default=None, pattern=r"^SOL-\d{8}-\d{3}$")
    mint: str | None = None
    size_lamports: int | None = Field(default=None, gt=0)
    max_slippage_bps: int | None = None
    exit_rule_id: str | None = (
        None  # exit_rule kind: which rule of engine/exits.py is pre-approved for this ticket
    )
    approved_by: str  # 'human:<name>' for human kinds; 'risk_engine' for autonomous_paper
    raw_message: str
    at: datetime  # Clock time (R27)
    consumed: bool = (
        False  # single-send: one approval, one order; reduced from ApprovalRecorded rows
    )

    HUMAN_KINDS: ClassVar[frozenset[str]] = frozenset(
        {"human_buy", "human_sell", "exit_rule", "killswitch_clear", "halt_clear", "live_gate"}
    )

    @model_validator(mode="after")
    def _human_kinds_need_human(self) -> Self:
        if self.kind in self.HUMAN_KINDS:
            if not self.approved_by.startswith("human:"):
                raise ValueError("human approval must be signed by a human, not a seat")
            if self.kind in ("human_buy", "human_sell") and (
                self.ticket_id is None
                or self.mint is None
                or self.size_lamports is None
                or self.max_slippage_bps is None
            ):
                raise ValueError("human trade approval must carry ticket, mint, size, slippage")
            if self.kind == "exit_rule" and (self.ticket_id is None or self.exit_rule_id is None):
                raise ValueError("exit_rule approval must name the ticket and the rule (R17)")
        elif self.approved_by != "risk_engine":
            raise ValueError("autonomous_paper approvals are issued by RiskEngine.check only (R24)")
        return self

    def matches(self, request: OrderRequest) -> bool:
        return (
            self.ticket_id == request.ticket_id
            and self.mint == request.mint
            and self.max_slippage_bps == request.max_slippage_bps
            and (self.size_lamports == request.size_lamports if request.side is Side.BUY else True)
            and not self.consumed
        )


# ---------------------------------------------------------------------------
# 2.10 ToolRegistry
# ---------------------------------------------------------------------------


class GrantAudit(BaseModel):
    """One row per resolution attempt. Every LIVE_WRITE attempt is a row with
    `allowed=False` and is also emitted as a critical alert (spec SECURITY_AND_VALIDATION).
    `at` is the injected Clock's time (R27), never `datetime.now`.
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

    Invariants (tests/test_registry_least_privilege.py), labelled I1-I5 (R40):
      I1 find() raises PermissionDenied unless the tool is in the bot's allowed_tools.
      I2 find() raises PermissionDenied if the tool's side_effect exceeds the grant's;
         a tool whose spec.requires_approval is True is additionally wrapped so that
         RiskEngine.check (src/pumpgrok/risk/engine.py, R31) runs before the underlying
         callable executes; the ApprovalRecord is matched there and consumed by
         PaperAdapter.place inside the same ledger transaction as the order (R23).
      I3 find() raises LiveGateError for any LIVE_WRITE tool regardless of roster,
         max_side_effect, or config mode. There is no argument that unlocks it.
      I4 Every refusal is appended to the audit log before the exception propagates.
      I5 Seats may only write ledger events through journal.append and desk.event_emit
         with kind in {journal_note, escalation}; the input models of those two tools
         enumerate exactly those kinds. Every other event type (OrderPlaced,
         FillRecorded, HaltSet, KillSwitchSet, ApprovalRecorded, ...) is appended by
         library code only: PaperAdapter, RiskEngine, the supervisor, the CLI (R32).

    Timeouts and retries are Clock-routed (R27): `clock.timeout(spec.timeout_s)` wraps
    the call and tenacity is constructed with `sleep=clock.sleep`.
    """

    def __init__(
        self,
        *,
        clock: Clock,
        audit_sink: Callable[[GrantAudit], None],
        limits_checker: Callable[[OrderRequest, str], Awaitable[bool]],
    ) -> None:
        self._clock = clock
        self._tools: dict[str, Tool] = {}
        self._audit = audit_sink
        self._check_limits = limits_checker  # RiskEngine.check bound by cli.py

    # -- registration -------------------------------------------------------

    def register(self, tool_obj: Tool) -> None:
        name = tool_obj.spec.name
        if name in self._tools:
            raise ValueError(f"duplicate tool {name}")
        if tool_obj.spec.side_effect is SideEffect.LIVE_WRITE:
            # Registered so attempts can be audited; never resolvable (I3).
            log.warning("registering live-write tool %s as refuse-only", name)
        self._tools[name] = tool_obj

    def register_all(self, tools: Iterable[Tool]) -> None:
        for t in tools:
            self.register(t)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def spec(self, name: str) -> ToolSpec:
        return self._tools[name].spec

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock.now(), UTC)

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
        candidates = [
            t for n, t in self._tools.items() if n == capability or n.startswith(capability + ".")
        ]
        if not candidates:
            self._refuse(bot, capability, max_side_effect, "unknown_tool", cid)
        for t in sorted(candidates, key=lambda t: t.spec.name):
            spec = t.spec
            if spec.side_effect is SideEffect.LIVE_WRITE:
                self._refuse(
                    bot, spec.name, spec.side_effect, "live_write_never_resolvable", cid, live=True
                )
            grant = bot.grant_for(spec.name)
            if grant is None:
                if capability == spec.name:
                    self._refuse(bot, spec.name, spec.side_effect, "not_in_roster", cid)
                continue
            if spec.side_effect.exceeds(grant.side_effect):
                self._refuse(bot, spec.name, spec.side_effect, "exceeds_grant", cid)
            if spec.side_effect.exceeds(max_side_effect):
                self._refuse(bot, spec.name, spec.side_effect, "exceeds_requested_max", cid)
            self._audit(
                GrantAudit(
                    at=self._now(),
                    bot=bot.id,
                    tool=spec.name,
                    requested_side_effect=spec.side_effect,
                    allowed=True,
                    reason="ok",
                    correlation_id=cid,
                )
            )
            return self._wrap(t, bot)
        self._refuse(bot, capability, max_side_effect, "no_granted_tool_in_namespace", cid)
        raise AssertionError("unreachable")

    def _refuse(
        self,
        bot: BotManifest,
        tool_name: str,
        se: SideEffect,
        reason: str,
        cid: str,
        *,
        live: bool = False,
    ) -> None:
        self._audit(
            GrantAudit(
                at=self._now(),
                bot=bot.id,
                tool=tool_name,
                requested_side_effect=se,
                allowed=False,
                reason=reason,
                correlation_id=cid,
            )
        )
        if live:
            raise LiveGateError(
                f"{bot.id} attempted live-write tool {tool_name}", tool=tool_name, bot=bot.id
            )
        raise PermissionDenied(
            f"{bot.id} may not resolve {tool_name}: {reason}",
            tool=tool_name,
            bot=bot.id,
            reason=reason,
        )

    def _wrap(self, t: Tool, bot: BotManifest) -> Tool:
        """Apply Clock-routed timeout and retry, rate limit, correlation stamping and, for
        approval-gated tools, the limits/approval check (I2). Returns a Tool.
        """
        spec = t.spec
        check_limits = self._check_limits
        clock = self._clock

        class _Guarded:
            def __init__(self) -> None:
                self.spec = spec

            async def __call__(self, payload: ToolInput, /) -> ToolOutput:
                cid = next_span(current_correlation())
                with bind_correlation(cid):
                    if spec.requires_approval:
                        req = OrderRequest.model_validate(
                            payload.model_dump() | {"correlation_id": str(cid)}
                        )
                        if not await check_limits(req, bot.id):
                            raise PermissionDenied(
                                "RiskEngine.check refused", tool=spec.name, bot=bot.id
                            )
                    # rate limit applied here by the implementation; retries use
                    # tenacity(sleep=clock.sleep, ...) per spec.retry (R27)
                    async with clock.timeout(spec.timeout_s):
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
| browser-ops | bot-07-shill | [] | [] | Keep 4 rules + NEVERs; add untrusted-content handling for metadata URLs; detection/research only, listed in the forbidden-actions test scope: no posting, no wallet UI (R39) |
| desk-execution-protocol | bot-04-sniper, bot-06-exit | [G-2, G-6] | [exec.quote, exec.simulate, exec.place, onchain.priority_fee] | Replace `tools/jupiter_quote.py`/`priority_fee.py` commands with `pumpgrok paper buy|sell --ticket --mint --size-sol --slippage-bps --approval-id` and tool names; keep 6-item checklist and UNKNOWN RESULT |
| desk-folders-and-journal | bot-00-chief, bot-09-journal | [G-2] | [journal.append] | Replace `/workspace/trading-desk/` tree with `var/` ledger + JSONL export; append-only rule enforced by ledger; `kind` is the snake_case event type (`journal_note`, ...) generated from `ledger/events.py` (R32) |
| desk-incident-response | bot-00-chief, bot-02-risk | [G-2] | [risk.halt_status] | Expand the 6 one-line playbooks into L2 steps citing runbooks; RISK sets the switch via `risk.kill_switch` (actions `set`, `flatten_request`; RISK-only grant); clear is CLI-only (`pumpgrok killswitch clear --by <human> --reason <text>`, R22) |
| desk-monitoring | bot-00-chief | [] | [risk.halt_status, portfolio.exposure, exec.positions] | DESK STATUS block sourced from tools, not memory; RUG's post-fill watch is `position-monitoring` |
| desk-operating-model | all | [] | [] | Keep constitution verbatim; roles become 10 seats; engagement levels are `research | paper` only; `live` is a config mode behind the live gate and is disabled; `micro-live` retired (R16) |
| desk-post-trade-review | bot-09-journal | [G-2] | [portfolio.ledger_read, portfolio.pnl, journal.append] | Owned by bot-09-journal, EXIT is a consumer (R36); grades A/B/C/F and Win/Scratch/Loss become `journal.append kind=journal_note` payload fields with `note_kind=review` |
| desk-risk-limits | bot-02-risk, bot-00-chief | [G-2] | [risk.check_limits] | 6-question interview writes the `[risk]` block (R20 keys) of the operator overlay given by `PUMPGROK_CONFIG=<file>` (R30) via a human-signed change, not free text |
| desk-strategy-lab | bot-06-exit, bot-08-signal | [G-2] | [] | Paper mode is the default; rule changes go through `replay-and-backtest` first; each seat uses its own granted `exec.simulate` / `journal.append` |
| desk-trade-lifecycle | bot-00-chief, bot-01-scout | [G-2] | [journal.append] | `tools/ticket_helper.py next|create` -> `pumpgrok ticket next|create|list`; 9 stages map to the snake_case event kinds of `ledger/events.py` (R32) |
| discovery-tools | bot-01-scout, bot-03-whale, bot-07-shill | [] | [market.trades] | LEAD schema unchanged; add data-source freshness rules; SCOUT additionally uses `market.liquidity`, `onchain.token_metadata`, `onchain.authorities` |
| grokbot-pipeline | all | [] | [] | Shrink: engine is ported into `src/pumpgrok/engine`; keep provenance/pin, 9-stage to seat mapping, evidence discipline; `pipeline_evidence.py` retired |
| hermes-cron-desk | bot-00-chief, bot-01-scout, bot-02-risk, bot-05-rug, bot-09-journal | [] | [desk.brief] | Cron prompts become thin wrappers over `pumpgrok <seat> <verb>` and `pumpgrok run --mode paper --once` |
| holder-and-flow-analysis | bot-03-whale | [] | [onchain.top_holders, onchain.large_transfers, market.holders_snapshot] | `holder_check.py` -> tools; LP exclusion documented; `onchain.large_transfers` and `onchain.deployer_history` are WHALE grants (R35) |
| jupiter-routing | bot-04-sniper, bot-06-exit | [G-6] | [exec.quote, onchain.priority_fee] | Quote/route preparation feeding `exec.quote` and `exec.place` (paper); the Jupiter quote is informational (route, priority) and never the fill price (R18, R38); priority-fee cap is the `max_micro_lamports` field; single-send is PaperAdapter idempotency (R23); row is a quarantined paper-write procedure |
| position-monitoring | bot-05-rug | [] | [onchain.lp_status, onchain.authorities, onchain.top_holders, market.price] | 5 red flags -> `pumpgrok rug watch` checks; RUG alerts are `desk.event_emit kind=escalation` payloads (`contracts/events/escalation.schema.json`); the supervisor relays `Escalation` events to `notify.alert` (RUG holds no `notify.alert`, R35); EXIT consumes the alert and `engine/watcher.py` (`PositionWatcher`, owned by bot-05-rug) feeds it |
| pumpgrok-setup | bot-00-chief | [G-7] | [desk.doctor] | Pointer to SETUP.md stays; receipt schema -> verification-receipts; engagement levels `research | paper` (R16) |
| risk-audit | bot-05-rug | [G-2] | [safety.score_report, onchain.authorities, onchain.top_holders] | `authority_check.py` -> `safety.score_report`; verdict schema unchanged; RUG runs the checks, RISK rules through `risk.check_limits` (R35: RISK holds no `onchain.*` / `safety.*` grants) |
| social-sentiment | bot-07-shill | [] | [onchain.token_metadata, market.trades] | Add detection method, D7 boundary, no posting |
| solana-api-reference | bot-04-sniper | [] | [] | Keep as reference; link to catalog backends |
| solana-market-data | bot-01-scout, bot-03-whale, bot-04-sniper, bot-05-rug, bot-08-signal | [] | [] | 4 sources -> D8 sources with endpoints (pump.fun REST, PumpPortal WS, Jupiter lite-api, Solana JSON-RPC); reference skill, each seat uses its own granted `market.*` subset |
| solana-rpc-and-wallet | bot-04-sniper, bot-06-exit | [G-3] | [onchain.priority_fee] | Wallet rules unchanged; RPC failover + rate limits documented (`src/pumpgrok/tools/onchain/rpc.py`, R31); cross-link key-custody |
| tool-connections | bot-00-chief | [] | [] | 7 sites stay; wallet hand-off stays human-only |

### 3.2 New skills

| Skill | bots | gates | required_tools | Purpose |
|---|---|---|---|---|
| verification-receipts | all | [G-2] | [desk.receipt_check] | Receipt before any completion claim; copied from programming-desk and extended with ledger-query evidence |
| paper-broker | bot-04-sniper, bot-06-exit | [G-2, G-6] | [exec.*, market.price, onchain.priority_fee] | One paper order per `(ticket_id, side, decision_id)` (R23); UNKNOWN RESULT handling |
| replay-and-backtest | bot-08-signal, bot-06-exit | [G-2] | [] | `pumpgrok run --mode paper --replay tests/fixtures/replay/<dataset>`; deterministic, same code path; replay ledgers live at `var/replay/<dataset>/ledger.sqlite` with `source=replay` and never feed the live gate (R21) |
| live-gate-procedure | bot-02-risk, bot-00-chief | [G-2, G-6] | [risk.halt_status] | The documented, separate procedure for the nine R21 preconditions; nothing in it flips a flag; `pumpgrok live confirm` is operator-only |
| kill-switch | bot-02-risk, bot-00-chief | [G-2, G-6] | [risk.halt_status] | `set` / `flatten_request` via `risk.kill_switch` (RISK-only grant), env (read at start), file `var/KILLSWITCH` and alert-channel command (polled every cycle); clear is CLI-only with an `ApprovalRecord kind=killswitch_clear` (R22) |
| rpc-hygiene | bot-01-scout, bot-03-whale, bot-04-sniper, bot-05-rug, bot-06-exit | [] | [] | Failover list, commitment, rate limits, never log keys in URLs; each seat uses its own granted `onchain.*` subset |
| key-custody | bot-02-risk, bot-04-sniper, bot-06-exit | [G-3] | [] | Constitution clause 1 made procedural; `forbidden_env_keys` (`hermes/profiles.yaml:18`); no key material exists in paper mode; nothing to custody (R40) |
| safety-scoring | bot-05-rug | [G-2] | [safety.score_report] | Reading and tuning the scored report; thresholds table; blind handling; RISK consumes the verdict through `risk.check_limits` |
| momentum-signals | bot-08-signal | [G-2] | [market.ohlcv, market.trades, market.holders_snapshot] | Component scores, weights, checker; signal is evidence not clearance; `journal.append kind=journal_note` with payload `note_kind=signal` (R40 literal `signal`) |
| portfolio-ledger | bot-09-journal, bot-02-risk | [G-2] | [portfolio.ledger_read, portfolio.exposure, portfolio.pnl] | Event types (R32), snapshots, restart reconciliation, JSONL export |
| daily-report | bot-09-journal | [G-2] | [journal.render_report] | What the 2-4 week evaluation reads; fields and delivery; daily 00:05Z, weekly Monday 00:15Z (R40) |
| desk-doctor | all | [G-7] | [desk.doctor] | `pumpgrok doctor`: prompt SHA, skills, roster, registry grants, effective mode == paper |

Total after upgrade: 23 + 12 = 35 skills.

## 4. Tests that prove least privilege, determinism and the safety invariants

| Test file | Asserts |
|---|---|
| `tests/test_registry_least_privilege.py::test_no_bot_resolves_live_write` | For every `BotManifest` loaded from `contracts/tool-rosters/*.yaml`, `registry.find(name, max_side_effect=PAPER_WRITE, bot=m)` raises `LiveGateError` for every tool whose spec is `LIVE_WRITE`; the audit sink received a row with `allowed=False, reason=live_write_never_resolvable` (I3, I4) |
| `...::test_sniper_cannot_resolve_kill_switch` | `find("risk.kill_switch", max_side_effect=PAPER_WRITE, bot=sniper)` raises `PermissionDenied` with `reason=not_in_roster` |
| `...::test_only_sniper_and_exit_resolve_exec_place` | `find("exec.place", ...)` succeeds for sniper and exit, raises for the other eight |
| `...::test_exit_cannot_place_buy` | `exec.place` wrapped for exit rejects `OrderRequest(side=BUY)` via `RiskEngine.check` rule id `seat_may_trade` (R34 vocabulary) |
| `...::test_chief_has_no_exposure_tools` | chief resolves no `exec.place`, `exec.cancel`, `market.*` tools |
| `...::test_shill_has_no_write_except_journal` | shill's only paper-write grant is `journal.append` |
| `...::test_nobody_resolves_ledger_write` | `portfolio.ledger_write` is `PermissionDenied` for all ten seats |
| `...::test_kill_switch_tool_has_no_clear_action` | the `risk.kill_switch` input model accepts `action in {set, flatten_request}` only; `clear` is a validation error (R22); the only clear path is `pumpgrok killswitch clear --by <human> --reason <text>` |
| `...::test_manifest_tools_subset_of_registry` | every `allowed_tools[].name` exists in the registry (spec Wave 1 `test_manifest_tools_subset_of_registry_grants`) |
| `...::test_grant_side_effect_never_exceeds_spec` | no manifest grants `PAPER_WRITE` on a `READ` tool or vice versa |
| `...::test_live_write_audited_and_alerted` | a live-write attempt produces an audit row and a `notify.alert` severity critical |
| `tests/test_skill_manifests.py::test_every_skill_frontmatter_parses` | all `skills/*/SKILL.md` parse into `SkillManifest`; `name == dirname` |
| `...::test_skill_required_tools_granted_to_its_bots` | every `required_tools` entry is in the roster of every bot listed in `bots` (namespace shorthand `exec.*` expands against the roster) |
| `...::test_skill_permissions_never_live` | `SkillManifest.permissions.max_side_effect != LIVE_WRITE` (validator) |
| `tests/test_bot_manifests.py::test_ten_manifests_validate` | exactly ten manifests; ids `bot-00-chief` .. `bot-09-journal` match `SEAT_RE = ^bot-0[0-9]-[a-z-]+$` (R19); `writes_to_exchange` true only for sniper and exit |
| `...::test_roster_tool_count_8_to_15` | core 8 + seat tools within `ROSTER_MIN_TOOLS = 8` .. `ROSTER_MAX_TOOLS = 15` inclusive (R19, R35; ported `ci/gates/check_desk_integrity.py`); RISK and RUG are exactly 15 as enumerated in R35 |
| `tests/safety/test_no_signing_outside_live_stub.py` | AST walk: no `sign`, `send_transaction`, `sendTransaction`, `Keypair` symbol outside `src/pumpgrok/execution/live/` (spec n7); nothing inside it either in this release (R21 precondition 8: no implementation ships) |
| `tests/safety/test_live_adapter_raises.py` | constructing `LiveAdapter` (`src/pumpgrok/execution/live/live_adapter.py`) under default config raises `LiveGateError` listing every unmet precondition by id (section 2.7, the nine ids) |
| `tests/safety/test_live_gate_rejects_replay_ledger.py` | a ledger whose `events.source` column contains at least one `replay` row is refused by `LiveGate.check()` for its metrics (precondition ids `min_paper_days` and `performance_thresholds` report `unmet: replay ledger`); the same ledger with only `source=paper` rows is accepted for metrics (R21) |
| `tests/safety/test_no_manipulation_tools.py` | no registered tool name matches `post|reply|like|follow|dm|broadcast|wash|volume`; no module under `src/pumpgrok/tools/social/` imports an HTTP method other than GET; `notify.*` is inside the scope: `notify.alert` destinations must come from the configured allowlist (Telegram chat ids, webhook URLs) and no `notify.*` module references a public social API (R39, D7); `skills/browser-ops/SKILL.md` is in the forbidden-actions scope (no posting, no wallet UI) |
| `tests/safety/test_virtual_time_only.py` (static) | AST walk over `src/pumpgrok/**`: no `asyncio.sleep`, `asyncio.timeout`, `asyncio.wait_for`, `time.time`, `time.monotonic`, `datetime.now` outside `src/pumpgrok/replay/clock.py`; every tenacity `Retrying`/`AsyncRetrying` construction passes `sleep=clock.sleep` (R27) |
| `tests/safety/test_no_uuid.py` (static) | no `import uuid` / `from uuid` anywhere under `src/pumpgrok/`; every id is minted by `src/pumpgrok/core/ids.py` (R29) |
| `tests/safety/test_money_is_int.py` (static) | no pydantic field under `src/pumpgrok/core/`, `src/pumpgrok/tools/`, `src/pumpgrok/ledger/`, `src/pumpgrok/execution/` whose name ends in `_sol`, `_lamports`, `_units`, `_amount`, `_fee`, `_cost`, `_basis`, `_pnl` is annotated `float`; `_lamports` / `_units` fields are `int`; `price_*` (`price_entry`, `price_peak`, `price_mark`, `price_avg`, `price_expected`, `price_exit`), `*_pct`, `*_fraction`, `*_ratio` fields are `Decimal` (R28). The only SOL-denominated inputs are the CLI flag `--size-sol` and the config key `paper_equity_sol`, both converted to lamports once at the boundary |
| `tests/test_correlation.py::test_correlation_id_chain` | a cycle bound with `bind_correlation` yields child ids `<ulid>.<n>` with `n` increasing per tool call, on every tool call and every log record; the root is a 26-char ULID minted by `IdFactory` (R29) |
| `tests/test_idempotency.py::test_exec_place_same_key_returns_first_fill` | two `exec.place` calls with the same `(ticket_id, side, decision_id)` produce one ledger event and return the first `Fill`; a third call with a fresh `decision_id` (same ticket and side) produces a new order (R23: a remainder sell or a re-decided buy is a new decision, never a replay of the first) |
| `tests/test_idempotency.py::test_approval_consumed_in_same_transaction` | after `exec.place` the ledger holds `OrderPlaced` and the `ApprovalRecorded` consumed-update with the same `seq` neighbourhood inside one `BEGIN IMMEDIATE` transaction; a crash injected between the two leaves neither (R23, R26) |
| `tests/ledger/test_single_writer_concurrent_appends.py` | two processes (supervisor and `pumpgrok paper buy` CLI) append 200 events each through `ledger/store.py`; the chain verifies, `seq` has no gaps, every `prev_hash` matches, and no `UNIQUE` violation on `hash` occurs (R26: `BEGIN IMMEDIATE` serialises writers) |
| `tests/risk/test_kill_switch_in_flight.py` | an order in `ACCEPTED` (latency sleep pending on `FixtureClock`) when `var/KILLSWITCH` appears is rejected at `CONFIRMING` with `reason=kill_switch` and no `FillRecorded`; with `flatten_request` the supervisor waits on the adapter's in-flight barrier, then calls `PaperAdapter.place` in-process so every open position gets `PositionClosed reason=kill_flatten` even with EXIT observe-only (R22) |
| `tests/test_registry_least_privilege.py::test_seats_write_only_journal_note_and_escalation` | for every seat, `journal.append` / `desk.event_emit` with `kind` outside `{journal_note, escalation}` is rejected by the input model; every other ledger type is appended only by `PaperAdapter`, `RiskEngine`, the supervisor or the CLI (I5) |
| `...::test_risk_and_rug_have_no_notify_alert` | `bot-02-risk` and `bot-05-rug` manifests do not grant `notify.alert` (R35); their escalations are `desk.event_emit kind=escalation` events that the supervisor relays to `notify.alert` with allowlisted destinations (R39) |
| `tests/execution/test_cancel_semantics.py` | `exec.cancel` on an `ACCEPTED` order returns `True` and appends `OrderRejected(reason=cancelled, stage=ACCEPTED)`; after the latency sleep it returns `False` and appends nothing |
| `tests/engine/test_blind_flatten.py` | an open position with no price for `blind_max_s = 300` virtual seconds is force-closed at `last_good` with `PositionClosed reason=blind_flatten` and an `Escalation` is appended; no position is ever left open past `blind_max_s` without a price (R25) |

## 5. Decisions recorded here

- `SideEffect` is a `StrEnum` with explicit ranks rather than `IntEnum` so that YAML and
  JSON carry readable values (`paper-write`), matching the catalog.
- `ToolInput.model_config.extra = "forbid"` is the pydantic equivalent of the roster's
  `additionalProperties: false` (`programming-desk/contracts/README.md:59`).
- `ApprovalRecord.approved_by` must start with `human:` for human kinds; this is the
  code form of G-2's "approved_by never self" and of constitution clause 3.
- `ToolRegistry.find` has no `allow_live` argument on purpose (I3). The only live path is
  `LiveAdapterStub.__init__`, which itself raises in this release.
- `BotManifest` validators encode D3 structurally: paper-write `exec.*` only for sniper
  and exit, `risk.kill_switch` only for risk, `portfolio.ledger_write` for nobody.
- Money is integer base units everywhere (`<x>_lamports: int`, `<x>_units: int` for token base units); prices,
  impacts and fractions are `Decimal` (R28). There is no float money field in this
  listing and the static test `test_money_is_int` keeps it that way.
- Every id (correlation, decision, order, event, approval) is a ULID from
  `core/ids.py`, minted from the injected `Clock` and seeded RNG (R29), so replay runs
  reproduce ids byte-for-byte. The `uuid` module is banned (`test_no_uuid`).
- Registry invariants are labelled I1-I5; the orchestrator's R-numbers are never reused
  as internal labels (R40).
- `contracts/events/` holds exactly the 18 R32 schemas (`order_placed.schema.json` ...
  `approval_recorded.schema.json`). The D2 `signal`, `safety_report`, `verdict` and
  `alert` shapes are folded into the `journal_note` (payload `note_kind`), `escalation`,
  `order_placed` and `fill_recorded` payload schemas; there is no separate
  `signal.schema.json` or `alert.schema.json`.
- RISK and RUG hold no `notify.alert` (R35, enforced by the `BotManifest` validator);
  they escalate with `desk.event_emit kind=escalation` and the supervisor relays every
  `Escalation` ledger event to `notify.alert` with allowlisted destinations (R39).
- Kill-switch flatten is executed by the supervisor calling `PaperAdapter.place`
  in-process after the adapter's in-flight barrier drains; `exec.cancel` on an
  `ACCEPTED` order appends `OrderRejected(reason=cancelled)`.

## Unverified Items

| Item | Default assumed |
|---|---|
| `programming-desk/skills/verification-receipts/SKILL.md:1-6` frontmatter (`bots`, `gates`) was read; the L1/L2 body headings beyond line 43 come from `scout-programming-desk.md:154` | Headings `L1 - Summary`, `L2 - Method`, `Failure modes`, `References` |
| pydantic v2 `Self` return on `model_validator(mode="after")` under `mypy --strict` | Accepted pattern; falls back to the class name if mypy objects |
| Whether the gateway (`services/desk-gateway/`) needs `approval_id` patterns to be JSON-Schema `pattern` (as written) or free strings | `pattern` as written |
| The 35-skill total assumes no existing skill is merged or deleted during upgrade | 23 kept + 12 new |
| Python listing was composed for `python3.12 -m py_compile`; the design-only wave does not run it | Main agent runs the parse check |
