"""RiskEngine: the only component that may say no to an order (paper-engine.md 5.2, R24).

Library code, called in-process by ``PaperAdapter.place`` for every order
regardless of the RISK seat's health. Only ``RiskEngine`` appends ``HaltSet``
and ``BreakerTripped`` rows. Decisions bind ``order_hash``: the adapter must
refuse to proceed without a passed ``RiskDecision`` whose hash matches.

The 19 R34 steps run in exact order with first-failure-wins. Steps 13 and 14
cap rather than reject. Sells carrying an exit reason in
``EXIT_SELL_REASONS`` skip steps 2-4 and 9-19 (reducing risk is always
allowed); every other order evaluates every step, so a manual sell is still
refused by an active kill switch, halt or open breaker. Steps 10-12 are
buy-only. Steps 13, 14, 18 and 19 compare lamport sizes, so sells auto-pass
them; steps 9, 15, 16 and 17 evaluate for sells too (trade counting, halt
detection and mark freshness are side-independent).

Approval consumption plus ``OrderPlaced`` in one transaction (TOOL-004) lands
in plan 04-07; here ``check`` returns the bound ``RiskDecision`` (with the
minted autonomous approval, when applicable) that the adapter consumes.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.ids import Clock, IdFactory, calling_seat
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.ledger.views import equity_lamports
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.risk.limits import EngineLimits

STEP_IDS: tuple[str, ...] = (
    "ledger_inconsistent",
    "kill_switch",
    "halted",
    "breaker_open",
    "live_gate",
    "approval_missing",
    "approval_mismatch",
    "seat_may_trade",
    "max_trades_per_day",
    "max_open_positions",
    "already_open",
    "creator_already_open",
    "max_trade_fraction",
    "max_token_fraction",
    "daily_loss_halt",
    "drawdown_halt",
    "data_stale",
    "size_too_small",
    "below_liquidity_floor",
)

#: Steps an exit sell never evaluates (paper-engine.md 5.2 line 578).
EXIT_SKIP_STEPS: frozenset[str] = frozenset(
    {
        "kill_switch",
        "halted",
        "breaker_open",
        "max_trades_per_day",
        "max_open_positions",
        "already_open",
        "creator_already_open",
        "max_trade_fraction",
        "max_token_fraction",
        "daily_loss_halt",
        "drawdown_halt",
        "data_stale",
        "size_too_small",
        "below_liquidity_floor",
    }
)

#: Exit reasons that earn the skip above. Adapter-internal force-closes
#: (``graduated``, ``blind_flatten``) carry no order; they still name the
#: same vocabulary when they do flow through ``check``.
EXIT_SELL_REASONS: frozenset[str] = frozenset(
    {"exit_rule", "rug_alert", "kill_flatten", "blind_flatten", "graduated"}
)

#: System-initiated risk exits mint their own approval in any autonomy mode.
SYSTEM_EXIT_REASONS: frozenset[str] = frozenset({"kill_flatten", "rug_alert"})

#: Seats allowed to send each side (upgrade-plan RISK-005, R34 step 8).
BUY_SEAT = "bot-04-sniper"
SELL_SEAT = "bot-06-exit"

#: Exact constitution bytes (rules/pumpgrok-team.mdc:34). The dash is U+2013;
#: chr() keeps this file ASCII (no literal or backslash-u escape).
FLOOR_HALTED_DAILY = "FLOOR HALTED " + chr(0x2013) + " DAILY LOSS LIMIT"

#: A RISK KILL verdict on a mint, recorded by the RISK seat as a ledger
#: ``JournalNote`` with ``note_kind == "verdict"`` and this text shape.
#: A killed mint refuses buys desk-wide for the session; sells still pass.
KILL_VERDICT_RE = re.compile(r"^RISK verdict=KILL mint=(?P<mint>\S+)(?:\s+reason=.*)?$")

#: Alert-channel command shape (T-04-10): exact ``KILL`` head, optional
#: ``FLATTEN`` flag, mandatory reason. Anything else is not a command.
KILL_LINE_RE = re.compile(r"^KILL(?:\s+FLATTEN)?\s+(?P<reason>.+)$")

_RECHECK_STEPS: frozenset[str] = frozenset(
    {
        "ledger_inconsistent",
        "kill_switch",
        "halted",
        "breaker_open",
        "max_trade_fraction",
        "max_token_fraction",
        "daily_loss_halt",
        "drawdown_halt",
        "data_stale",
        "size_too_small",
        "below_liquidity_floor",
    }
)


class RiskDecision(BaseModel):
    """One bound decision. ``reason`` is the first-failure R34 id, or ``pass``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    reason: str
    order_hash: str
    decision_id: str
    approval_id: str | None = None
    approval: ApprovalRecord | None = None
    size_lamports: int | None = None
    token_units: int | None = None
    capped: bool = False
    caps: dict[str, int] = Field(default_factory=dict)
    probe: bool = False
    evaluated: list[dict[str, str]] = Field(default_factory=list)


