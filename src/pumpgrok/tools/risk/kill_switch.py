"""risk.kill_switch: set the global kill switch or request a flatten (TOOL-005).

Actions ``set`` and ``flatten_request`` only: ``clear`` is not a tool action
(R22) - it is the human CLI, and it fails input validation here. A set
appends a ``KillSwitchSet`` ledger event with a minute-derived idempotency
key, so repeats within the minute replay instead of duplicating.

A ``flatten_request`` (RISK-004) runs :func:`execute_flatten` after the set
is recorded: it waits for the in-flight barrier to go idle, then closes every
open position with reason ``kill_flatten`` through the injected async
``close_position``. If the barrier does not clear within its bound, nothing
is closed and the response reports ``blocked``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import sqlite3
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.risk.killswitch import InflightBarrier, env_engaged, kill_file_text
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.tools._common import meta_now

__all__ = [
    "FLATTEN_BARRIER_TIMEOUT_S",
    "KILL_SWITCH_SPEC",
    "FlattenIntent",
    "FlattenOutcome",
    "FlattenResult",
    "KillSwitchIn",
    "KillSwitchOut",
    "build_kill_switch_tool",
    "execute_flatten",
    "kill_switch_key",
    "run_kill_switch",
]

log = logging.getLogger(__name__)

#: Margin on top of the adapter's confirmation bound for the barrier wait (RISK-004).
FLATTEN_BARRIER_MARGIN_S = 5.0

#: Bound on the in-flight barrier wait. An order can legitimately stay in flight for the
#: adapter's ``confirm_timeout_s``, so the wait covers that bound plus a margin.
FLATTEN_BARRIER_TIMEOUT_S = EngineLimits().confirm_timeout_s + FLATTEN_BARRIER_MARGIN_S

#: Time allowed for the closing work after the barrier clears.
FLATTEN_CLOSE_BUDGET_S = 30.0

#: ``async close_position(*, mint, ticket_id, reason) -> dict``. The paper
#: adapter returns ``{"status": "closed", ...}`` only when the sell and the
#: ``PositionClosed`` row are written; any other status is not flattened.
ClosePosition = Callable[..., Awaitable[Mapping[str, Any]]]


class KillSwitchIn(ToolInput):
    """Engage the switch or request a flatten; ``clear`` is CLI-only."""

    action: Literal["set", "flatten_request"]
    reason: str = Field(min_length=1, max_length=500)


class FlattenIntent(BaseModel):
    """One open position a flatten must close with reason ``kill_flatten``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mint: str
    ticket_id: str
    token_units: int


class FlattenOutcome(BaseModel):
    """Per-position result: ``closed``, or ``not_flattened`` with the adapter status."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mint: str
    ticket_id: str
    status: Literal["closed", "not_flattened"]
    detail: str = ""


class FlattenResult(BaseModel):
    """Flatten run: ``completed`` after the barrier cleared, ``blocked`` if it did not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["completed", "blocked", "unavailable"]
    detail: str = ""
    outcomes: list[FlattenOutcome] = Field(default_factory=list)


class KillSwitchOut(ToolOutput):
    """Combined switch view: env, file and ledger causes, plus flatten status."""

    active: bool
    since: datetime | None = None
    source: Literal["env", "file", "command", "none"]
    flatten_requested: bool = False
    reason: str | None = None
    flatten_status: Literal[
        "not_requested", "completed", "incomplete", "blocked", "unavailable"
    ] = "not_requested"
    flatten_detail: str = ""
    flatten_outcomes: list[FlattenOutcome] = Field(default_factory=list)


KILL_SWITCH_SPEC = ToolSpec(
    name="risk.kill_switch",
    description=(
        "Set the global kill switch or request a flatten of every open paper "
        "position. A flatten waits for in-flight orders, then sells each open "
        "position with reason kill_flatten. Clear is the human CLI, never this tool."
    ),
    input_model=KillSwitchIn,
    output_model=KillSwitchOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=FLATTEN_BARRIER_TIMEOUT_S + FLATTEN_CLOSE_BUDGET_S,
    rate_limit_key="killswitch",
    idempotent=True,
    backend="pumpgrok.ledger.store.LedgerStore",
)


