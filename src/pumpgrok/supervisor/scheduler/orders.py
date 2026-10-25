"""Replay order placement through granted tools: sniper buys, exit rule sells."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from pumpgrok.core.ids import CorrelationId, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.engine.pipeline import BUY
from pumpgrok.logging.json import bind_seat
from pumpgrok.supervisor.exit_rules import ExitRules, RuleSell
from pumpgrok.supervisor.scheduler.replay_runtime import (
    EXIT_SEAT,
    REPLAY_BUY_LAMPORTS,
    REPLAY_SLIPPAGE_BPS,
    REPLAY_TICKET,
    RISK_ROW_TYPES,
    TRADE_ROW_TYPES,
    ReplayRuntime,
    _await_order,
    _replay_trade,
    _ReplayTrading,
)
from pumpgrok.supervisor.scheduler.supervisor import rollover_key

log = logging.getLogger("pumpgrok.supervisor.scheduler")


async def _place_candidates(trading: _ReplayTrading) -> dict[str, Any]:
    """Place each BUY candidate once, when the recorded timeline reaches its tick.

    A candidate waits until the clock is at or past its own tick, and is never priced
    from a later one. The tool resolves through the sniper's roster grant, so risk and
    PaperAdapter approve or veto each order, and the attempt with its outcome is recorded.
    """
    for index, candidate in enumerate(trading.candidates):
        if candidate.verdict.decision != BUY or index in trading.attempted:
            continue
        if candidate.ts > trading.clock.now():
            continue  # the recording has not reached this candidate yet
        trading.attempted.add(index)
        if trading.refresh_marks is not None:
            await trading.refresh_marks()
        mint = candidate.token.mint
        decision_id = trading.ids.ulid()
        payload = trading.place.spec.input_model.model_validate(
            {
                "ticket_id": REPLAY_TICKET,
                "mint": mint,
                "side": "buy",
                "decision_id": decision_id,
                "size_lamports": REPLAY_BUY_LAMPORTS,
                "max_slippage_bps": REPLAY_SLIPPAGE_BPS,
                "approval_id": f"apr-{trading.ids.ulid()}",
            }
        )
        with bind_seat("bot-04-sniper"), bind_correlation(CorrelationId.new(trading.ids)):
            settled = await _await_order(trading.clock, trading.place(payload))
        result = settled.model_dump(mode="json")
        outcome = str(result["status"])
        reason = str(result["reason"] or ("ok" if outcome == "filled" else ""))
        trading.attempts.append(
            _replay_trade(
                trading.store,
                side="buy",
                mint=mint,
                outcome=outcome,
                reason=reason,
                decision_id=decision_id,
            )
        )
    return {"orders": len(trading.attempts)}


def _check_cycle_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    """Only day-keyed ``DailyRollover`` rows and the sniper's order rows may be new."""
    for row in rows:
        row_type = row.get("type")
        if row_type == "DailyRollover":
            day = str((row.get("payload") or {}).get("day_utc", ""))
            if not day or row.get("idempotency_key") != rollover_key(day):
                raise RuntimeError("replay seat cycles wrote an unkeyed DailyRollover")
        elif row_type in TRADE_ROW_TYPES or row_type in RISK_ROW_TYPES:
            continue
        elif row_type == "Escalation" and (row.get("payload") or {}).get("kind") == "graduated":
            continue  # the exit seat closed a graduated position (exit_rules._close_graduated)
        else:
            raise RuntimeError(f"replay seat cycles wrote an unexpected {row_type} row")


async def _place_rule_sell(
    trading: _ReplayTrading, mint: str, ticket: str, units: int, rule: str
) -> dict[str, Any]:
    """Submit one rule sell through the exit seat's granted ``exec.place`` (TOOL-009)."""
    if trading.exit_place is None:
        raise RuntimeError("exit seat has no granted exec.place")
    decision_id = trading.ids.ulid()
    payload = trading.exit_place.spec.input_model.model_validate(
        {
            "ticket_id": ticket,
            "mint": mint,
            "side": "sell",
            "decision_id": decision_id,
            "token_units": units,
            "max_slippage_bps": REPLAY_SLIPPAGE_BPS,
            "approval_id": f"apr-{trading.ids.ulid()}",
            "exit_reason": rule,
        }
    )
    with bind_seat(EXIT_SEAT), bind_correlation(CorrelationId.new(trading.ids)):
        settled = await _await_order(trading.clock, trading.exit_place(payload))
    result: dict[str, Any] = settled.model_dump(mode="json")
    outcome = str(result["status"])
    reason = str(result["reason"] or ("ok" if outcome == "filled" else ""))
    trading.attempts.append(
        _replay_trade(
            trading.store,
            side="sell",
            mint=mint,
            outcome=outcome,
            reason=reason,
            rule=rule,
            decision_id=decision_id,
        )
    )
    return result


async def _run_exit_rules(trading: _ReplayTrading) -> list[RuleSell]:
    """One exit pass at the current clock: the rules see the price as of this tick."""
    if trading.exits is None:
        return []
    return await trading.exits.check(trading.clock.now())


def _replay_trading(runtime: ReplayRuntime) -> _ReplayTrading:
    """Resolve the sniper's and the exit seat's ``exec.place`` through their roster grants.

    Each grant is resolved through the registry, so a seat without one cannot place. The
    exit seat sells only through its own grant, and only on a rule that fired.
    """
    with bind_correlation(CorrelationId.new(runtime.ids)):
        place = runtime.registry.find(
            "exec.place",
            max_side_effect=SideEffect.PAPER_WRITE,
            bot=runtime.manifests["bot-04-sniper"],
        )
        exit_place = runtime.registry.find(
            "exec.place",
            max_side_effect=SideEffect.PAPER_WRITE,
            bot=runtime.manifests[EXIT_SEAT],
        )

    async def refresh_marks() -> None:
        """Write one combined mark for every held mint at this instant.

        A position without a fresh mark is refused as data_stale and counts as zero value in
        loss checks, so the replay refreshes marks before risk checks and before each order.
        Each mint keeps the recorded time of its own tick, so a silent mint stays visibly old.
        """
        await runtime.adapter.mark_open_positions(source="replay")

    trading = _ReplayTrading(
        clock=runtime.clock,
        ids=runtime.ids,
        place=place,
        candidates=runtime.candidates,
        exit_place=exit_place,
        refresh_marks=refresh_marks,
        store=runtime.store,
    )

    async def place_sell(mint: str, ticket: str, units: int, rule: str) -> dict[str, Any]:
        return await _place_rule_sell(trading, mint, ticket, units, rule)

    async def close_graduated(mint: str, last_s: int, last_t: int) -> dict[str, Any] | None:
        """Close a graduated position at its last open reserves; book it as a trade."""
        with bind_seat(EXIT_SEAT):
            row = await runtime.adapter.close_on_graduation(
                mint, last_s=last_s, last_t=last_t, source="replay"
            )
        if row is not None:
            trading.attempts.append(
                _replay_trade(
                    trading.store,
                    side="sell",
                    mint=mint,
                    outcome="filled",
                    reason="ok",
                    rule="graduated",
                )
            )
        return row

    trading.exits = ExitRules(
        store=runtime.store,
        curves=runtime.curves,
        exits=runtime.exits,
        clock=runtime.clock,
        place_sell=place_sell,
        graduate=close_graduated,
    )
    return trading
