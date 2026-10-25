"""The 19 R34 step checks plus halt detection mixed into RiskEngine."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from pumpgrok.core.errors import CorruptState
from pumpgrok.core.ids import calling_seat
from pumpgrok.ledger.reducer import LedgerState
from pumpgrok.ledger.store import LedgerInconsistent
from pumpgrok.ledger.views import equity_lamports
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.risk.engine.constants import (
    BUY_SEAT,
    FLOOR_HALTED_DAILY,
    RULE_EXIT_REASONS,
    SELL_SEAT,
    SYSTEM_EXIT_REASONS,
)
from pumpgrok.risk.engine.model import _Fail, _StepCtx, _suppress_integrity, halt_key


class _EngineSteps:
    """The 19 R34 step checks plus halt detection."""

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
        """Detect fresh daily-loss and drawdown breaches and append ``HaltSet``.

        Returns the breach reason (``daily_loss`` or ``drawdown``) or ``None``.
        Raises ``CorruptState`` when day-start equity is not positive.
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

    def _cleared_today(self, today: str) -> bool:
        """A human clear today suppresses re-detection for the rest of the day.

        The halt stays meaningful (a fresh day re-evaluates from the day-start
        baseline) while the clear stays effective (the same ongoing condition
        does not re-trip until tomorrow).
        """
        for event in self._store.read(limit=None):
            if event["type"] == "HaltCleared" and str(event.get("ts_utc", ""))[:10] == today:
                return True
        return False

    def _detect_breach(
        self,
        state: LedgerState,
        equity: int,
        *,
        ts_utc: str,
        source: str,
        correlation_id: str,
    ) -> str | None:
        if self._cleared_today(ts_utc[:10]):
            return None
        day_start = int(state.day_start_equity_lamports)
        peak = int(state.peak_equity_lamports)
        if day_start <= 0:
            raise CorruptState(
                f"daily-loss check failed: day-start equity is {day_start}; "
                "refusing to treat it as zero loss"
            )
        # Integer cross-multiplication: the loss in lamports over the day-start
        # baseline meets the halt fraction without any float ratio.
        loss_lamports = day_start - equity
        limit = Fraction(str(self._budget.daily_loss_halt_fraction))
        drawdown_limit = float(self._budget.drawdown_halt_fraction)
        if loss_lamports * limit.denominator >= day_start * limit.numerator:
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
        # R62: a degraded reputation book fails closed for buys only. Exit
        # sells skip this step, and manual sells are not new entries, so
        # exits and kill-flatten still run while buys refuse.
        if ctx.is_buy and self._reputation is not None and self._reputation.degraded:
            self._write_reputation_escalation(ctx)
            raise _Fail("reputation_degraded", "reputation book degraded")
        if ctx.open_breakers:
            raise _Fail("breaker_open", f"breaker={sorted(ctx.open_breakers)[0]}")
        if ctx.order.mint in ctx.killed:
            raise _Fail("breaker_open", f"risk_kill:{ctx.order.mint}")
        if ctx.half_blocked:
            raise _Fail("breaker_open", "probe inflight")

    def _write_reputation_escalation(self, ctx: _StepCtx) -> None:
        """One Escalation per UTC day while the reputation book is degraded."""
        source = ctx.source if ctx.source in ("paper", "replay", "manual") else "paper"
        day = self._now_ts()[:10]
        with _suppress_integrity():
            self._store.append(
                ts_utc=self._now_ts(),
                source=source,
                correlation_id=ctx.correlation_id,
                idempotency_key=f"reputation-degraded|{day}",
                type="Escalation",
                payload={
                    "source": source,
                    "kind": "reputation_degraded",
                    "seat": "bot-02-risk",
                    "detail": "reputation book degraded: buys refused until restore or rebuild",
                },
            )

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
        presented = ctx.order.approval_id
        approval = ctx.approvals.get(presented) if presented else None
        if approval is None or approval.ticket_id != ctx.order.ticket_id:
            raise _Fail("approval_missing", "no unconsumed approval for the presented id")
        ctx.approval = approval
        ctx.approval_id = approval.id

    def _step_approval_mismatch(self, ctx: _StepCtx) -> None:
        ctx.mark("approval_mismatch")
        approval = ctx.approval
        if approval is not None and approval.approved_by == "risk_engine":
            return
        names_other_rule = (
            approval is not None
            and approval.kind == "exit_rule"
            and ctx.exit_reason in RULE_EXIT_REASONS
            and approval.exit_rule_id != ctx.exit_reason
        )
        if names_other_rule:
            raise _Fail("approval_mismatch", "exit_rule approval names another rule")
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
        if "bot-06-exit" in self._observe_only and ctx.is_buy:
            # Open positions are unmanaged while EXIT is latched: no new entries, even before
            # its HaltSet is recorded.
            raise _Fail("seat_may_trade", "exit seat latched: buys off desk-wide")
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
        cap = int(self._budget.max_trade_fraction * ctx.equity)
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
        cap = int(self._budget.max_token_fraction * ctx.equity) - basis
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
        now = self._clock.now()
        limit = float(self._limits.mtm_interval_s)
        # Every held mint must carry a mark younger than the limit: a silent mint makes the
        # whole balance stale, however fresh the other mints are.
        for mint, pos in ctx.state.positions.items():
            if pos.token_units <= 0:
                continue
            if not pos.last_mtm_ts_utc:
                raise _Fail("data_stale", f"mint={mint} no MarkToMarket yet")
            age = now - parse_ts_utc(pos.last_mtm_ts_utc)
            if age > limit:
                raise _Fail("data_stale", f"mint={mint} mtm age {age:.1f}s")

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
