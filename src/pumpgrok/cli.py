"""Command line: parse, check, main (FOUND-013, R30, R37; port of grokbot `pipeline.py` shape).

Verbs: `run` (paper, `--once --replay <dir>` runs one engine-decision cycle) and `doctor`;
every other verb (`paper buy|sell`, `scout`, `risk`, `chief`, `rug`, `journal`,
`ticket`, `state`, `killswitch`, `live confirm`, `replay`, `audit`, `verify`,
`report`) parses its flags and returns not-yet-implemented (exit 5) until its
subsystem lands. `paper` and `state` require `--seat` and refuse `sniper`/`exit`.

Exit codes: 0 ok; 1 config or usage; 2 ledger inconsistent; 3 live refused; 4 corrupt
fixture; 5 not implemented. argparse's own exit 2 is overridden so that 2 means only a
ledger inconsistency. Stdout carries the doctor report and the engine decision;
diagnostics go to stderr.

Run order: refuse key-bearing CLI values -> parse -> settings (mode R30) -> logging ->
live gate (live exits 3 before any other work) -> verb. For the replay cycle: manifest
verification (exit 4, before any ledger file exists) -> recreate ledger -> map fixture
ticks to evidence-less engine candidates -> run the pure filter stage -> print one
`engine decision=` line -> append one `JournalNote` (source=replay) -> verify chain.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn, TextIO

from pumpgrok.config.settings import (
    ConfigError,
    Settings,
    current_profile,
    load_settings,
    refuse_cli_secrets,
)
from pumpgrok.core.idempotency import derive_idempotency_key
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.doctor import doctor_report
from pumpgrok.engine.pipeline import decide_replay, format_decision
from pumpgrok.execution.live.live_gate import LiveGate, refusal_lines
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore, recreate_ledger_db
from pumpgrok.logging.json import bind_seat, setup_logging
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import CorruptFixture, event_epoch, load_dataset
from pumpgrok.replay.rng import make_rng

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_LEDGER = 2
EXIT_LIVE = 3
EXIT_FIXTURE = 4
EXIT_NOT_IMPLEMENTED = 5

LEDGER_ROOT = Path("var") / "replay"
CYCLE_SEAT = "desk"
DATASET_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")

FORBIDDEN_OWNERS = frozenset({"sniper", "exit"})
TICKET_RE = re.compile(r"^SOL-\d{8}-\d{3}$")
APPROVAL_RE = re.compile(r"^apr-[0-9A-HJKMNP-TV-Z]{26}$")
_BASE58 = frozenset("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
LAMPORTS_PER_SOL = 1_000_000_000

log = logging.getLogger("pumpgrok.cli")


class UsageError(Exception):
    """A malformed command line. Exit 1, never argparse's 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def _ticket(value: str) -> str:
    if not TICKET_RE.fullmatch(value):
        raise UsageError(f"bad --ticket {value!r}: want SOL-YYYYMMDD-NNN")
    return value


def _mint(value: str) -> str:
    if not 32 <= len(value) <= 44 or any(char not in _BASE58 for char in value):
        raise UsageError("bad --mint: want 32-44 base58 characters")
    return value


def _size_sol(value: str) -> float:
    try:
        size = float(value)
    except ValueError:
        raise UsageError(f"bad --size-sol {value!r}: want a positive number") from None
    if not size > 0:
        raise UsageError(f"bad --size-sol {value!r}: want a positive number")
    return size


def _slippage_bps(value: str) -> int:
    try:
        bps = int(value)
    except ValueError:
        raise UsageError(f"bad --slippage-bps {value!r}: want 0-10000") from None
    if not 0 <= bps <= 10000:
        raise UsageError(f"bad --slippage-bps {value!r}: want 0-10000")
    return bps


def _approval_id(value: str) -> str:
    if not APPROVAL_RE.fullmatch(value):
        raise UsageError("bad --approval-id: want apr-<26 char ULID>")
    return value


def size_sol_to_lamports(size_sol: float) -> int:
    """Convert a SOL size to lamports once, here, so every path shares one rounding."""
    return int(size_sol * LAMPORTS_PER_SOL)


def _not_implemented(verb: str) -> int:
    """Absent-subsystem contract: fixed JSON on stdout, one stderr line, exit 5."""
    _say(sys.stdout, json.dumps({"ok": False, "status": "not-yet-implemented", "verb": verb}))
    _say(sys.stderr, f"not implemented: `{verb}` is not yet implemented in this release")
    return EXIT_NOT_IMPLEMENTED


def _refuse_forbidden_seat(seat: str, verb: str) -> int | None:
    """Refuse forbidden_owners callers (jobs.yaml) with exit 1. None means allowed."""
    if seat in FORBIDDEN_OWNERS:
        _say(sys.stderr, f"refused: seat {seat!r} is a forbidden owner for `{verb}`")
        return EXIT_CONFIG
    return None


