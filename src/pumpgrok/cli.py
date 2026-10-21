"""Command line: parse, check, main (FOUND-013, R30, R37; port of grokbot `pipeline.py` shape).

Verbs: `run` (paper, `--once --replay <dir>` runs one skip-only cycle) and `doctor`.

Exit codes: 0 ok; 1 config or usage; 2 ledger inconsistent; 3 live refused; 4 corrupt
fixture; 5 not implemented. argparse's own exit 2 is overridden so that 2 means only a
ledger inconsistency. Stdout carries the doctor report; diagnostics go to stderr.

Run order: refuse key-bearing CLI values -> parse -> settings (mode R30) -> logging ->
live gate (live exits 3 before any other work) -> verb. For the skip cycle: manifest
verification (exit 4, before any ledger file exists) -> recreate ledger -> read fixture
events -> append one `JournalNote` (source=replay) -> verify chain -> exit 0.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn, TextIO

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

log = logging.getLogger("pumpgrok.cli")


class UsageError(Exception):
    """A malformed command line. Exit 1, never argparse's 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


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
    run = verbs.add_parser("run", parents=[mode_option], help="run the desk")
    run.add_argument("--once", action="store_true", help="run a single cycle and exit")
    run.add_argument("--replay", metavar="DIR", default=None, help="recorded fixture directory")
    verbs.add_parser("doctor", parents=[mode_option], help="report subsystem health")
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
    if not (args.once and args.replay):
        _say(
            sys.stderr,
            "not implemented: this release runs only `run --mode paper --once --replay <dir>`",
        )
        return EXIT_NOT_IMPLEMENTED
    return _skip_cycle(Path(args.replay), settings.replay.seed)


def _skip_cycle(source: Path, seed: int) -> int:
    dataset_name = source.resolve().name
    if not DATASET_NAME_RE.fullmatch(dataset_name):
        raise ConfigError([f"replay directory name is not a plain name: {dataset_name!r}"])
    dataset = load_dataset(source)  # verifies every listed digest before any ledger file exists

    start = event_epoch(dataset.events[0]) if dataset.events else 0.0
    clock = FixtureClock(start=start)
    ids = IdFactory(clock, make_rng(seed))
    cycle = CorrelationId.new(ids)
    ledger_path = recreate_ledger_db(LEDGER_ROOT / dataset_name / "ledger.sqlite")

    with bind_correlation(cycle), bind_seat(CYCLE_SEAT):
        for event in dataset.events:
            clock.advance_to(event_epoch(event))
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
                    "note_kind": "note",
                    "text": (
                        f"skip-only replay cycle: read {len(dataset.events)} fixture events "
                        f"from {dataset_name}; no engine ran"
                    ),
                    "refs": [],
                },
            )
            store.verify()
        finally:
            store.close()
        log.info(
            "skip-only replay cycle complete",
            extra={
                "event": "cycle_end",
                "events_read": len(dataset.events),
                "ledger_seq": row["seq"],
            },
        )
    return EXIT_OK


def _dispatch(argv: Sequence[str]) -> int:
    refuse_cli_secrets(argv)
    args = build_parser().parse_args(list(argv))
    settings = load_settings(**_settings_kwargs(args.mode))
    setup_logging(mode=settings.effective_mode, profile=current_profile())
    if args.verb == "doctor":
        _say(sys.stdout, *doctor_report(settings))
        return EXIT_OK
    return _run(args, settings)


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
