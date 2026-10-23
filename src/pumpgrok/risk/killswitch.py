"""Kill switch state machine (paper-engine.md 5.4, R22, RISK-004).

Sources, in precedence order:

- env: ``PUMPGROK_KILLSWITCH`` set and not in ``{"", "0", "false"}``,
  snapshotted at construction (read once at start; an env var cannot
  change inside a running process).
- file: ``<data_dir>/KILLSWITCH`` exists; in the desk that is
  ``var/desk/KILLSWITCH``. The first line carries the reason, or
  ``FLATTEN`` (with an optional reason) when a flatten was requested.
  This is the one latch path: every writer resolves it through
  :func:`killswitch_file`.
- ledger: a ``KillSwitchSet`` row without a later ``KillSwitchCleared``.

The alert command (``KILL <reason>`` / ``KILL FLATTEN <reason>``, exact
shape per T-04-10) is a writer, not a separate source: :func:`engage_from_alert`
writes the latch file, so the next engine check sees it. The file source is
authoritative and the switch survives restarts. First observation of an
active switch appends ``KillSwitchSet``; clear is human-only and refused
while any live source is still set. ``flatten_request`` waits on the
in-flight barrier and then closes every open position with reason
``kill_flatten``; the order-building half lives here, the driving loop
with the supervisor/adapter.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import Clock
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.risk.alert_channel import AlertChannel, EmptyAlertChannel

log = logging.getLogger(__name__)

#: Exact alert command shape (T-04-10): ``KILL`` head, optional ``FLATTEN``
#: flag, mandatory reason. Bare ``KILL``, ``KILLX`` and lowercase are ignored.
KILL_LINE_RE = re.compile(r"^KILL(?:\s+FLATTEN)?\s+(?P<reason>.+)$")

#: Seat ids look like ``bot-04-sniper`` (core/bot.py SEAT_RE, R19); a clear
#: ``--by`` value must be human and must not match this shape.
SEAT_RE = re.compile(r"^bot-0[0-9]-[a-z-]+$")


def kill_switch_key(origin: str, reason: str, day_utc: str, *, flatten: bool = False) -> str:
    """Idempotency per (origin, reason, utc_day[, flatten]) for ``KillSwitchSet`` rows.

    A flatten escalation of an engaged switch is its own row, so it never collides with the
    plain set. The plain key is unchanged, so rows written before escalation keep their keys.
    """
    body = f"KillSwitchSet|{origin}|{reason}|{day_utc}"
    if flatten:
        body += "|flatten"
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


#: Latch file name inside the operational data directory (``var/desk`` in the desk).
KILLSWITCH_FILE_NAME = "KILLSWITCH"


def killswitch_file(data_dir: Path | str) -> Path:
    """The one latch path, ``<data_dir>/KILLSWITCH``; every reader and writer uses it."""
    return Path(data_dir) / KILLSWITCH_FILE_NAME


def latch_from_alert(line: str, path: Path) -> tuple[bool, str] | None:
    """Write the latch file for one alert line; ``(flatten, reason)``, or None when not a command.

    ``path`` is the latch file itself (``killswitch_file(data_dir)`` in the desk). Nothing is
    written for a line outside the exact command shape.
    """
    parsed = parse_kill_line(line)
    if parsed is None:
        return None
    flatten, reason = parsed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(kill_file_text(reason, flatten), encoding="utf-8")
    return parsed


def engage_from_alert(line: str, data_dir: Path | str) -> bool:
    """Write the latch file for a ``KILL`` line under ``data_dir``; False when not a command."""
    return latch_from_alert(line, killswitch_file(data_dir)) is not None


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


def env_engaged(raw: str | None) -> bool:
    """True when a killswitch env value engages the switch (R22).

    Anything non-empty other than ``"0"``/``"false"`` engages; ``"1"`` is
    just the conventional spelling. Shared by ``poll``, ``live_sources``,
    and the operator status views so they never disagree on what "set" means.
    """
    return raw is not None and raw.strip() not in ("", "0", "false")


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
        env: Mapping[str, str] | None = None,
        alert_channel: AlertChannel | None = None,
    ) -> None:
        self._clock = clock
        self._store = store
        self._path = Path(killswitch_path) if killswitch_path is not None else None
        start_env = dict(env) if env is not None else dict(os.environ)
        self._env_start = start_env.get("PUMPGROK_KILLSWITCH", "")
        self._alerts: AlertChannel = (
            alert_channel if alert_channel is not None else EmptyAlertChannel()
        )
        # Set while the latch file holds a reason this process wrote from an alert line.
        self._alert_latch: tuple[bool, str] | None = None
        # A KILL line accepted from the channel whose latch file could not be written yet. It
        # keeps the switch in force (fail closed) and is retried before any further poll.
        self._pending_line: str | None = None
        # Set when a KILL FLATTEN escalated an engaged switch; cleared once nothing is engaged.
        self._flatten_escalated = False

    def absorb_alerts(self) -> None:
        """Poll the alert channel once and act on each KILL line in order (RISK-004).

        With env and the latch file both clear, a valid line engages the latch file. While the
        switch is engaged, a ``KILL FLATTEN`` escalates it to flatten and is persisted to the
        latch file before anything else; a plain ``KILL`` changes nothing. A line whose latch
        cannot be written stays pending: the switch is engaged in memory (orders are refused),
        no further poll runs until the latch is saved, and the channel's offset is not committed,
        so Telegram redelivers the command once the write succeeds.
        """
        if self._pending_line is not None and not self._save_pending():
            return
        for text in self._alerts.poll():
            for raw in text.splitlines():
                parsed = parse_kill_line(raw)
                if parsed is None:
                    continue
                flatten, reason = parsed
                engaged = env_engaged(self._env_start) or (
                    self._path is not None and self._path.is_file()
                )
                if engaged:
                    if flatten and not self._flatten_escalated:
                        if not self._escalate(reason):
                            return
                    else:
                        log.info("alert KILL ignored: the switch is already engaged")
                    continue
                if self._path is None:
                    log.warning("alert KILL ignored: no latch file is configured")
                    continue
                self._pending_line = raw
                if not self._save_pending():
                    return
        self._alerts.commit()

    def _save_pending(self) -> bool:
        """Write the pending KILL line to the latch; True once saved, False while it cannot be."""
        raw = self._pending_line
        if raw is None or self._path is None:
            return False
        try:
            self._alert_latch = latch_from_alert(raw, self._path)
        except OSError as exc:
            log.warning("alert KILL not persisted, kill stays in force: %s", type(exc).__name__)
            return False
        self._pending_line = None
        log.warning("alert KILL engaged the kill latch file")
        return True

    def _escalate(self, reason: str) -> bool:
        """Escalate an engaged switch to flatten, persisting it to the latch file first.

        The latch file is the durable record: a restart reads ``FLATTEN`` from it even when env
        is the source of record. Returns False when the write fails, so the caller does not
        commit the offset and the KILL line is delivered again on the next poll.
        """
        if self._path is not None:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_name(self._path.name + ".tmp")
                tmp.write_text(kill_file_text(reason, True), encoding="utf-8")
                os.replace(tmp, self._path)
            except OSError as exc:
                log.warning("alert KILL FLATTEN not persisted: %s", type(exc).__name__)
                return False
            self._alert_latch = (True, reason)
        self._flatten_escalated = True
        log.warning("alert KILL FLATTEN escalated the kill switch to flatten")
        return True

    def _file_requests_flatten(self) -> bool:
        """True when the latch file's first line is a ``FLATTEN`` request."""
        if self._path is None or not self._path.is_file():
            return False
        first = self._path.read_text(encoding="utf-8").splitlines()
        return bool(first) and _file_state(first[0].strip()).flatten_requested

    def poll(self) -> KillState:
        """Current switch state: env (start) beats the latch file beats the ledger.

        An alert ``KILL FLATTEN`` that escalated the engaged switch keeps ``flatten_requested``
        set for whichever source is active, until the switch is no longer engaged.
        """
        state = self._engaged_state()
        if not state.active:
            self._flatten_escalated = False
            return state
        if self._flatten_escalated and not state.flatten_requested:
            return KillState(True, state.source, state.reason, True)
        return state

    def _engaged_state(self) -> KillState:
        if env_engaged(self._env_start):
            # Env is the source of record for the reason; a FLATTEN latch in the file still
            # requests the flatten, so a consumed KILL FLATTEN survives a restart.
            return KillState(True, "env", self._env_start.strip(), self._file_requests_flatten())
        if self._path is not None and self._path.is_file():
            first = self._path.read_text(encoding="utf-8").splitlines()
            line = first[0].strip() if first else ""
            if self._alert_latch is not None:
                flatten, reason = self._alert_latch
                if line == kill_file_text(reason, flatten):
                    return KillState(True, "alert_command", reason, flatten)
            return _file_state(line)
        if self._pending_line is not None:
            parsed = parse_kill_line(self._pending_line)
            if parsed is not None:
                flatten, reason = parsed
                return KillState(True, "alert_command", reason, flatten)
        self._alert_latch = None
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
        """Append ``KillSwitchSet`` on first observation, and again when a flatten escalates it."""
        if self._store is None:
            return None
        state = self.poll()
        if not state.active:
            return None
        latest = self._latest_set()
        if latest is not None:
            latest_flatten = bool(latest["payload"].get("flatten_requested", False))
            if latest_flatten or not state.flatten_requested:
                return None
        row: dict[str, Any] = {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": kill_switch_key(
                state.source, state.reason, ts_utc[:10], flatten=state.flatten_requested
            ),
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
        """Live sources currently set: env-now and the latch file (ledger excluded)."""
        live: list[str] = []
        env_now = os.environ.get("PUMPGROK_KILLSWITCH", "")
        if env_engaged(env_now) or env_engaged(self._env_start):
            live.append("env")
        if self._path is not None and self._path.is_file():
            live.append("file")
        if self._pending_line is not None:
            live.append("alert_command")
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