def _add_seat(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--seat",
        required=True,
        help="calling seat; sniper and exit are refused (forbidden_owners)",
    )


def _add_paper_trade_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ticket", required=True, type=_ticket, help="ticket id SOL-YYYYMMDD-NNN")
    parser.add_argument("--mint", required=True, type=_mint, help="base58 mint address")
    parser.add_argument(
        "--size-sol",
        required=True,
        type=_size_sol,
        dest="size_sol",
        help="size in SOL, converted once to lamports",
    )
    parser.add_argument(
        "--slippage-bps",
        required=True,
        type=_slippage_bps,
        dest="slippage_bps",
        help="max slippage 0-10000 bps",
    )
    parser.add_argument(
        "--approval-id",
        required=True,
        type=_approval_id,
        dest="approval_id",
        help="consumed ApprovalRecord id (apr-<ULID>)",
    )
    _add_seat(parser)


def _add_run(verbs: Any, mode_option: argparse.ArgumentParser) -> None:
    run = verbs.add_parser("run", parents=[mode_option], help="run the desk")
    run.add_argument("--once", action="store_true", help="run a single cycle and exit")
    run.add_argument("--replay", metavar="DIR", default=None, help="recorded fixture directory")
    run.add_argument(
        "--record", metavar="DATASET", default=None, help="record a dataset (not yet implemented)"
    )
    run.add_argument(
        "--duration", metavar="SECONDS", default=None, type=int, help="record duration (R40)"
    )


def _add_simple(verbs: Any, mode_option: argparse.ArgumentParser) -> None:
    verbs.add_parser("doctor", parents=[mode_option], help="report subsystem health")
    verbs.add_parser("audit", parents=[mode_option], help="audit the ledger (not yet implemented)")
    verify = verbs.add_parser("verify", parents=[mode_option], help="verify a fixture or ledger")
    verify.add_argument("--fixture", required=True, metavar="DATASET", help="dataset to verify")
    report = verbs.add_parser("report", parents=[mode_option], help="emit a desk report")
    report_period = report.add_mutually_exclusive_group(required=True)
    report_period.add_argument("--daily", action="store_true", help="daily report")
    report_period.add_argument("--weekly", action="store_true", help="weekly report")


def _add_scout(verbs: Any, mode_option: argparse.ArgumentParser) -> None:
    scout = verbs.add_parser("scout", parents=[mode_option], help="discovery verbs")
    scout_cmd = scout.add_subparsers(dest="cmd", required=True, metavar="SCOUT")
    scout_discover = scout_cmd.add_parser("discover", help="discover new launches")
    scout_discover.add_argument("--max-leads", type=int, default=5, help="max leads this run")
    scout_pipeline = scout_cmd.add_parser("pipeline", help="ingest pipeline candidates")
    scout_pipeline.add_argument("--candidates", action="store_true", help="read candidates")
    scout_pipeline.add_argument("--limit", type=int, default=5, help="max candidates this run")


def _add_risk_chief_rug(verbs: Any, mode_option: argparse.ArgumentParser) -> None:
    risk = verbs.add_parser("risk", parents=[mode_option], help="risk verbs")
    risk_cmd = risk.add_subparsers(dest="cmd", required=True, metavar="RISK")
    risk_audit = risk_cmd.add_parser("audit", help="audit open leads")
    risk_audit.add_argument("--pending", action="store_true", help="audit pending leads only")
    chief = verbs.add_parser("chief", parents=[mode_option], help="chief verbs")
    chief_cmd = chief.add_subparsers(dest="cmd", required=True, metavar="CHIEF")
    chief_cmd.add_parser("pickup", help="route CLEAR/CONDITIONAL briefs to tickets")
    rug = verbs.add_parser("rug", parents=[mode_option], help="rug-watch verbs")
    rug_cmd = rug.add_subparsers(dest="cmd", required=True, metavar="RUG")
    rug_cmd.add_parser("watch", help="watch open paper positions")


def _add_journal_ticket(verbs: Any, mode_option: argparse.ArgumentParser) -> None:
    journal = verbs.add_parser("journal", parents=[mode_option], help="journal verbs")
    journal_cmd = journal.add_subparsers(dest="cmd", required=True, metavar="JOURNAL")
    journal_rollup = journal_cmd.add_parser("rollup", help="daily journal rollup")
    journal_rollup.add_argument("--daily", action="store_true", help="roll up today")
    journal_rollup.add_argument("--weekly", action="store_true", help="roll up this week")
    ticket = verbs.add_parser("ticket", parents=[mode_option], help="ticket verbs")
    ticket_cmd = ticket.add_subparsers(dest="cmd", required=True, metavar="TICKET")
    ticket_cmd.add_parser("next", help="allocate the next ticket id")
    ticket_create = ticket_cmd.add_parser("create", help="draft a ticket")
    ticket_create.add_argument("--mint", default=None, help="mint address")
    ticket_create.add_argument("--ticket", default=None, help="ticket id SOL-YYYYMMDD-NNN")
    ticket_create.add_argument("--status", default=None, help="initial ticket status")
    ticket_cmd.add_parser("list", help="list tickets")