def order_hash_for(order: OrderRequest) -> str:
    """Bind a decision to its order: sha256 over the canonical order fields."""
    return hashlib.sha256(
        canonical_json(
            {
                "ticket_id": order.ticket_id,
                "side": order.side.value,
                "decision_id": order.decision_id,
                "mint": order.mint,
                "size_lamports": order.size_lamports,
                "token_units": order.token_units,
                "max_slippage_bps": order.max_slippage_bps,
            }
        ).encode("utf-8")
    ).hexdigest()


def halt_key(reason: str, day_utc: str) -> str:
    """Idempotency per (reason, utc_day): one ``HaltSet`` per reason per day."""
    return hashlib.sha256(f"HaltSet|{reason}|{day_utc}".encode()).hexdigest()


def utc_day(now_s: float) -> str:
    """UTC calendar day of an epoch timestamp."""
    return format_ts_utc(now_s)[:10]


class _Fail(Exception):
    """Internal: abort the step walk with the failing step id and detail."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass
class _StepCtx:
    """Mutable walk state shared by the 19 step methods."""

    order: OrderRequest
    seat: str | None
    exit_reason: str | None
    creator: str | None
    source: str
    correlation_id: str
    stage: str
    is_buy: bool
    is_exit_sell: bool
    wanted: set[str]
    state: LedgerState
    kill: tuple[str, str, bool] | None
    open_breakers: set[str]
    killed: set[str]
    equity: int
    approvals: dict[str, ApprovalRecord]
    evaluated: dict[str, str] = field(default_factory=dict)
    approval: ApprovalRecord | None = None
    approval_id: str | None = None
    final_size: int | None = None
    caps: dict[str, int] = field(default_factory=dict)
    capped: bool = False

    def mark(self, step: str, status: str = "pass") -> None:
        """Record a step outcome (call args keep password-wording lints quiet)."""
        self.evaluated[step] = status


class RiskEngine:
    """Evaluates the 19 R34 steps for one order (paper-engine.md 5.2).

    The kill-switch env is snapshotted at construction (read once at start,
    R22); the file and alert sources are polled on every check. Repeat checks
    with the same ``order_hash`` (and stage) return the identical decision.
    """

    def __init__(
        self,
        *,
        store: LedgerStore,
        budget: RiskBudget,
        ids: IdFactory,
        clock: Clock,
        limits: EngineLimits | None = None,
        mode: Literal["paper", "live"] = "paper",
        autonomy: Literal["manual-ticket", "autonomous-paper"] = "manual-ticket",
        killswitch_path: Path | str | None = None,
        alert_lines: Callable[[], list[str]] | None = None,
        env: Mapping[str, str] | None = None,
        get_reserves: Callable[[str], tuple[int, int] | None] | None = None,
        live_check: Callable[[], list[str]] | None = None,
        observe_only: frozenset[str] = frozenset(),
        scan_kill_verdicts: bool = True,
    ) -> None:
        self._store = store
        self._budget = budget
        self._ids = ids
        self._clock = clock
        self._limits = limits if limits is not None else EngineLimits()
        self._mode = mode
        self._autonomy = autonomy
        self._killswitch_path = Path(killswitch_path) if killswitch_path is not None else None
        self._alert_lines = alert_lines
        start_env = dict(env) if env is not None else dict(os.environ)
        self._killswitch_env_start = start_env.get("PUMPGROK_KILLSWITCH", "")
        self._get_reserves = get_reserves
        self._live_check = live_check
        self._observe_only = observe_only
        self._scan_kill_verdicts = scan_kill_verdicts
        self._decisions: dict[str, RiskDecision] = {}

    def _now_ts(self) -> str:
        return format_ts_utc(self._clock.now())

    def _fold(self) -> LedgerState:
        events = self._store.read(since_seq=1, limit=None)
        meta_equity = self._store.get_meta("initial_equity_lamports")
        if meta_equity is not None:
            initial = int(meta_equity)
        else:
            initial = self._budget.paper_equity_lamports
        meta_source = self._store.get_meta("source")
        if meta_source:
            source = meta_source
        elif events:
            source = str(events[0]["source"])
        else:
            source = "paper"
        state = initial_state(
            source=source,
            initial_equity_lamports=initial,
            day_utc=utc_day(self._clock.now()),
        )
        for event in events:
            state = reduce(state, event)
        return state

    def _poll_kill(self) -> tuple[str, str, bool] | None:
        """Active kill switch, if any: (source, reason, flatten_requested)."""
        if self._killswitch_env_start.strip() not in ("", "0", "false"):
            return ("env", self._killswitch_env_start.strip(), False)
        file_state = self._kill_file_state()
        if file_state is not None:
            return file_state
        alert_state = self._kill_alert_state()
        if alert_state is not None:
            return alert_state
        return self._fold_uncached_kill()

    def _kill_file_state(self) -> tuple[str, str, bool] | None:
        if self._killswitch_path is None or not self._killswitch_path.is_file():
            return None
        first = self._killswitch_path.read_text(encoding="utf-8").splitlines()
        line = first[0].strip() if first else ""
        if line in ("FLATTEN", "FLATTEN:"):
            return ("file", "flatten requested", True)
        if line.startswith("FLATTEN ") or line.startswith("FLATTEN:"):
            return ("file", line[len("FLATTEN") :].lstrip(" :"), True)
        return ("file", line, False)

    def _kill_alert_state(self) -> tuple[str, str, bool] | None:
        if self._alert_lines is None:
            return None
        for raw in self._alert_lines():
            match = KILL_LINE_RE.match(raw.strip())
            if match is not None:
                head = raw.strip().split(None, 2)[:2]
                return ("alert_command", match.group("reason").strip(), "FLATTEN" in head)
        return None

    def _fold_uncached_kill(self) -> tuple[str, str, bool] | None:
        for event in self._store.read(limit=None):
            if event["type"] == "KillSwitchSet":
                payload = event["payload"]
                if isinstance(payload, dict):
                    return (
                        str(payload.get("origin", "command")),
                        str(payload.get("reason", "")),
                        bool(payload.get("flatten_requested", False)),
                    )
            elif event["type"] == "KillSwitchCleared":
                return None
        return None

    def _killed_mints(self) -> set[str]:
        """Mints under a session RISK KILL verdict (upgrade-plan RISK-005)."""
        if not self._scan_kill_verdicts:
            return set()
        killed: set[str] = set()
        for event in self._store.read(limit=None):
            if event["type"] != "JournalNote":
                continue
            payload = event["payload"]
            if not isinstance(payload, dict):
                continue
            if str(payload.get("note_kind", "")) != "verdict":
                continue
            match = KILL_VERDICT_RE.match(str(payload.get("text", "")))
            if match is not None:
                killed.add(match.group("mint"))
        return killed

    def _approvals(self) -> dict[str, ApprovalRecord]:
        """Latest unconsumed approvals by id, rebuilt from ``ApprovalRecorded`` rows."""
        latest: dict[str, dict[str, Any]] = {}
        for event in self._store.read(limit=None):
            if event["type"] != "ApprovalRecorded":
                continue
            payload = event["payload"]
            if not isinstance(payload, dict):
                continue
            approval_id = str(payload.get("id", ""))
            if approval_id:
                latest[approval_id] = payload
        records: dict[str, ApprovalRecord] = {}
        for approval_id, payload in latest.items():
            if bool(payload.get("consumed", False)):
                continue
            try:
                records[approval_id] = ApprovalRecord(
                    id=approval_id,
                    kind=payload.get("kind", ""),
                    ticket_id=payload.get("ticket_id") or None,
                    mint=payload.get("mint") or None,
                    size_lamports=payload.get("size_lamports") or None,
                    token_units=payload.get("token_units") or None,
                    max_slippage_bps=payload.get("max_slippage_bps") or None,
                    exit_rule_id=payload.get("exit_rule_id") or None,
                    approved_by=str(payload.get("approved_by", "")),
                    raw_message=str(payload.get("raw_message", "")),
                    at=datetime.fromisoformat(str(payload.get("at", ""))),
                    consumed=False,
                )
            except ValueError:
                continue
        return records

    def _mint_autonomous(self, order: OrderRequest, exit_reason: str | None) -> ApprovalRecord:
        now = datetime.fromtimestamp(self._clock.now(), UTC)
        if order.side.value == "buy":
            message = f"autonomous-paper buy {order.ticket_id} {order.mint}"
            return ApprovalRecord(
                id=f"apr-{self._ids.ulid()}",
                kind="autonomous_paper",
                ticket_id=order.ticket_id,
                mint=order.mint,
                size_lamports=order.size_lamports,
                max_slippage_bps=order.max_slippage_bps,
                approved_by="risk_engine",
                raw_message=message,
                at=now,
            )
        message = f"autonomous-paper sell {exit_reason or 'exit'} {order.mint}"
        return ApprovalRecord(
            id=f"apr-{self._ids.ulid()}",
            kind="autonomous_paper",
            ticket_id=order.ticket_id,
            mint=order.mint,
            token_units=order.token_units,
            max_slippage_bps=order.max_slippage_bps,
            approved_by="risk_engine",
            raw_message=message,
            at=now,
        )

    def _halt_row(
        self,
        *,
        reason: str,
        detail: str,
        equity: int,
        day_start: int,
        ts_utc: str,
        source: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        return {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": halt_key(reason, ts_utc[:10]),
            "type": "HaltSet",
            "payload": {
                "source": source,
                "reason": reason,
                "detail": detail,
                "equity_lamports": equity,
                "day_start_equity_lamports": day_start,
                "set_by": "risk_engine",
            },
        }

    def evaluate_halts(self, *, source: str = "paper", correlation_id: str = "desk") -> str | None:
        """Detect fresh daily-loss/drawdown breaches and append ``HaltSet``.

        Returns the breach reason (``daily_loss``/``drawdown``) or ``None``.
        Never clears: UTC rollover and the passage of time leave halts latched
        until the human halt-clear path appends ``HaltCleared`` (R5).
        """
        try:
            self._store.verify()
        except LedgerInconsistent:
            return None
        state = self._fold()
        if state.halt.active:
            return None
        equity = self._equity_for_halts(state)
        return self._detect_breach(
            state, equity, ts_utc=self._now_ts(), source=source, correlation_id=correlation_id
        )

    def _equity_for_halts(self, state: LedgerState) -> int:
        if self._limits.daily_loss_basis == "realized":
            return int(state.cash_lamports) + int(state.counters.realized_today_lamports)
        return int(equity_lamports(state))

    def _detect_breach(
        self,
        state: LedgerState,
        equity: int,
        *,
        ts_utc: str,
        source: str,
        correlation_id: str,
    ) -> str | None:
        day_start = int(state.day_start_equity_lamports)
        peak = int(state.peak_equity_lamports)
        daily_limit = float(self._budget.daily_loss_halt_fraction)
        drawdown_limit = float(self._budget.drawdown_halt_fraction)
        daily_loss = (day_start - equity) / day_start if day_start > 0 else 0.0
        if daily_loss >= daily_limit:
            with _suppress_integrity():
                self._store.append(
                    **self._halt_row(
                        reason="daily_loss",
                        detail=FLOOR_HALTED_DAILY,
                        equity=equity,
                        day_start=day_start,
                        ts_utc=ts_utc,
                        source=source,
                        correlation_id=correlation_id,
                    )
                )
            return "daily_loss"
        drawdown = (peak - equity) / peak if peak > 0 else 0.0
        if drawdown >= drawdown_limit:
            with _suppress_integrity():
                self._store.append(
                    **self._halt_row(
                        reason="drawdown",
                        detail=f"drawdown {drawdown:.4f} >= {drawdown_limit:.2f} of peak",
                        equity=equity,
                        day_start=day_start,
                        ts_utc=ts_utc,
                        source=source,
                        correlation_id=correlation_id,
                    )
                )
            return "drawdown"
        return None

    def check(
        self,
        order: OrderRequest,
        *,
        seat: str | None = None,
        exit_reason: str | None = None,
        creator: str | None = None,
        source: str = "paper",
        correlation_id: str = "desk",
        stage: Literal["ACCEPTED", "CONFIRMING"] = "ACCEPTED",
    ) -> RiskDecision:
        """Run the R34 steps for one order; first failure wins.

        ``exit_reason`` names an exit-rule, ``rug_alert``, ``kill_flatten``,
        ``blind_flatten`` or ``graduated`` sell; those sells skip steps 2-4
        and 9-19. ``creator`` is the candidate mint's creator for the
        ``creator_already_open`` step (the sniper knows it off-ledger; the
        ledger scan is the fallback). ``stage="CONFIRMING"`` re-runs only
        the stop and limit steps before a fill.
        """
        order_hash = order_hash_for(order)
        cache_key = f"{stage}|{order_hash}"
        cached = self._decisions.get(cache_key)
        if cached is not None:
            return cached
        decision = self._evaluate(
            order,
            order_hash=order_hash,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            source=source,
            correlation_id=correlation_id,
            stage=stage,
        )
        self._decisions[cache_key] = decision
        return decision

    def _skip(self, step: str, ctx: _StepCtx) -> bool:
        if ctx.stage == "CONFIRMING" and step not in _RECHECK_STEPS:
            return True
        return ctx.is_exit_sell and step in EXIT_SKIP_STEPS

    def _evaluate(
        self,
        order: OrderRequest,
        *,
        order_hash: str,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
        source: str,
        correlation_id: str,
        stage: Literal["ACCEPTED", "CONFIRMING"],
    ) -> RiskDecision:
        is_buy = order.side.value == "buy"
        state = self._fold()
        ctx = _StepCtx(
            order=order,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            source=source,
            correlation_id=correlation_id,
            stage=stage,
            is_buy=is_buy,
            is_exit_sell=(
                not is_buy and exit_reason is not None and exit_reason in EXIT_SELL_REASONS
            ),
            wanted={"human_buy"} if is_buy else {"human_sell", "exit_rule"},
            state=state,
            kill=self._poll_kill(),
            open_breakers=self._open_breakers(state),
            killed=self._killed_mints() if is_buy else set(),
            equity=self._equity_for_halts(state),
            approvals=self._approvals(),
            final_size=order.size_lamports if is_buy else None,
        )
        ctx.approval_id = order.approval_id or None
        try:
            for step in STEP_IDS:
                if self._skip(step, ctx):
                    continue
                getattr(self, f"_step_{step}")(ctx)
        except _Fail as fail:
            return self._reject(order_hash, ctx, fail.reason)
        return self._accept(order_hash, ctx)

    def _accept(self, order_hash: str, ctx: _StepCtx) -> RiskDecision:
        order = ctx.order
        return RiskDecision(
            passed=True,
            reason="pass",
            order_hash=order_hash,
            decision_id=order.decision_id,
            approval_id=ctx.approval_id,
            approval=ctx.approval,
            size_lamports=ctx.final_size if ctx.is_buy else None,
            token_units=None if ctx.is_buy else order.token_units,
            capped=ctx.capped,
            caps=dict(ctx.caps),
            evaluated=self._evaluated(ctx, None),
        )

    def _reject(self, order_hash: str, ctx: _StepCtx, reason: str) -> RiskDecision:
        order = ctx.order
        return RiskDecision(
            passed=False,
            reason=reason,
            order_hash=order_hash,
            decision_id=order.decision_id,
            approval_id=ctx.approval_id,
            approval=ctx.approval,
            size_lamports=ctx.final_size if ctx.is_buy else None,
            token_units=None if ctx.is_buy else order.token_units,
            capped=ctx.capped,
            caps=dict(ctx.caps),
            evaluated=self._evaluated(ctx, reason),
        )

    def _evaluated(self, ctx: _StepCtx, failed: str | None) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for step in STEP_IDS:
            status = "fail" if step == failed else ctx.evaluated.get(step, "skip")
            rows.append({"id": step, "status": status})
        return rows

    def _step_ledger_inconsistent(self, ctx: _StepCtx) -> None:
        ctx.mark("ledger_inconsistent")
        try:
            self._store.verify()
        except LedgerInconsistent as exc:
            with _suppress_integrity():
                self._store.append(
                    **self._halt_row(
                        reason="ledger_inconsistent",
                        detail=f"chain verify failed: {exc}",
                        equity=0,
                        day_start=0,
                        ts_utc=self._now_ts(),
                        source=ctx.source,
                        correlation_id=ctx.correlation_id,
                    )
                )
            raise _Fail("ledger_inconsistent", "chain verify failed") from exc

    def _step_kill_switch(self, ctx: _StepCtx) -> None:
        ctx.mark("kill_switch")
        if ctx.kill is not None:
            raise _Fail("kill_switch", f"source={ctx.kill[0]}")

    def _step_halted(self, ctx: _StepCtx) -> None:
        ctx.mark("halted")
        if ctx.state.halt.active:
            raise _Fail("halted", f"reason={ctx.state.halt.reason}")

    def _step_breaker_open(self, ctx: _StepCtx) -> None:
        ctx.mark("breaker_open")
        if ctx.open_breakers:
            raise _Fail("breaker_open", f"breaker={sorted(ctx.open_breakers)[0]}")
        if ctx.killed:
            raise _Fail("breaker_open", f"risk_kill:{sorted(ctx.killed)[0]}")

    def _step_live_gate(self, ctx: _StepCtx) -> None:
        ctx.mark("live_gate")
        if self._mode == "paper":
            return
        unmet = self._live_check() if self._live_check is not None else ["adapter_registered"]
        if unmet:
            raise _Fail("live_gate", f"unmet={','.join(unmet)}")

    def _step_approval_missing(self, ctx: _StepCtx) -> None:
        ctx.mark("approval_missing")
        if ctx.exit_reason in SYSTEM_EXIT_REASONS or self._autonomy == "autonomous-paper":
            ctx.approval = self._mint_autonomous(ctx.order, ctx.exit_reason)
            ctx.approval_id = ctx.approval.id
            return
        ticket_approval = self._ticket_approval(ctx.approvals, ctx.order.ticket_id)
        if ticket_approval is None:
            raise _Fail("approval_missing", "no unconsumed approval for ticket")
        ctx.approval = ticket_approval
        ctx.approval_id = ticket_approval.id

    def _step_approval_mismatch(self, ctx: _StepCtx) -> None:
        ctx.mark("approval_mismatch")
        approval = ctx.approval
        if approval is not None and approval.approved_by == "risk_engine":
            return
        if approval is None or approval.kind not in ctx.wanted or not approval.matches(ctx.order):
            raise _Fail("approval_mismatch", "approval does not bind this order")

    def _step_seat_may_trade(self, ctx: _StepCtx) -> None:
        ctx.mark("seat_may_trade")
        approval = ctx.approval
        if (
            ctx.exit_reason == "kill_flatten"
            and approval is not None
            and approval.approved_by == "risk_engine"
        ):
            return
        acting = ctx.seat if ctx.seat is not None else calling_seat()
        if acting is None:
            raise _Fail("seat_may_trade", "no seat bound")
        if acting in self._observe_only:
            raise _Fail("seat_may_trade", f"seat observe-only: {acting}")
        if "bot-02-risk" in self._observe_only and ctx.is_buy:
            raise _Fail("seat_may_trade", "risk seat latched: buys off desk-wide")
        if ctx.is_buy and acting != BUY_SEAT:
            raise _Fail("seat_may_trade", f"buys only from {BUY_SEAT}")
        if not ctx.is_buy and acting != SELL_SEAT:
            raise _Fail("seat_may_trade", f"sells only from {SELL_SEAT}")

    def _step_max_trades_per_day(self, ctx: _StepCtx) -> None:
        ctx.mark("max_trades_per_day")
        trades = int(ctx.state.counters.trades_today)
        if trades >= int(self._budget.max_trades_per_day):
            raise _Fail("max_trades_per_day", f"trades_today={trades}")

    def _step_max_open_positions(self, ctx: _StepCtx) -> None:
        ctx.mark("max_open_positions")
        if not ctx.is_buy:
            return
        open_count = sum(1 for p in ctx.state.positions.values() if p.token_units > 0)
        if open_count >= int(self._budget.max_open_positions):
            raise _Fail("max_open_positions", f"open={open_count}")

    def _step_already_open(self, ctx: _StepCtx) -> None:
        ctx.mark("already_open")
        if not ctx.is_buy:
            return
        pos = ctx.state.positions.get(ctx.order.mint)
        if pos is not None and pos.token_units > 0:
            raise _Fail("already_open", f"mint={ctx.order.mint}")

    def _step_creator_already_open(self, ctx: _StepCtx) -> None:
        ctx.mark("creator_already_open")
        if not ctx.is_buy or not self._limits.one_position_per_creator:
            return
        mint_creator = ctx.creator or self._creator_of(ctx.order.mint, ctx.state)
        if mint_creator and self._creator_open(mint_creator, ctx.state):
            raise _Fail("creator_already_open", f"creator={mint_creator}")

    def _step_max_trade_fraction(self, ctx: _StepCtx) -> None:
        ctx.mark("max_trade_fraction")
        if not ctx.is_buy:
            return
        assert ctx.final_size is not None
        cap = int(float(self._budget.max_trade_fraction) * ctx.equity)
        if ctx.final_size > cap:
            ctx.final_size = cap
            ctx.capped = True
            ctx.caps["max_trade_fraction"] = cap

    def _step_max_token_fraction(self, ctx: _StepCtx) -> None:
        ctx.mark("max_token_fraction")
        if not ctx.is_buy:
            return
        assert ctx.final_size is not None
        pos = ctx.state.positions.get(ctx.order.mint)
        basis = int(pos.cost_basis_lamports) if pos is not None else 0
        cap = int(float(self._budget.max_token_fraction) * ctx.equity) - basis
        if ctx.final_size > cap:
            if cap < int(self._limits.min_trade_lamports):
                raise _Fail("max_token_fraction", f"cap={cap} below minimum")
            ctx.final_size = cap
            ctx.capped = True
            ctx.caps["max_token_fraction"] = cap

    def _step_daily_loss_halt(self, ctx: _StepCtx) -> None:
        ctx.mark("daily_loss_halt")
        breach = self._detect_breach(
            ctx.state,
            ctx.equity,
            ts_utc=self._now_ts(),
            source=ctx.source,
            correlation_id=ctx.correlation_id,
        )
        if breach == "daily_loss":
            raise _Fail("daily_loss_halt", FLOOR_HALTED_DAILY)

    def _step_drawdown_halt(self, ctx: _StepCtx) -> None:
        ctx.mark("drawdown_halt")
        state = self._fold()
        ctx.state = state
        ctx.equity = self._equity_for_halts(state)
        breach = self._detect_breach(
            state,
            ctx.equity,
            ts_utc=self._now_ts(),
            source=ctx.source,
            correlation_id=ctx.correlation_id,
        )
        if breach == "drawdown":
            raise _Fail("drawdown_halt", "drawdown halt")

    def _step_data_stale(self, ctx: _StepCtx) -> None:
        ctx.mark("data_stale")
        if not any(p.token_units > 0 for p in ctx.state.positions.values()):
            return
        last_mtm = ctx.state.last_mtm_ts_utc
        if not last_mtm:
            raise _Fail("data_stale", "no MarkToMarket yet")
        age = self._clock.now() - parse_ts_utc(last_mtm)
        if age > float(self._limits.mtm_interval_s):
            raise _Fail("data_stale", f"mtm age {age:.1f}s")

    def _step_size_too_small(self, ctx: _StepCtx) -> None:
        ctx.mark("size_too_small")
        if not ctx.is_buy:
            return
        assert ctx.final_size is not None
        if ctx.final_size < int(self._limits.min_trade_lamports):
            raise _Fail("size_too_small", f"size={ctx.final_size}")

    def _step_below_liquidity_floor(self, ctx: _StepCtx) -> None:
        ctx.mark("below_liquidity_floor")
        if not ctx.is_buy:
            return
        assert ctx.final_size is not None
        reserves = self._get_reserves(ctx.order.mint) if self._get_reserves else None
        if reserves is None:
            raise _Fail("below_liquidity_floor", "no curve reserves")
        floor = int(self._budget.liquidity_floor_multiple) * ctx.final_size
        if reserves[0] < floor:
            raise _Fail("below_liquidity_floor", f"S0={reserves[0]} floor={floor}")

    def _open_breakers(self, state: LedgerState) -> set[str]:
        """Breakers open in the ledger fold (task 2 adds cooldown/half-open)."""
        return {name for name, view in state.breakers.items() if view.state == "open"}

    def _creator_of(self, mint: str, state: LedgerState) -> str:
        pos = state.positions.get(mint)
        if pos is not None and pos.creator:
            return str(pos.creator)
        for event in self._store.read(limit=None):
            if event["type"] != "PositionOpened":
                continue
            payload = event["payload"]
            if isinstance(payload, dict) and str(payload.get("mint", "")) == mint:
                return str(payload.get("creator", ""))
        return ""

    def _creator_open(self, creator: str, state: LedgerState) -> bool:
        return any(p.token_units > 0 and p.creator == creator for p in state.positions.values())

    def _ticket_approval(
        self, approvals: Mapping[str, ApprovalRecord], ticket_id: str
    ) -> ApprovalRecord | None:
        """First unconsumed approval for a ticket, any kind (step 7 gates kind)."""
        for record in approvals.values():
            if record.ticket_id == ticket_id:
                return record
        return None


class _suppress_integrity:
    """Idempotent halt rows: already-set or unwritable is not an error.

    A duplicate key means another path already recorded the breach. A
    latched handle (``LedgerInconsistent``) cannot record anything; the
    verify failure itself is the persistent signal, so the append is dropped.
    """

    def __enter__(self) -> _suppress_integrity:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return isinstance(exc, (sqlite3.IntegrityError, LedgerInconsistent))
