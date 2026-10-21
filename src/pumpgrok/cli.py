"""Command line: parse, check, main (FOUND-013, R30, R37; port of grokbot `pipeline.py` shape).

Verbs: `run` (paper, `--once --replay <dir>` runs one engine-decision cycle) and `doctor`
print text (exemptions: the replay checkpoint prints the engine-decision line and the
doctor report is human-readable). Every other section-12 verb is a thin JSON wrapper
over catalog tools through `build_operator_registry` + `registry.find` (TOOL-011, I1):
`paper buy|sell` (fail closed on unknown `--approval-id`, exit 1, R63), `state`,
`killswitch`, `scout`, `risk`, `chief`, `rug`, `journal`, `ticket`, `report`,
`audit`, `verify`. Absent backends print the JSON error envelope and exit 5 (B5
partial until Phase 4); human-only verbs (`killswitch clear`, `state halt --clear`,
`state autonomy`, `live confirm`) record their intent shape and exit 5 (R22); replay
maintenance verbs exit 5. `paper` and `state` require `--seat` and refuse
`sniper`/`exit`. Hidden `tools <id> --help` prints the tool JSON schema (B8).
Exit codes: 0 ok; 1 config or usage; 2 ledger inconsistent; 3 live refused; 4 corrupt
fixture; 5 not implemented. argparse's own exit 2 is overridden so that 2 means only a
ledger inconsistency. Stdout carries JSON (or the doctor report and the engine decision);
diagnostics go to stderr.

Run order: refuse key-bearing CLI values -> parse -> settings (mode R30) -> logging ->
live gate (live exits 3 before any other work) -> verb. For the replay cycle: manifest
verification (exit 4, before any ledger file exists) -> recreate ledger -> map fixture
ticks to evidence-less engine candidates -> run the pure filter stage -> print one
`engine decision=` line -> append one `JournalNote` (source=replay) -> verify chain.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from collections.abc import Awaitable, Callable, Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, TextIO

from pydantic import ValidationError

from pumpgrok.config.settings import (
    ConfigError,
    Settings,
    current_profile,
    load_settings,
    refuse_cli_secrets,
)
from pumpgrok.contracts.projection import short_to_seat
from pumpgrok.core.errors import DataStale, PumpgrokError, ReplayMissingRecord
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool
from pumpgrok.doctor import doctor_report
from pumpgrok.execution.live.live_gate import LiveGate, refusal_lines
from pumpgrok.ledger.store import LedgerInconsistent
from pumpgrok.logging.json import setup_logging
from pumpgrok.replay.clock import WallClock
from pumpgrok.replay.fixtures import CorruptFixture
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.runner import run_replay
from pumpgrok.tools import build_operator_registry

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_LEDGER = 2
EXIT_LIVE = 3
EXIT_FIXTURE = 4
EXIT_NOT_IMPLEMENTED = 5

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


if TYPE_CHECKING:
    _VerbsAction = argparse._SubParsersAction[_Parser]


def _ticket(value: str) -> str:
    if not TICKET_RE.fullmatch(value):
        raise UsageError(f"bad --ticket {value!r}: want SOL-YYYYMMDD-NNN")
    return value


def _mint(value: str) -> str:
    if not 32 <= len(value) <= 44 or any(char not in _BASE58 for char in value):
        raise UsageError("bad --mint: want 32-44 base58 characters")
    return value


def _size_sol(value: str) -> Decimal:
    """Parse --size-sol once, at the CLI boundary (R28): Decimal in, lamports out."""
    try:
        size = Decimal(value)
        valid = size.is_finite() and size > 0
    except InvalidOperation:
        valid = False
    if not valid:
        raise UsageError(f"bad --size-sol {value!r}: want a positive number") from None
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


def size_sol_to_lamports(size_sol: Decimal) -> int:
    """Convert a SOL size to lamports once, here, so every path shares one rounding."""
    return int((size_sol * LAMPORTS_PER_SOL).to_integral_value(rounding=ROUND_HALF_UP))


def _not_implemented(verb: str, intent: dict[str, Any] | None = None) -> int:
    """Absent-subsystem contract: fixed JSON on stdout, one stderr line, exit 5.

    Human-only verbs (R22) record their parsed intent shape in the envelope
    so the Phase 4 backend knows exactly what was requested.
    """
    envelope: dict[str, Any] = {"ok": False, "status": "not-yet-implemented", "verb": verb}
    if intent is not None:
        envelope["intent"] = intent
    _say(sys.stdout, json.dumps(envelope))
    _say(sys.stderr, f"not implemented: `{verb}` is not yet implemented in this release")
    return EXIT_NOT_IMPLEMENTED


def _refuse_forbidden_seat(seat: str, verb: str) -> int | None:
    """Refuse forbidden_owners callers (jobs.yaml) with exit 1. None means allowed."""
    if seat in FORBIDDEN_OWNERS:
        _say(sys.stderr, f"refused: seat {seat!r} is a forbidden owner for `{verb}`")
        return EXIT_CONFIG
    return None


_EXIT_BY_CODE = {
    "not_yet_implemented": EXIT_NOT_IMPLEMENTED,
    "ledger_unavailable": EXIT_LEDGER,
    "live_gate": EXIT_LIVE,
}


def _exit_for_code(code: str) -> int:
    """Map a tool error code to the CLI exit contract (docstring); unknown codes exit 1."""
    return _EXIT_BY_CODE.get(code, EXIT_CONFIG)


def _tool_error(verb: str, code: str, message: str) -> int:
    """Print the JSON error envelope (T-03-07-03: code+message only) with the mapped exit."""
    _say(sys.stdout, json.dumps({"ok": False, "code": code, "message": message}))
    _say(sys.stderr, f"{verb} failed: {code}: {message}")
    return _exit_for_code(code)


def _repo_root() -> Path:
    """Repo root for repo-anchored tool inputs (ownership.yaml, gates dir)."""
    return Path(__file__).resolve().parents[2]


def _seat_manifest_id(seat: str) -> str:
    """Map a CLI --seat to a roster seat id.

    Accepts a roster short (chief, scout, ...), the operator seat ``desk``
    (the console acts under the supervisor seat until Phase 4 operator
    identity lands with approvals), or a full seat id (bot-04-sniper).
    Unknown values are usage errors. The sniper/exit string filter in
    :func:`_refuse_forbidden_seat` stays a policy layer; the control is the
    registry grant plus the approval record (R63).
    """
    if seat == "desk":
        return "bot-00-chief"
    shorts = short_to_seat()
    if seat in shorts:
        return shorts[seat]
    return seat


async def _with_tools(
    verb: str,
    seat: str,
    settings: Settings,
    capabilities: Sequence[str],
    use: Callable[[list[Tool]], Awaitable[int]],
) -> int:
    """Build the operator registry, resolve ``seat``, find every capability (I1).

    Each find refusal prints the JSON envelope with the mapped exit before
    anything runs. Otherwise ``use`` receives the resolved tools and decides:
    call one (functional backends), fail on the approval gate (paper), or
    return not-yet-implemented (Phase 4 orchestration). No tool implementation
    is ever imported or called directly here; everything goes through find().
    """
    reg, manifests, client = build_operator_registry(
        data_dir=Path("var") / "desk",
        repo_root=_repo_root(),
        settings=settings,
    )
    try:
        try:
            manifest = manifests[_seat_manifest_id(seat)]
        except KeyError:
            raise UsageError(f"bad --seat {seat!r}: unknown seat") from None
        factory = IdFactory(WallClock(), make_rng(settings.replay.seed))
        with bind_correlation(CorrelationId.new(factory)):
            tools: list[Tool] = []
            for capability in capabilities:
                try:
                    tools.append(
                        reg.find(
                            capability,
                            max_side_effect=SideEffect.PAPER_WRITE,
                            bot=manifest,
                        )
                    )
                except PumpgrokError as exc:
                    return _tool_error(verb, exc.code, exc.message)
            return await use(tools)
    finally:
        await client.aclose()


def _run_wired(
    verb: str,
    seat: str,
    settings: Settings,
    capabilities: Sequence[str],
    use: Callable[[list[Tool]], Awaitable[int]],
) -> int:
    """Run one wired verb: registry build, find (I1), then the verb tail."""
    return asyncio.run(_with_tools(verb, seat, settings, capabilities, use))


def _call_use(
    verb: str, index: int, fields: dict[str, Any]
) -> Callable[[list[Tool]], Awaitable[int]]:
    """Tail that validates one input through the tool spec and calls the tool (B5).

    The input model comes from the resolved spec, so the CLI never imports a
    tool module. Success prints the output JSON; PumpgrokError (including the
    absent-backend not_yet_implemented) prints the envelope with the exit map.
    """

    async def use(tools: list[Tool]) -> int:
        tool = tools[index]
        try:
            payload = tool.spec.input_model(**fields)
        except ValidationError as exc:
            return _tool_error(
                verb,
                "invalid_arguments",
                f"invalid arguments for {tool.spec.name}: {exc.errors()[0]['msg']}",
            )
        try:
            out = await tool(payload)
        except PumpgrokError as exc:
            return _tool_error(verb, exc.code, exc.message)
        _say(sys.stdout, json.dumps(out.model_dump(mode="json")))
        return EXIT_OK

    return use


def _skip_use(verb: str) -> Callable[[list[Tool]], Awaitable[int]]:
    """Tail for Phase 4 orchestration verbs: find (I1) proves the path, then exit 5."""

    async def use(_tools: list[Tool]) -> int:
        return _not_implemented(verb)

    return use


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


def _add_run(verbs: _VerbsAction, mode_option: _Parser) -> None:
    run = verbs.add_parser("run", parents=[mode_option], help="run the desk")
    run.add_argument("--once", action="store_true", help="run a single cycle and exit")
    run.add_argument("--replay", metavar="DIR", default=None, help="recorded fixture directory")
    run.add_argument(
        "--record", metavar="DATASET", default=None, help="record a dataset (not yet implemented)"
    )
    run.add_argument(
        "--duration", metavar="SECONDS", default=None, type=int, help="record duration (R40)"
    )


def _add_simple(verbs: _VerbsAction, mode_option: _Parser) -> None:
    verbs.add_parser("doctor", parents=[mode_option], help="report subsystem health")
    verbs.add_parser("audit", parents=[mode_option], help="audit the ledger (not yet implemented)")
    verify = verbs.add_parser("verify", parents=[mode_option], help="verify a fixture or ledger")
    verify.add_argument("--fixture", required=True, metavar="DATASET", help="dataset to verify")
    report = verbs.add_parser("report", parents=[mode_option], help="emit a desk report")
    report_period = report.add_mutually_exclusive_group(required=True)
    report_period.add_argument("--daily", action="store_true", help="daily report")
    report_period.add_argument("--weekly", action="store_true", help="weekly report")


def _add_scout(verbs: _VerbsAction, mode_option: _Parser) -> None:
    scout = verbs.add_parser("scout", parents=[mode_option], help="discovery verbs")
    scout_cmd = scout.add_subparsers(dest="cmd", required=True, metavar="SCOUT")
    scout_discover = scout_cmd.add_parser("discover", help="discover new launches")
    scout_discover.add_argument("--max-leads", type=int, default=5, help="max leads this run")
    scout_pipeline = scout_cmd.add_parser("pipeline", help="ingest pipeline candidates")
    scout_pipeline.add_argument("--candidates", action="store_true", help="read candidates")
    scout_pipeline.add_argument("--limit", type=int, default=5, help="max candidates this run")


def _add_risk_chief_rug(verbs: _VerbsAction, mode_option: _Parser) -> None:
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


def _add_journal_ticket(verbs: _VerbsAction, mode_option: _Parser) -> None:
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


def _add_state(verbs: _VerbsAction, mode_option: _Parser) -> None:
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


def _add_tail(verbs: _VerbsAction, mode_option: _Parser) -> None:
    killswitch = verbs.add_parser("killswitch", parents=[mode_option], help="killswitch verbs")
    killswitch_cmd = killswitch.add_subparsers(dest="cmd", required=True, metavar="KILLSWITCH")
    killswitch_set = killswitch_cmd.add_parser("set", help="engage the killswitch")
    killswitch_set.add_argument("--reason", required=True, help="why the killswitch is set")
    killswitch_flatten = killswitch_cmd.add_parser(
        "flatten", help="request flatten of every open paper position"
    )
    killswitch_flatten.add_argument("--reason", required=True, help="why open positions flatten")
    killswitch_clear = killswitch_cmd.add_parser(
        "clear", help="release the killswitch (human only)"
    )
    killswitch_clear.add_argument("--by", required=True, help="human releasing the killswitch")
    killswitch_clear.add_argument("--reason", required=True, help="why the killswitch clears")
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
    parser = _Parser(
        prog="pumpgrok",
        description=(
            "PumpGrok paper-first trading desk. Section-12 wrappers print JSON "
            "by default; `run` prints the engine-decision line and `doctor` "
            "prints a text report."
        ),
    )
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
    result = run_replay(source, settings.filter, seed=settings.replay.seed)
    _say(sys.stdout, f"engine decision={result.decision} reason={result.reason}")
    return EXIT_OK


def _paper(args: argparse.Namespace, settings: Settings) -> int:
    verb = f"paper {args.cmd}"
    refused = _refuse_forbidden_seat(args.seat, verb)
    if refused is not None:
        return refused
    lamports = size_sol_to_lamports(args.size_sol)
    if lamports > settings.risk.paper_equity_lamports:
        _say(sys.stderr, "usage error: --size-sol exceeds paper equity")
        return EXIT_CONFIG

    async def use(_tools: list[Tool]) -> int:
        # R63: no paper trade without a valid approval. Phase 3 has no
        # approval-issue/consume path (RiskEngine check plus the PaperAdapter
        # place transaction land in Phase 4), so every presented approval_id
        # is unknown: fail closed with exit 1 and write nothing. A fresh
        # decision_id is minted per invocation here in Phase 4 (R23).
        _say(
            sys.stdout,
            json.dumps(
                {
                    "ok": False,
                    "code": "approval_unknown",
                    "message": f"refused: no valid approval_id for `{verb}` (R63)",
                }
            ),
        )
        _say(sys.stderr, f"refused: no valid approval_id for `{verb}` (R63)")
        return EXIT_CONFIG

    return _run_wired(verb, args.seat, settings, ("exec.simulate", "exec.place"), use)


def _state(args: argparse.Namespace, settings: Settings) -> int:
    verb = f"state {args.cmd}"
    refused = _refuse_forbidden_seat(args.seat, verb)
    if refused is not None:
        return refused
    if args.cmd == "halt" and args.clear:
        # Human-only (R22): the ledger HaltCleared + ApprovalRecord land in Phase 4.
        return _not_implemented("state halt --clear", {"by": args.by, "reason": args.reason})
    if args.cmd == "autonomy":
        # Human-only (R17, R40): the ledger ConfigChanged lands in Phase 4.
        return _not_implemented("state autonomy", {"policy": args.policy})
    return _run_wired(verb, args.seat, settings, ("risk.halt_status",), _call_use(verb, 0, {}))


def _killswitch(args: argparse.Namespace, settings: Settings) -> int:
    verb = f"killswitch {args.cmd}"
    if args.cmd == "clear":
        # Human-only (R22): the ledger KillSwitchCleared + ApprovalRecord
        # kind killswitch_clear land in Phase 4. No tool, no seat.
        return _not_implemented(verb, {"by": args.by, "reason": args.reason})
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
            _call_use(verb, 0, {"action": "flatten_request", "reason": args.reason}),
        )
    return _run_wired(verb, "risk", settings, ("risk.halt_status",), _call_use(verb, 0, {}))


def _find_only(verb: str, seat: str, settings: Settings, capabilities: Sequence[str]) -> int:
    """Section-12 verb whose multi-tool orchestration lands in Phase 4 (B5 partial).

    Every catalog tool resolves through find (I1 enforced; a wrong seat prints
    the refusal envelope instead of 5), then the verb returns the
    not-yet-implemented envelope because calling would need network backends
    or Phase 4 orchestration. No tool implementation is called.
    """
    return _run_wired(verb, seat, settings, capabilities, _skip_use(verb))


def _tools_schema(tool_id: str) -> int:
    """Hidden developer verb (B8): print one catalog tool JSON schema, exit 0."""

    async def _schema() -> int:
        settings = load_settings()
        reg, _, client = build_operator_registry(
            data_dir=Path("var") / "desk",
            repo_root=_repo_root(),
            settings=settings,
        )
        try:
            try:
                spec = reg.spec(tool_id)
            except KeyError:
                return _tool_error(f"tools {tool_id}", "unknown_tool", f"unknown tool: {tool_id}")
            _say(
                sys.stdout,
                json.dumps(
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "input_schema": spec.input_model.model_json_schema(),
                        "output_schema": spec.output_model.model_json_schema(),
                        "side_effect": str(spec.side_effect),
                        "timeout_s": spec.timeout_s,
                        "rate_limit_key": spec.rate_limit_key,
                        "requires_approval": spec.requires_approval,
                        "idempotent": spec.idempotent,
                        "backend": spec.backend,
                    }
                ),
            )
            return EXIT_OK
        finally:
            await client.aclose()

    return asyncio.run(_schema())


_TOOLS_HELP = (
    "usage: pumpgrok tools <id> [--help]",
    "",
    "Hidden developer verb (B8): print one catalog tool JSON schema.",
    "Not listed in top-level help. The schema is mode-independent.",
    "",
    "examples:",
    "  pumpgrok tools exec.quote --help",
)


def _tools_entry(rest: list[str]) -> int:
    """Route the hidden `tools` verb without argparse (B8: absent from top help)."""
    if not rest:
        raise UsageError("tools requires a tool id (try `pumpgrok tools exec.quote --help`)")
    if rest in (["--help"], ["-h"]):
        _say(sys.stdout, *_TOOLS_HELP)
        return EXIT_OK
    tool_id = rest[0]
    if tool_id.startswith("-"):
        raise UsageError(f"unexpected arguments for `tools`: {' '.join(rest)}")
    if rest[1:] not in ([], ["--help"], ["-h"]):
        raise UsageError(f"unexpected arguments for `tools {tool_id}`: {' '.join(rest[1:])}")
    return _tools_schema(tool_id)


_SCOUT_FLOW = ("market.trades", "market.liquidity", "onchain.authorities", "journal.append")
_RISK_AUDIT = (
    "portfolio.ledger_read",
    "portfolio.exposure",
    "portfolio.pnl",
    "risk.drawdown",
    "risk.check_limits",
    "risk.halt_status",
    "desk.event_emit",
)
_CHIEF_PICKUP = ("desk.brief", "risk.halt_status", "exec.positions", "notify.alert")
_RUG_WATCH = (
    "onchain.lp_status",
    "onchain.authorities",
    "onchain.top_holders",
    "market.price",
    "desk.event_emit",
)


def _verb_label(args: argparse.Namespace) -> str:
    """Audit label for a find-only verb: the verb plus its subcommand, when it has one."""
    verb: str = args.verb
    cmd: str | None = getattr(args, "cmd", None)
    return verb if cmd is None else f"{verb} {cmd}"


def _doctor_verb(_args: argparse.Namespace, settings: Settings) -> int:
    _say(sys.stdout, *doctor_report(settings))
    return EXIT_OK


def _live_verb(_args: argparse.Namespace, _settings: Settings) -> int:
    # Human-only (R21): the HMAC-bound live.confirmation_record lands in Phase 4.
    return _not_implemented("live confirm")


def _verify_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Replay a fixture dataset into its canonical replay ledger and verify it.

    ``--fixture`` names a directory or a dataset bundled under
    ``tests/fixtures/replay/<name>``. The run recreates
    ``var/replay/<dataset>/ledger.sqlite``, prints the ``events.hash`` of the
    chain, and exits 0 only when the chain verifies CONSISTENT.
    """
    raw = str(args.fixture)
    candidate = Path(raw)
    if candidate.is_dir():
        dataset_dir = candidate
    else:
        bundled = _repo_root() / "tests" / "fixtures" / "replay" / raw
        if not bundled.is_dir():
            raise ConfigError([f"unknown fixture dataset: {raw!r}"])
        dataset_dir = bundled
    try:
        result = run_replay(dataset_dir, settings.filter, seed=settings.replay.seed)
    except (DataStale, ReplayMissingRecord) as exc:
        _say(sys.stderr, f"replay failed: {exc.code}: {exc.message}")
        return EXIT_CONFIG
    _say(sys.stdout, f"events.hash={result.events_hash}")
    _say(sys.stdout, f"verify=CONSISTENT seq={result.seq} events={result.events_read}")
    return EXIT_OK