def _add_state(verbs: Any, mode_option: argparse.ArgumentParser) -> None:
    state = verbs.add_parser("state", parents=[mode_option], help="desk state verbs")
    state_cmd = state.add_subparsers(dest="cmd", required=True, metavar="STATE")
    state_status = state_cmd.add_parser("status", help="report desk status")
    _add_seat(state_status)
    state_halt = state_cmd.add_parser("halt", help="set or inspect the halt flag")
    state_halt.add_argument("--clear", action="store_true", help="clear the halt (human only)")
    state_halt.add_argument("--by", default=None, help="who clears the halt")
    state_halt.add_argument("--reason", default=None, help="why the halt changes")
    _add_seat(state_halt)
    state_autonomy = state_cmd.add_parser("autonomy", help="set the autonomy mode (R40)")
    state_autonomy.add_argument(
        "policy", choices=("manual-ticket", "autonomous-paper"), help="autonomy policy"
    )
    _add_seat(state_autonomy)


def _add_tail(verbs: Any, mode_option: argparse.ArgumentParser) -> None:
    killswitch = verbs.add_parser("killswitch", parents=[mode_option], help="killswitch verbs")
    killswitch_cmd = killswitch.add_subparsers(dest="cmd", required=True, metavar="KILLSWITCH")
    killswitch_cmd.add_parser("set", help="engage the killswitch")
    killswitch_cmd.add_parser("clear", help="release the killswitch")
    killswitch_cmd.add_parser("status", help="report killswitch state")
    paper = verbs.add_parser("paper", parents=[mode_option], help="paper trade verbs")
    paper_cmd = paper.add_subparsers(dest="cmd", required=True, metavar="PAPER")
    paper_buy = paper_cmd.add_parser("buy", help="paper buy (not yet implemented)")
    _add_paper_trade_flags(paper_buy)
    paper_sell = paper_cmd.add_parser("sell", help="paper sell (not yet implemented)")
    _add_paper_trade_flags(paper_sell)
    live = verbs.add_parser("live", parents=[mode_option], help="live verbs")
    live_cmd = live.add_subparsers(dest="cmd", required=True, metavar="LIVE")
    live_cmd.add_parser("confirm", help="confirm a live gate (not yet implemented)")
    replay = verbs.add_parser("replay", parents=[mode_option], help="replay dataset verbs")
    replay_cmd = replay.add_subparsers(dest="cmd", required=True, metavar="REPLAY")
    replay_cmd.add_parser("trim", help="trim a replay dataset")
    replay_cmd.add_parser("rebuild-ticks", help="rebuild ticks from a recording")


def build_parser() -> argparse.ArgumentParser:
    mode_option = _Parser(add_help=False)
    mode_option.add_argument(
        "--mode",
        choices=("paper", "live"),
        default=None,
        help="execution mode; overrides PUMPGROK_MODE and the overlay",
    )
    parser = _Parser(prog="pumpgrok", description="PumpGrok paper-first trading desk.")
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="VERB")
    _add_run(verbs, mode_option)
    _add_simple(verbs, mode_option)
    _add_scout(verbs, mode_option)
    _add_risk_chief_rug(verbs, mode_option)
    _add_journal_ticket(verbs, mode_option)
    _add_state(verbs, mode_option)
    _add_tail(verbs, mode_option)
    return parser


def _say(stream: TextIO, *lines: str) -> None:
    for line in lines:
        stream.write(line + "\n")


def _settings_kwargs(mode: str | None) -> dict[str, str]:
    # Passing mode=None would shadow PUMPGROK_MODE with a null init value; omit it instead.
    return {} if mode is None else {"mode": mode}


def _run(args: argparse.Namespace, settings: Settings) -> int:
    gate = LiveGate(mode=settings.effective_mode, environ=os.environ, root=Path.cwd())
    if settings.effective_mode == "live":
        preconditions = gate.evaluate()
        if any(not item.met for item in preconditions):
            _say(sys.stderr, *refusal_lines(preconditions))
            return EXIT_LIVE
    if args.record is not None or args.duration is not None:
        return _not_implemented("run --record")
    if not (args.once and args.replay):
        _say(
            sys.stderr,
            "not implemented: this release runs only `run --mode paper --once --replay <dir>`",
        )
        return EXIT_NOT_IMPLEMENTED
    return _skip_cycle(Path(args.replay), settings)


