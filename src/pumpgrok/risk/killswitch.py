"""Kill switch state machine (paper-engine.md 5.4, R22, RISK-004).

Sources, in precedence order:

- env: ``PUMPGROK_KILLSWITCH`` set and not in ``{"", "0", "false"}``,
  snapshotted at construction (read once at start; an env var cannot
  change inside a running process).
- file: ``var/KILLSWITCH`` exists; the first line carries the reason, or
  ``FLATTEN`` (with an optional reason) when a flatten was requested.
- alert: an inbound ``KILL <reason>`` / ``KILL FLATTEN <reason>`` command
  line in the exact command shape (T-04-10); anything else is ignored.
- ledger: a ``KillSwitchSet`` row without a later ``KillSwitchCleared``.

The Telegram adapter writes ``var/KILLSWITCH``, so the file source is
authoritative and the switch survives restarts. First observation of an
active switch appends ``KillSwitchSet``; clear is human-only and refused
while any live source is still set. ``flatten_request`` waits on the
in-flight barrier and then closes every open position with reason
``kill_flatten``; the order-building half lives here, the driving loop
with the supervisor/adapter.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import Clock
from pumpgrok.ledger.store import LedgerStore

#: Exact alert command shape (T-04-10): ``KILL`` head, optional ``FLATTEN``
#: flag, mandatory reason. Bare ``KILL``, ``KILLX`` and lowercase are ignored.
KILL_LINE_RE = re.compile(r"^KILL(?:\s+FLATTEN)?\s+(?P<reason>.+)$")

#: Seat ids look like ``bot-04-sniper`` (core/bot.py SEAT_RE, R19); a clear
#: ``--by`` value must be human and must not match this shape.
SEAT_RE = re.compile(r"^bot-0[0-9]-[a-z-]+$")


def kill_switch_key(origin: str, reason: str, day_utc: str) -> str:
    """Idempotency per (origin, reason, utc_day) for ``KillSwitchSet`` rows."""
    body = f"KillSwitchSet|{origin}|{reason}|{day_utc}"
    return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class FlattenOrder:
    """One ``kill_flatten`` sell with its minted autonomous approval."""

    order: OrderRequest
    approval: ApprovalRecord


def parse_kill_line(line: str) -> tuple[bool, str] | None:
    """Parse an alert line: ``(flatten, reason)`` or ``None`` when not a command."""
    match = KILL_LINE_RE.match(line.strip())
    if match is None:
        return None
    head = line.strip().split(None, 2)[:2]
    return ("FLATTEN" in head, match.group("reason").strip())


def kill_file_text(reason: str, flatten: bool) -> str:
    """File body for an engagement: plain reason, or ``FLATTEN <reason>``."""
    return f"FLATTEN {reason}" if flatten else reason


@dataclass(frozen=True)
class KillState:
    """One poll outcome; ``active`` False carries empty source/reason."""

    active: bool
    source: str = ""
    reason: str = ""
    flatten_requested: bool = False


class ClearRefused(Exception):
    """The switch stays active: human-only rule or a live source persists."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class _SuppressIntegrity:
    """A duplicate set/clear key means another path recorded it already."""

    def __enter__(self) -> _SuppressIntegrity:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return isinstance(exc, sqlite3.IntegrityError)


def _file_state(line: str) -> KillState:
    """File source state for a stripped first line (empty file still engages)."""
    if line in ("FLATTEN", "FLATTEN:"):
        return KillState(True, "file", "flatten requested", True)
    if line.startswith("FLATTEN ") or line.startswith("FLATTEN:"):
        return KillState(True, "file", line[len("FLATTEN") :].lstrip(" :"), True)
    return KillState(True, "file", line, False)