def kill_switch_key(action: str, reason: str, clock: Clock) -> str:
    """Minute-derived idempotency key: d(tool, action, reason, UTC minute)."""
    minute = datetime.fromtimestamp(clock.now(), UTC).strftime("%Y-%m-%dT%H:%M")
    digest = hashlib.sha256(f"{action}\n{reason}\n{minute}".encode()).hexdigest()
    return digest[:32]


async def execute_flatten(
    intents: Callable[[], Sequence[FlattenIntent]],
    *,
    barrier: InflightBarrier,
    close_position: ClosePosition,
    barrier_timeout_s: float = FLATTEN_BARRIER_TIMEOUT_S,
    open_mints: Callable[[], Iterable[str]] | None = None,
) -> FlattenResult:
    """Wait for in-flight orders to settle, then close each open position.

    ``intents`` is called only after the barrier is idle, so the positions it
    lists include any order that filled while the barrier drained. If the
    barrier does not clear within ``barrier_timeout_s``, nothing is closed and
    the result is ``blocked`` (fail closed). Otherwise ``close_position`` runs
    once per intent with ``reason="kill_flatten"``. A position counts as closed
    only when the adapter returns status ``closed``; a refusal or a
    ``PumpgrokError`` marks that position ``not_flattened`` and the remaining
    positions still close.

    A ``no_position`` answer is ambiguous: the position may have been closed by another caller
    (an overlapping ``flatten`` or a gateway poll) that selected it too. After the loop,
    ``open_mints`` re-reads the ledger, and a ``no_position`` outcome counts as ``closed`` only
    when its mint is no longer open. A mint still listed stays ``not_flattened``. Without
    ``open_mints`` every ``no_position`` stays ``not_flattened`` (fail closed).
    """
    cleared = await asyncio.to_thread(barrier.wait_empty, barrier_timeout_s)
    if not cleared:
        return FlattenResult(
            status="blocked",
            detail=f"in-flight orders did not clear within {barrier_timeout_s:g}s; nothing closed",
        )
    outcomes: list[FlattenOutcome] = []
    for intent in intents():
        try:
            result = await close_position(
                mint=intent.mint, ticket_id=intent.ticket_id, reason="kill_flatten"
            )
        except PumpgrokError as exc:
            outcomes.append(
                FlattenOutcome(
                    mint=intent.mint,
                    ticket_id=intent.ticket_id,
                    status="not_flattened",
                    detail=exc.message,
                )
            )
            continue
        except Exception as exc:
            # Any other failure is this position's alone: record it and keep closing the rest.
            outcomes.append(
                FlattenOutcome(
                    mint=intent.mint,
                    ticket_id=intent.ticket_id,
                    status="not_flattened",
                    detail=type(exc).__name__,
                )
            )
            continue
        adapter_status = str(result.get("status", ""))
        if adapter_status == "closed":
            outcomes.append(
                FlattenOutcome(mint=intent.mint, ticket_id=intent.ticket_id, status="closed")
            )
        else:
            outcomes.append(
                FlattenOutcome(
                    mint=intent.mint,
                    ticket_id=intent.ticket_id,
                    status="not_flattened",
                    detail=f"status={adapter_status}",
                )
            )
    if open_mints is not None and any(_is_no_position(o) for o in outcomes):
        still_open = set(open_mints())
        outcomes = [_settle_already_closed(o, still_open) for o in outcomes]
    return FlattenResult(status="completed", outcomes=outcomes)


def _is_no_position(outcome: FlattenOutcome) -> bool:
    return outcome.status == "not_flattened" and outcome.detail == "status=no_position"