def _skip_cycle(source: Path, settings: Settings) -> int:
    dataset_name = source.resolve().name
    if not DATASET_NAME_RE.fullmatch(dataset_name):
        raise ConfigError([f"replay directory name is not a plain name: {dataset_name!r}"])
    dataset = load_dataset(source)  # verifies every listed digest before any ledger file exists

    start = event_epoch(dataset.events[0]) if dataset.events else 0.0
    clock = FixtureClock(start=start)
    ids = IdFactory(clock, make_rng(settings.replay.seed))
    cycle = CorrelationId.new(ids)
    ledger_path = recreate_ledger_db(LEDGER_ROOT / dataset_name / "ledger.sqlite")

    with bind_correlation(cycle), bind_seat(CYCLE_SEAT):
        for event in dataset.events:
            clock.advance_to(event_epoch(event))
        # Pure engine stage only: fixture ticks become evidence-less
        # candidates, so the fail-closed filter decides. No monitor stream,
        # no analyzer fetch, no model lookup of any kind.
        decision = decide_replay(dataset.events, settings.filter, clock.now())
        _say(sys.stdout, format_decision(decision))
        store = LedgerStore(ledger_path)
        try:
            row = store.append(
                ts_utc=clock.utc_iso(),
                source="replay",
                correlation_id=str(cycle),
                idempotency_key=derive_idempotency_key(
                    "skip_cycle",
                    CYCLE_SEAT,
                    {"dataset": dataset_name, "events": len(dataset.events)},
                    scope=str(cycle),
                ),
                type="JournalNote",
                payload={
                    "source": "replay",
                    "seat": CYCLE_SEAT,
                    "note_kind": "verdict",
                    "text": (
                        f"replay engine cycle: {format_decision(decision)}; "
                        "model resolution skipped (replay); "
                        f"read {len(dataset.events)} fixture events from {dataset_name}; "
                        "metadata and age gates satisfied by construction, "
                        "buyer evidence absent by construction"
                    ),
                    "refs": [],
                },
            )
            store.verify()
        finally:
            store.close()
        log.info(
            "replay engine cycle complete",
            extra={
                "event": "cycle_end",
                "events_read": len(dataset.events),
                "engine_decision": decision.decision,
                "engine_reason": decision.reason,
                "ledger_seq": row["seq"],
            },
        )
    return EXIT_OK


def _paper(args: argparse.Namespace) -> int:
    verb = f"paper {args.cmd}"
    refused = _refuse_forbidden_seat(args.seat, verb)
    if refused is not None:
        return refused
    lamports = size_sol_to_lamports(args.size_sol)
    log.info(
        "absent paper verb",
        extra={"event": "absent_verb", "verb": verb, "size_lamports": lamports},
    )
    return _not_implemented(verb)


def _state(args: argparse.Namespace) -> int:
    verb = f"state {args.cmd}"
    refused = _refuse_forbidden_seat(args.seat, verb)
    if refused is not None:
        return refused
    return _not_implemented(verb)


def _dispatch(argv: Sequence[str]) -> int:
    refuse_cli_secrets(argv)
    args = build_parser().parse_args(list(argv))
    settings = load_settings(**_settings_kwargs(args.mode))
    setup_logging(mode=settings.effective_mode, profile=current_profile())
    if args.verb == "doctor":
        _say(sys.stdout, *doctor_report(settings))
        return EXIT_OK
    if args.verb == "run":
        return _run(args, settings)
    if args.verb == "paper":
        return _paper(args)
    if args.verb == "state":
        return _state(args)
    if args.verb in (
        "scout",
        "risk",
        "chief",
        "rug",
        "journal",
        "ticket",
        "killswitch",
        "live",
        "replay",
    ):
        return _not_implemented(f"{args.verb} {args.cmd}")
    return _not_implemented(args.verb)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else list(argv)
    try:
        return _dispatch(arguments)
    except UsageError as exc:
        _say(sys.stderr, f"usage error: {exc}")
        return EXIT_CONFIG
    except ConfigError as exc:
        _say(sys.stderr, "config error:", *(f"  - {problem}" for problem in exc.problems))
        return EXIT_CONFIG
    except CorruptFixture as exc:
        details = [f"  - {key}: {value}" for key, value in exc.fields.items()]
        _say(sys.stderr, f"corrupt fixture: {exc.message}", *details)
        return EXIT_FIXTURE
    except LedgerInconsistent as exc:
        _say(sys.stderr, f"ledger inconsistent: {exc.message}")
        return EXIT_LEDGER


if __name__ == "__main__":
    raise SystemExit(main())