class KillSwitch:
    """Polls kill sources, records first observation, gates human-only clear."""

    def __init__(
        self,
        clock: Clock,
        store: LedgerStore | None = None,
        killswitch_path: Path | str | None = None,
        alert_lines: Callable[[], list[str]] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._clock = clock
        self._store = store
        self._path = Path(killswitch_path) if killswitch_path is not None else None
        self._alert_lines = alert_lines
        start_env = dict(env) if env is not None else dict(os.environ)
        self._env_start = start_env.get("PUMPGROK_KILLSWITCH", "")

    def poll(self) -> KillState:
        """Current switch state; env (start) beats file beats alert beats ledger."""
        if self._env_start.strip() not in ("", "0", "false"):
            return KillState(True, "env", self._env_start.strip(), False)
        if self._path is not None and self._path.is_file():
            first = self._path.read_text(encoding="utf-8").splitlines()
            line = first[0].strip() if first else ""
            return _file_state(line)
        if self._alert_lines is not None:
            for raw in self._alert_lines():
                parsed = parse_kill_line(raw)
                if parsed is not None:
                    flatten, reason = parsed
                    return KillState(True, "alert_command", reason, flatten)
        if self._store is not None:
            row = self._latest_set()
            if row is not None:
                payload = row["payload"]
                return KillState(
                    True,
                    str(payload.get("origin", "command")),
                    str(payload.get("reason", "")),
                    bool(payload.get("flatten_requested", False)),
                )
        return KillState(False)

    def observe(
        self, *, ts_utc: str, source: str = "paper", correlation_id: str = "desk"
    ) -> dict[str, Any] | None:
        """Append ``KillSwitchSet`` on first observation of an active switch."""
        if self._store is None:
            return None
        state = self.poll()
        if not state.active or self._latest_set() is not None:
            return None
        row: dict[str, Any] = {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": kill_switch_key(state.source, state.reason, ts_utc[:10]),
            "type": "KillSwitchSet",
            "payload": {
                "source": source,
                "origin": state.source,
                "reason": state.reason,
                "flatten_requested": state.flatten_requested,
                "set_by": "risk_engine",
            },
        }
        with _SuppressIntegrity():
            self._store.append(**row)
        return row

    def live_sources(self) -> list[str]:
        """Live sources currently set: env-now, file, alert (ledger excluded)."""
        live: list[str] = []
        env_now = os.environ.get("PUMPGROK_KILLSWITCH", "").strip()
        if env_now not in ("", "0", "false") or self._env_start not in ("", "0", "false"):
            live.append("env")
        if self._path is not None and self._path.is_file():
            live.append("file")
        if self._alert_lines is not None:
            for raw in self._alert_lines():
                if parse_kill_line(raw) is not None:
                    live.append("alert_command")
                    break
        return live

    def request_clear(
        self,
        approval: ApprovalRecord,
        reason: str,
        *,
        ts_utc: str,
        source: str = "paper",
        correlation_id: str = "desk",
    ) -> dict[str, Any]:
        """Append ``KillSwitchCleared`` plus the ``killswitch_clear`` approval.

        Human-only: ``cleared_by`` must start with ``human:`` and must not
        match a seat id (the G-2 rule). Refused while any live source persists.
        Both rows land in one atomic batch: a duplicate clear key is an
        explicit refusal ("already cleared, re-poll"), never a false success.
        """
        by = approval.approved_by
        if not by.startswith("human:") or SEAT_RE.match(by.removeprefix("human:")):
            raise ClearRefused(f"clear must come from a human, got {by!r}")
        if approval.kind != "killswitch_clear":
            raise ClearRefused(f"clear needs a killswitch_clear approval, got {approval.kind!r}")
        live = self.live_sources()
        if live:
            raise ClearRefused(f"live sources still set: {','.join(live)}")
        if self._store is None:
            raise ClearRefused("no ledger bound")
        cleared: dict[str, Any] = {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": kill_switch_key("clear", reason, ts_utc[:10]),
            "type": "KillSwitchCleared",
            "payload": {
                "source": source,
                "cleared_by": by,
                "approval_id": approval.id,
                "sources_now_clear": [],
            },
        }
        consumed: dict[str, Any] = {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"consumed|{approval.id}",
            "type": "ApprovalRecorded",
            "payload": {
                "source": source,
                "id": approval.id,
                "kind": approval.kind,
                "approved_by": by,
                "at": approval.at.isoformat(),
                "ticket_id": approval.ticket_id or "",
                "mint": approval.mint or "",
                "size_lamports": approval.size_lamports or 0,
                "token_units": approval.token_units or 0,
                "max_slippage_bps": approval.max_slippage_bps or 0,
                "exit_rule_id": approval.exit_rule_id or "",
                "raw_message": reason,
                "consumed": True,
            },
        }
        if self._store.by_key(str(cleared["idempotency_key"])) is not None:
            raise ClearRefused(f"kill switch already cleared for {reason!r}: re-poll state")
        if self._store.by_key(str(consumed["idempotency_key"])) is not None:
            raise ClearRefused(f"killswitch_clear approval {approval.id} is already consumed")
        self._store.append_batch([cleared, consumed])
        return cleared

    def _latest_set(self) -> dict[str, Any] | None:
        assert self._store is not None
        latest: dict[str, Any] | None = None
        for event in self._store.read(limit=None):
            if event["type"] == "KillSwitchSet":
                payload = event.get("payload")
                if isinstance(payload, dict):
                    latest = event
            elif event["type"] == "KillSwitchCleared":
                latest = None
        return latest


class InflightBarrier:
    """Tracks ACCEPTED/CONFIRMING orders; flatten waits until the set is empty.

    The adapter owns the production barrier (paper-engine.md 2.8); this is
    the shared primitive so the engine, adapter and tests agree on semantics.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._inflight: set[str] = set()

    def register(self, key: str) -> None:
        """Mark one order accepted (idempotent for repeats)."""
        with self._cond:
            self._inflight.add(key)

    def done(self, key: str) -> None:
        """Mark one order settled and wake waiters when the set drains."""
        with self._cond:
            self._inflight.discard(key)
            if not self._inflight:
                self._cond.notify_all()

    def __len__(self) -> int:
        with self._cond:
            return len(self._inflight)

    def wait_empty(self, timeout_s: float = 30.0) -> bool:
        """Block until no order is inflight; False on timeout."""
        with self._cond:
            return self._cond.wait_for(lambda: not self._inflight, timeout=timeout_s)