def _settle_already_closed(outcome: FlattenOutcome, still_open: set[str]) -> FlattenOutcome:
    """A ``no_position`` outcome whose mint the ledger no longer lists was closed elsewhere."""
    if _is_no_position(outcome) and outcome.mint not in still_open:
        return FlattenOutcome(
            mint=outcome.mint,
            ticket_id=outcome.ticket_id,
            status="closed",
            detail="closed by another caller",
        )
    return outcome


async def run_kill_switch(
    inp: KillSwitchIn,
    store: LedgerStore,
    clock: Clock,
    killswitch_path: Path | None = None,
    *,
    close_position: ClosePosition | None = None,
    barrier: InflightBarrier | None = None,
    barrier_timeout_s: float = FLATTEN_BARRIER_TIMEOUT_S,
) -> dict[str, Any]:
    """Append the set event (idempotent per minute), write the file, run any flatten.

    The file write makes the engagement survive restarts: the engine polls
    the file source on every check (design 5.4). Clear stays CLI-only, so
    this tool accepts ``set`` and ``flatten_request`` only. A flatten with no
    ``close_position`` wired reports ``unavailable`` and closes nothing.
    """
    ambient = ambient_correlation()
    correlation = inp.correlation_id or (str(ambient) if ambient else "none")
    ts_utc = datetime.fromtimestamp(clock.now(), UTC).isoformat()
    key = kill_switch_key(inp.action, inp.reason, clock)
    flatten = inp.action == "flatten_request"
    # Same minute repeat: the stored row already carries this intent.
    with contextlib.suppress(sqlite3.IntegrityError):
        store.append(
            ts_utc=ts_utc,
            source="paper",
            correlation_id=correlation,
            idempotency_key=key,
            type="KillSwitchSet",
            payload={
                "source": "paper",
                "origin": "tool",
                "reason": inp.reason,
                "flatten_requested": flatten,
                "set_by": "risk.kill_switch",
            },
        )
    if killswitch_path is not None:
        text = kill_file_text(inp.reason, flatten)
        await asyncio.to_thread(killswitch_path.write_text, text, encoding="utf-8")
    result: FlattenResult | None = None
    if flatten:
        if close_position is None:
            result = FlattenResult(
                status="unavailable",
                detail="no position closer is wired; nothing closed",
            )
        elif barrier is None:
            raise ValueError("a flatten closer needs the adapter's in-flight barrier")
        else:
            result = await execute_flatten(
                lambda: _flatten_intents(store),
                barrier=barrier,
                close_position=close_position,
                barrier_timeout_s=barrier_timeout_s,
                open_mints=lambda: [i.mint for i in _flatten_intents(store)],
            )
    return _status(store, killswitch_path, correlation, clock, result)


def _reported_flatten_status(flatten: FlattenResult | None) -> str:
    """The flatten status the caller sees: ``completed`` only when every position closed.

    A run whose outcomes include a position that did not close reports ``incomplete``, so no
    reader can take a partly-flattened book for a flat one (G7). ``blocked`` and ``unavailable``
    runs already name themselves and are reported as they are.
    """
    if flatten is None:
        return "not_requested"
    if flatten.status == "completed" and any(o.status != "closed" for o in flatten.outcomes):
        return "incomplete"
    return flatten.status


