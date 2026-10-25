"""Desk state verbs: run, paper, state, killswitch, ticket."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from pumpgrok.cli.codes import (
    DATASET_NAME_RE,
    EXIT_CONFIG,
    EXIT_LIVE,
    EXIT_NOT_IMPLEMENTED,
    EXIT_OK,
    _TRADE_UNAVAILABLE,
)
from pumpgrok.cli.errors import UsageError, _not_implemented, _refuse_forbidden_seat, _say, _tool_error
from pumpgrok.cli.validators import _human_by, _mint_approval_id, _utc_now, size_sol_to_lamports
from pumpgrok.cli.wiring import (
    _call_use,
    _run_wired,
    _seat_manifest_id,
    _unflattened_lines,
)
from pumpgrok.config.settings import ConfigError, Settings, health_port
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.tool import Tool
from pumpgrok.execution.live.live_gate import LiveGate, refusal_lines
from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.ledger.tickets import allocate_ticket
from pumpgrok.replay.clock import WallClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.runner import format_trade
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import ClearRefused, KillSwitch, killswitch_file
from pumpgrok.supervisor.scheduler import run_once_replay, serve_replay
from pumpgrok.core.ids import IdFactory

log = logging.getLogger("pumpgrok.cli")


def _run(args: argparse.Namespace, settings: Settings) -> int:
    gate = LiveGate(
        mode=settings.effective_mode,
        environ=os.environ,
        root=Path.cwd(),
        live_enabled=settings.live.enabled,
    )
    if settings.effective_mode == "live":
        preconditions = gate.evaluate(now=_utc_now().strftime("%Y-%m-%d"))
        if any(not item.met for item in preconditions):
            _say(sys.stderr, *refusal_lines(preconditions))
            return EXIT_LIVE
    if args.record is not None or args.duration is not None:
        return _not_implemented("run --record")
    if args.serve:
        if args.once or not args.replay:
            _say(
                sys.stderr,
                "not implemented: `run --serve` needs `--replay <dir>` without `--once`",
            )
            return EXIT_NOT_IMPLEMENTED
        return _serve_replay_loop(Path(args.replay), settings)
    if not (args.once and args.replay):
        _say(
            sys.stderr,
            "not implemented: this release runs only `run --mode paper --once --replay <dir>`",
        )
        return EXIT_NOT_IMPLEMENTED
    return _skip_cycle(Path(args.replay), settings)


def _serve_replay_loop(source: Path, settings: Settings) -> int:
    """D1 serve path: replay a recorded dataset in a loop, serving /healthz and /metrics."""
    dataset_name = source.resolve().name
    if not DATASET_NAME_RE.fullmatch(dataset_name):
        raise ConfigError([f"replay directory name is not a plain name: {dataset_name!r}"])
    port = health_port(settings)
    if port <= 0:
        _say(sys.stderr, "run --serve needs a nonzero health port: set PUMPGROK_HEALTH__PORT")
        return EXIT_CONFIG
    host = settings.health.host
    log.info("serve starting (dataset=%s host=%s port=%d)", dataset_name, host, port)
    return asyncio.run(
        serve_replay(
            source,
            settings.filter,
            seed=settings.replay.seed,
            host=host,
            port=port,
            exits=settings.exits,
            budget=settings.risk,
            limits=settings.limits,
        )
    )


def _skip_cycle(source: Path, settings: Settings) -> int:
    dataset_name = source.resolve().name
    if not DATASET_NAME_RE.fullmatch(dataset_name):
        raise ConfigError([f"replay directory name is not a plain name: {dataset_name!r}"])

    result = run_once_replay(
        source,
        settings.filter,
        seed=settings.replay.seed,
        exits=settings.exits,
        budget=settings.risk,
        limits=settings.limits,
    )
    _say(sys.stdout, f"engine decision={result.decision} reason={result.reason}")
    _say(sys.stdout, *(format_trade(trade) for trade in result.trades))
    filled = sum(1 for trade in result.trades if trade.outcome == "filled")
    _say(sys.stdout, f"trades filled={filled} not_filled={len(result.trades) - filled}")
    return EXIT_OK


def _paper(args: argparse.Namespace, settings: Settings) -> int:
    """Paper trade: seat authorization first, then refuse with code ``unavailable``.

    The forbidden-owner guard and the registry grant check (``find``) run before
    the refusal, so forbidden and operator seats keep their existing codes. Only a
    seat allowed to trade reaches the refusal. No tool is invoked and nothing is
    written: no curve price source is bound on the CLI and the RPC curve layout is
    ASSUMED.
    """
    verb = f"paper {args.cmd}"
    refused = _refuse_forbidden_seat(args.seat, verb)
    if refused is not None:
        return refused
    if size_sol_to_lamports(args.size_sol) > settings.risk.paper_equity_lamports:
        _say(sys.stderr, "usage error: --size-sol exceeds paper equity")
        return EXIT_CONFIG

    async def use(_tools: list[Tool]) -> int:
        return _tool_error(verb, "unavailable", _TRADE_UNAVAILABLE)

    return _run_wired(verb, args.seat, settings, ("exec.simulate", "exec.place"), use)


def _set_autonomy(policy: str, by: str) -> int:
    """Append the ``ConfigChanged`` + ``JournalNote`` pair for a level change."""
    store = LedgerStore(str(PAPER_LEDGER_PATH))
    try:
        previous = read_autonomy(store)
        ts_utc = format_ts_utc(WallClock().now())
        store.append_batch(
            autonomy_rows(
                policy,
                by,
                previous=previous,
                ts_utc=ts_utc,
                source="paper",
                correlation_id="desk",
            )
        )
    finally:
        store.close()
    _say(
        sys.stdout,
        json.dumps({"ok": True, "autonomy": policy, "previous": previous, "by": by}),
    )
    return EXIT_OK


def _halt_clear(by: str, reason: str, settings: Settings) -> int:
    """Append ``HaltCleared`` plus the consumed ``halt_clear`` approval (R5)."""
    verb = "state halt --clear"
    store = LedgerStore(str(PAPER_LEDGER_PATH))
    try:
        clock = WallClock()
        engine = RiskEngine(
            store=store,
            budget=settings.risk,
            ids=IdFactory(clock, make_rng(settings.replay.seed)),
            clock=clock,
            limits=settings.limits,
        )
        approval = ApprovalRecord(
            id=_mint_approval_id(),
            kind="halt_clear",
            approved_by=by,
            raw_message=reason,
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        try:
            engine.request_halt_clear(approval, reason, source="paper", correlation_id="desk")
        except (ValueError, sqlite3.IntegrityError, LedgerInconsistent) as exc:
            return _tool_error(verb, "halt_clear_refused", str(exc))
    finally:
        store.close()
    _say(sys.stdout, json.dumps({"ok": True, "halt": "cleared", "by": by, "reason": reason}))
    return EXIT_OK


def _resume(target: str, by: str) -> int:
    """Record a seat resume from observe-only (paper-engine.md 6.4, R22)."""
    store = LedgerStore(str(PAPER_LEDGER_PATH))
    try:
        ts_utc = format_ts_utc(WallClock().now())
        store.append(
            ts_utc=ts_utc,
            source="paper",
            correlation_id="desk",
            idempotency_key=f"resume|{target}|{ts_utc}",
            type="JournalNote",
            payload={
                "source": "paper",
                "seat": target,
                "note_kind": "note",
                "text": f"resume {target} by {by}",
                "refs": [],
            },
        )
    finally:
        store.close()
    _say(sys.stdout, json.dumps({"ok": True, "seat": target, "by": by}))
    return EXIT_OK


def _state(args: argparse.Namespace, settings: Settings) -> int:
    verb = f"state {args.cmd}"
    if args.cmd == "resume":
        # Human-only (R22): the supervisor folds the note in 04-08. The
        # target seat resolves through the roster; sniper/exit targets are
        # allowed here because resuming them is the point.
        by = _human_by(args.by, verb)
        try:
            target = _seat_manifest_id(args.seat)
        except UsageError as exc:
            _say(sys.stderr, f"usage error: {exc}")
            return EXIT_CONFIG
        return _resume(target, by)
    refused = _refuse_forbidden_seat(args.seat, verb)
    if refused is not None:
        return refused
    if args.cmd == "halt" and args.clear:
        # Human-only (R22): the ledger HaltCleared + ApprovalRecord.
        by = _human_by(args.by, verb)
        return _halt_clear(by, args.reason or "", settings)
    if args.cmd == "autonomy":
        # Human-only (R17, R40): ConfigChanged plus a journal note, one batch.
        by = _human_by(args.by, verb)

        async def _autonomy_use(_tools: list[Tool]) -> int:
            return _set_autonomy(args.policy, by)

        return _run_wired(verb, args.seat, settings, ("risk.halt_status",), _autonomy_use)
    return _run_wired(verb, args.seat, settings, ("risk.halt_status",), _call_use(verb, 0, {}))


def _killswitch_clear(by: str, reason: str) -> int:
    """Append ``KillSwitchCleared`` plus the ``killswitch_clear`` approval."""
    verb = "killswitch clear"
    store = LedgerStore(str(PAPER_LEDGER_PATH))
    try:
        clock = WallClock()
        switch = KillSwitch(
            clock,
            store=store,
            killswitch_path=killswitch_file(Path("var") / "desk"),
        )
        approval = ApprovalRecord(
            id=_mint_approval_id(),
            kind="killswitch_clear",
            approved_by=by,
            raw_message=reason,
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        try:
            switch.request_clear(
                approval, reason, ts_utc=format_ts_utc(clock.now()), source="paper"
            )
        except (ClearRefused, ValueError, sqlite3.IntegrityError, LedgerInconsistent) as exc:
            return _tool_error(verb, "killswitch_clear_refused", str(exc))
    finally:
        store.close()
    _say(sys.stdout, json.dumps({"ok": True, "killswitch": "cleared", "by": by, "reason": reason}))
    return EXIT_OK


def _killswitch(args: argparse.Namespace, settings: Settings) -> int:
    verb = f"killswitch {args.cmd}"
    if args.cmd == "clear":
        # Human-only (R22): the ledger KillSwitchCleared + ApprovalRecord.
        # No seat: the human identity in --by is the authorization.
        by = _human_by(args.by, verb)
        return _killswitch_clear(by, args.reason)
    if args.cmd == "set":
        return _run_wired(
            verb,
            "risk",
            settings,
            ("risk.kill_switch",),
            _call_use(verb, 0, {"action": "set", "reason": args.reason}),
        )
    if args.cmd == "flatten":
        return _run_wired(
            verb,
            "risk",
            settings,
            ("risk.kill_switch",),
            _call_use(
                verb,
                0,
                {"action": "flatten_request", "reason": args.reason},
                check=_unflattened_lines,
            ),
        )
    return _run_wired(verb, "risk", settings, ("risk.halt_status",), _call_use(verb, 0, {}))


def _ticket_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Allocate and list paper tickets over the canonical ledger (R29, R33)."""
    del settings
    verb = f"ticket {args.cmd}"
    store = LedgerStore(str(PAPER_LEDGER_PATH))
    try:
        ts_utc = format_ts_utc(WallClock().now())
        if args.cmd == "next":
            ticket_id = allocate_ticket(
                store,
                ts_utc=ts_utc,
                source="paper",
                correlation_id="desk",
                seat="desk",
                title="lead",
            )
            _say(sys.stdout, json.dumps({"ok": True, "ticket_id": ticket_id}))
            return EXIT_OK
        if args.cmd == "create":
            if args.ticket is not None:
                ticket_id = args.ticket
                taken = {
                    str(note.get("payload", {}).get("refs", [None])[0])
                    for note in store.read(types=["JournalNote"], limit=None)
                    if isinstance(note.get("payload"), dict)
                    and note["payload"].get("note_kind") == "ticket"
                }
                if ticket_id in taken:
                    return _tool_error(verb, "ticket_taken", f"ticket already exists: {ticket_id}")
                title = " ".join(part for part in (args.mint, args.status) if part) or "lead"
                store.append(
                    ts_utc=ts_utc,
                    source="paper",
                    correlation_id="desk",
                    idempotency_key=f"ticket:{ticket_id}",
                    type="JournalNote",
                    payload={
                        "source": "paper",
                        "seat": "desk",
                        "note_kind": "ticket",
                        "text": f"{ticket_id} {title}",
                        "refs": [ticket_id],
                    },
                )
            else:
                title = " ".join(part for part in (args.mint, args.status) if part) or "lead"
                ticket_id = allocate_ticket(
                    store,
                    ts_utc=ts_utc,
                    source="paper",
                    correlation_id="desk",
                    seat="desk",
                    title=title,
                )
            _say(sys.stdout, json.dumps({"ok": True, "ticket_id": ticket_id}))
            return EXIT_OK
        if args.cmd == "list":
            tickets = [
                str(note["payload"]["refs"][0])
                for note in store.read(types=["JournalNote"], limit=None)
                if isinstance(note.get("payload"), dict)
                and note["payload"].get("note_kind") == "ticket"
                and note["payload"].get("refs")
            ]
            _say(sys.stdout, json.dumps({"ok": True, "tickets": tickets}))
            return EXIT_OK
    finally:
        store.close()
    return _not_implemented(verb)
