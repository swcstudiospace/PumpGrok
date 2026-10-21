"""risk.kill_switch: set the global kill switch or request a flatten (TOOL-005).

Actions ``set`` and ``flatten_request`` only: ``clear`` is not a tool action
(R22) — it is the human CLI, and it fails input validation here. A set
appends a ``KillSwitchSet`` ledger event with a minute-derived idempotency
key, so repeats within the minute replay instead of duplicating.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.risk.killswitch import kill_file_text
from pumpgrok.tools._common import meta_now

__all__ = [
    "KILL_SWITCH_SPEC",
    "KillSwitchIn",
    "KillSwitchOut",
    "build_kill_switch_tool",
    "kill_switch_key",
    "run_kill_switch",
]


class KillSwitchIn(ToolInput):
    """Engage the switch or request a flatten; ``clear`` is CLI-only."""

    action: Literal["set", "flatten_request"]
    reason: str = Field(min_length=1, max_length=500)


class KillSwitchOut(ToolOutput):
    """Combined switch view: env, file and ledger causes."""

    active: bool
    since: datetime | None = None
    source: Literal["env", "file", "command", "none"]
    flatten_requested: bool = False
    reason: str | None = None


KILL_SWITCH_SPEC = ToolSpec(
    name="risk.kill_switch",
    description=(
        "Set the global kill switch or request a flatten of every open paper "
        "position. Clear is the human CLI, never this tool."
    ),
    input_model=KillSwitchIn,
    output_model=KillSwitchOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=5.0,
    rate_limit_key="killswitch",
    idempotent=True,
    backend="pumpgrok.ledger.store.LedgerStore",
)


def kill_switch_key(action: str, reason: str, clock: Clock) -> str:
    """Minute-derived idempotency key: d(tool, action, reason, UTC minute)."""
    minute = datetime.fromtimestamp(clock.now(), UTC).strftime("%Y-%m-%dT%H:%M")
    digest = hashlib.sha256(f"{action}\n{reason}\n{minute}".encode()).hexdigest()
    return digest[:32]


async def run_kill_switch(
    inp: KillSwitchIn,
    store: LedgerStore,
    clock: Clock,
    killswitch_path: Path | None = None,
) -> dict[str, Any]:
    """Append the set event (idempotent per minute), write the file, report the view.

    The file write makes the engagement survive restarts: the engine polls
    the file source on every check (design 5.4). Clear stays CLI-only, so
    this tool accepts ``set`` and ``flatten_request`` only.
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
    return _status(store, killswitch_path, correlation, clock)


def _status(
    store: LedgerStore, killswitch_path: Path | None, correlation: str, clock: Clock
) -> dict[str, Any]:
    """Fold env, file and ledger causes into one view."""
    env_set = os.environ.get("PUMPGROK_KILLSWITCH", "").strip() == "1"
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
            "meta": meta_now("killswitch", correlation, clock),
        }
    ).model_dump()


def build_kill_switch_tool(
    store: LedgerStore, clock: Clock, killswitch_path: Path | None = None
) -> Tool:
    """Bind ``risk.kill_switch`` to one store, clock and file path."""

    @tool(KILL_SWITCH_SPEC)
    async def _kill_switch(payload: KillSwitchIn) -> dict[str, Any]:
        return await run_kill_switch(payload, store, clock, killswitch_path)

    return _kill_switch