def _status(
    store: LedgerStore,
    killswitch_path: Path | None,
    correlation: str,
    clock: Clock,
    flatten: FlattenResult | None = None,
) -> dict[str, Any]:
    """Fold env, file and ledger causes into one view."""
    env_set = env_engaged(os.environ.get("PUMPGROK_KILLSWITCH"))
    file_set = killswitch_path is not None and killswitch_path.is_file()
    latest_set: dict[str, Any] | None = None
    cleared_after = False
    for event in store.read(limit=None):
        if event["type"] == "KillSwitchSet":
            latest_set = event
            cleared_after = False
        elif event["type"] == "KillSwitchCleared":
            cleared_after = True
    ledger_active = latest_set is not None and not cleared_after
    active = env_set or file_set or ledger_active
    if env_set:
        source: Literal["env", "file", "command", "none"] = "env"
    elif file_set:
        source = "file"
    elif ledger_active:
        # Ledger engagements come only from the command path (CLI or tool).
        source = "command"
    else:
        source = "none"
    since = None
    reason = None
    flatten_requested = False
    if ledger_active and latest_set is not None:
        since = datetime.fromisoformat(str(latest_set["ts_utc"]))
        reason = str(latest_set["payload"].get("reason"))
        flatten_requested = bool(latest_set["payload"].get("flatten_requested", False))
    return KillSwitchOut.model_validate(
        {
            "active": active,
            "since": since,
            "source": source,
            "flatten_requested": flatten_requested,
            "reason": reason,
            "flatten_status": _reported_flatten_status(flatten),
            "flatten_detail": flatten.detail if flatten is not None else "",
            "flatten_outcomes": [o.model_dump() for o in flatten.outcomes] if flatten else [],
            "meta": meta_now("killswitch", correlation, clock),
        }
    ).model_dump()


def _flatten_intents(store: LedgerStore) -> list[FlattenIntent]:
    """One intent per position still holding units, folded from the ledger."""
    state = initial_state(source="paper", initial_equity_lamports=0, day_utc="")
    for event in store.read(limit=None):
        state = reduce(state, event)
    return [
        FlattenIntent(mint=pos.mint, ticket_id=pos.ticket_id, token_units=pos.token_units)
        for pos in state.positions.values()
        if pos.token_units > 0
    ]


def flatten_hook_for(
    store: LedgerStore,
    barrier: InflightBarrier,
    close_position: ClosePosition,
) -> Callable[[], Awaitable[None]]:
    """Bind the kill-poll flatten to one store, in-flight barrier and position closer (RISK-004).

    The engine calls the returned hook from ``RiskEngine.poll_kill_sources`` whenever a flatten
    is requested, so an alert ``KILL FLATTEN`` is honoured without any order check.
    """

    async def _flatten() -> None:
        result = await execute_flatten(
            lambda: _flatten_intents(store),
            barrier=barrier,
            close_position=close_position,
            open_mints=lambda: [i.mint for i in _flatten_intents(store)],
        )
        # G7: a position the flatten did not close stays open. Say so at ERROR, with the mint
        # and the adapter's detail. Nothing here records the flatten as complete; the request
        # stays set, so the next poll retries the positions that are still open.
        if result.status != "completed":
            log.error(
                "kill flatten did not complete: status=%s detail=%s", result.status, result.detail
            )
        for outcome in result.outcomes:
            if outcome.status != "closed":
                log.error(
                    "kill flatten left a position open: mint=%s ticket=%s status=%s detail=%s",
                    outcome.mint,
                    outcome.ticket_id,
                    outcome.status,
                    outcome.detail,
                )

    return _flatten


def build_kill_switch_tool(
    store: LedgerStore,
    clock: Clock,
    killswitch_path: Path | None = None,
    *,
    close_position: ClosePosition | None = None,
    barrier: InflightBarrier | None = None,
) -> Tool:
    """Bind ``risk.kill_switch`` to one store, clock, file path and position closer.

    A position closer must come with the adapter's in-flight barrier: without it
    a flatten would not wait for live orders. The refusal happens here, at wiring.
    """
    if close_position is not None and barrier is None:
        raise ValueError("a flatten closer needs the adapter's in-flight barrier")

    @tool(KILL_SWITCH_SPEC)
    async def _kill_switch(payload: KillSwitchIn) -> dict[str, Any]:
        return await run_kill_switch(
            payload,
            store,
            clock,
            killswitch_path,
            close_position=close_position,
            barrier=barrier,
        )

    return _kill_switch