def _replay_verb(args: argparse.Namespace, _settings: Settings) -> int:
    return _not_implemented(f"replay {args.cmd}")


# Find-only verbs (B5 partial): verb -> (calling seat, capabilities resolved through find).
_FIND_ONLY_ROUTES: dict[str, tuple[str, tuple[str, ...]]] = {
    "scout": ("scout", _SCOUT_FLOW),
    "risk": ("risk", _RISK_AUDIT),
    "chief": ("chief", _CHIEF_PICKUP),
    "rug": ("rug", _RUG_WATCH),
    "journal": ("journal", ("journal.render_report",)),
    "ticket": ("journal", ("journal.append", "portfolio.ledger_read")),
    "report": ("journal", ("journal.render_report",)),
    "audit": ("desk", ("desk.doctor",)),
}

_VERB_HANDLERS: dict[str, Callable[[argparse.Namespace, Settings], int]] = {
    "doctor": _doctor_verb,
    "run": _run,
    "paper": _paper,
    "state": _state,
    "killswitch": _killswitch,
    "live": _live_verb,
    "replay": _replay_verb,
    "verify": _verify_verb,
}


def _route(args: argparse.Namespace, settings: Settings) -> int:
    find_route = _FIND_ONLY_ROUTES.get(args.verb)
    if find_route is not None:
        seat, capabilities = find_route
        return _find_only(_verb_label(args), seat, settings, capabilities)
    handler = _VERB_HANDLERS.get(args.verb)
    if handler is None:
        return _not_implemented(args.verb)
    return handler(args, settings)


def _dispatch(argv: Sequence[str]) -> int:
    refuse_cli_secrets(argv)
    if argv and argv[0] == "tools":
        return _tools_entry(list(argv[1:]))
    args = build_parser().parse_args(list(argv))
    settings = load_settings(**_settings_kwargs(args.mode))
    setup_logging(mode=settings.effective_mode, profile=current_profile())
    return _route(args, settings)


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
