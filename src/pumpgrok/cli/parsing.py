"""Argparse graph: per-verb flags and the top-level parser."""

from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING

from pumpgrok.cli.errors import _Parser
from pumpgrok.cli.validators import _approval_id, _mint, _size_sol, _slippage_bps, _ticket
from pumpgrok.config.sections.v4 import WAKE_MODES

log = logging.getLogger("pumpgrok.cli")

if TYPE_CHECKING:
    _VerbsAction = argparse._SubParsersAction[_Parser]


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


def _add_wake_mode(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--wake-mode",
        choices=WAKE_MODES,
        default=None,
        dest="wake_mode",
        help="supervisor wake: cadence (default) or event; overrides events.wake_mode",
    )


def _add_run(verbs: _VerbsAction, mode_option: _Parser) -> None:
    run = verbs.add_parser("run", parents=[mode_option], help="run the desk")
    run.add_argument("--once", action="store_true", help="run a single cycle and exit")
    run.add_argument("--replay", metavar="DIR", default=None, help="recorded fixture directory")
    run.add_argument(
        "--serve",
        action="store_true",
        help="replay a recorded dataset in a loop, serving /healthz and /metrics",
    )
    run.add_argument(
        "--record", metavar="DATASET", default=None, help="record a live-paper dataset"
    )
    run.add_argument(
        "--duration", metavar="SECONDS", default=None, type=int, help="record duration in seconds"
    )
    run.add_argument(
        "--mints",
        default=None,
        metavar="LIST",
        help="comma-separated mints to record; other mints are not admitted",
    )
    _add_wake_mode(run)


def _add_simple(verbs: _VerbsAction, mode_option: _Parser) -> None:
    doctor = verbs.add_parser("doctor", parents=[mode_option], help="report subsystem health")
    doctor.add_argument("--json", action="store_true", help="one record per operator input")
    _add_wake_mode(doctor)
    verbs.add_parser("audit", parents=[mode_option], help="audit the ledger (not yet implemented)")
    verify = verbs.add_parser("verify", parents=[mode_option], help="verify a fixture or ledger")
    verify.add_argument("--fixture", required=True, metavar="DATASET", help="dataset to verify")
    report = verbs.add_parser("report", parents=[mode_option], help="emit a desk report")
    report_period = report.add_mutually_exclusive_group(required=True)
    report_period.add_argument("--daily", action="store_true", help="daily report")
    report_period.add_argument("--weekly", action="store_true", help="weekly report")
    report.add_argument("--day", default=None, help="report day YYYY-MM-DD (default today)")
    report.add_argument("--week", default=None, help="week Monday YYYY-MM-DD (default this week)")
    report.add_argument("--out", default=None, help="write markdown to this path as well")
    backtest = verbs.add_parser("backtest", parents=[mode_option], help="run a backtest")
    backtest.add_argument("--fixture", required=True, metavar="DATASET", help="dataset to backtest")
    backtest.add_argument("--params", default=None, metavar="PATH", help="parameter-set JSON file")
    backtest.add_argument(
        "--paper-ledger",
        default=None,
        metavar="PATH",
        help="paper ledger sqlite for the same-window comparison",
    )
    backtest.add_argument(
        "--strategy",
        default=None,
        metavar="ID",
        help="registered strategy id; one strategy, no search",
    )


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
    ticket_create.add_argument(
        "--ticket", default=None, type=_ticket, help="ticket id SOL-YYYYMMDD-NNN"
    )
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
    state_autonomy.add_argument("--by", required=True, help="human setting the policy")
    _add_seat(state_autonomy)
    state_resume = state_cmd.add_parser("resume", help="resume a seat from observe-only")
    state_resume.add_argument("--seat", required=True, help="seat to resume")
    state_resume.add_argument("--by", required=True, help="human resuming the seat")


def _add_events(verbs: _VerbsAction, mode_option: _Parser) -> None:
    events = verbs.add_parser("events", parents=[mode_option], help="event sidecar verbs")
    events_cmd = events.add_subparsers(dest="cmd", required=True, metavar="EVENTS")
    dlq = events_cmd.add_parser("dlq", help="sidecar dead-letter queue")
    dlq_cmd = dlq.add_subparsers(dest="dlq_cmd", required=True, metavar="DLQ")
    dlq_cmd.add_parser("list", help="list sidecar dlq rows")
    replay = dlq_cmd.add_parser("replay", help="republish a named dlq row")
    replay.add_argument("name", help="dlq row name")
    purge = dlq_cmd.add_parser("purge", help="drop a named dlq row")
    purge.add_argument("name", help="dlq row name")


def _add_seat_tool(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seat", required=True, help="roster seat id, e.g. bot-04-sniper")
    parser.add_argument("--tool", required=True, help="a tool named in that seat's roster")


def _add_onboarding(verbs: _VerbsAction, mode_option: _Parser) -> None:
    onboarding = verbs.add_parser(
        "onboarding",
        parents=[mode_option],
        help="operator choices: seat tool access and the RPC endpoint",
    )
    onboarding_cmd = onboarding.add_subparsers(dest="cmd", required=True, metavar="ONBOARDING")
    onboarding_cmd.add_parser(
        "init-key", help="create the operator key (interactive terminal, operator account)"
    )
    onboarding_cmd.add_parser("list", help="roster-derived tool choices and the RPC choice")
    access = onboarding_cmd.add_parser("access", help="explicitly allow or deny a seat tool")
    _add_seat_tool(access)
    decision = access.add_mutually_exclusive_group(required=True)
    decision.add_argument("--allow", dest="decision", action="store_const", const="allow")
    decision.add_argument("--deny", dest="decision", action="store_const", const="deny")
    revoke = onboarding_cmd.add_parser("revoke", help="revoke a seat tool grant")
    _add_seat_tool(revoke)
    rpc = onboarding_cmd.add_parser("rpc", help="show, or choose, a configured RPC endpoint")
    rpc.add_argument(
        "--endpoint",
        default=None,
        help="a configured endpoint URL; only its scheme, host and port are recorded",
    )


def _add_tail(verbs: _VerbsAction, mode_option: _Parser) -> None:
    killswitch = verbs.add_parser("killswitch", parents=[mode_option], help="killswitch verbs")
    killswitch_cmd = killswitch.add_subparsers(dest="cmd", required=True, metavar="KILLSWITCH")
    killswitch_set = killswitch_cmd.add_parser("set", help="engage the killswitch")
    killswitch_set.add_argument("--reason", required=True, help="why the killswitch is set")
    killswitch_set.add_argument(
        "--strategy", default=None, help="engage a strategy kill for this strategy id"
    )
    killswitch_set.add_argument("--by", default=None, help="human engaging a strategy kill")
    killswitch_flatten = killswitch_cmd.add_parser(
        "flatten", help="request flatten of every open paper position"
    )
    killswitch_flatten.add_argument("--reason", required=True, help="why open positions flatten")
    killswitch_clear = killswitch_cmd.add_parser(
        "clear", help="release the killswitch (human only)"
    )
    killswitch_clear.add_argument("--by", required=True, help="human releasing the killswitch")
    killswitch_clear.add_argument("--reason", required=True, help="why the killswitch clears")
    killswitch_clear.add_argument(
        "--strategy", default=None, help="clear only the kill of this strategy id"
    )
    killswitch_cmd.add_parser("status", help="report killswitch state")
    paper = verbs.add_parser("paper", parents=[mode_option], help="paper trade verbs")
    paper_cmd = paper.add_subparsers(dest="cmd", required=True, metavar="PAPER")
    paper_buy = paper_cmd.add_parser("buy", help="paper buy against the paper engine")
    _add_paper_trade_flags(paper_buy)
    paper_sell = paper_cmd.add_parser("sell", help="paper sell against the paper engine")
    _add_paper_trade_flags(paper_sell)
    live = verbs.add_parser("live", parents=[mode_option], help="live verbs")
    live_cmd = live.add_subparsers(dest="cmd", required=True, metavar="LIVE")
    live_serve = live_cmd.add_parser("serve", help="serve the live-data paper root")
    live_serve.add_argument(
        "--mode",
        choices=("paper", "live"),
        default=argparse.SUPPRESS,
        help="execution mode; live is refused",
    )
    live_serve.add_argument(
        "--rpc",
        required=True,
        help="read-only RPC endpoint; required, no default",
    )
    live_serve.add_argument(
        "--once",
        action="store_true",
        help="run exactly one paper cycle and exit",
    )
    live_confirm = live_cmd.add_parser("confirm", help="record a human live-gate confirmation")
    live_confirm.add_argument("--by", required=True, help="confirming human (human:<name>)")
    live_confirm.add_argument("--notional-cap", required=True, help="cap SOL, 0 < cap <= 1")
    live_confirm.add_argument("--expires", required=True, help="confirmation expiry UTC (ISO-8601)")
    _add_replay(verbs, mode_option)


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from None
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer: {text!r}")
    return value


def _add_replay(verbs: _VerbsAction, mode_option: _Parser) -> None:
    replay = verbs.add_parser("replay", parents=[mode_option], help="replay dataset verbs")
    replay_cmd = replay.add_subparsers(dest="cmd", required=True, metavar="REPLAY")
    replay_trim = replay_cmd.add_parser("trim", help="trim a replay dataset")
    replay_trim.add_argument("--from", dest="from_dir", required=True, help="source dataset dir")
    replay_trim.add_argument("--to", dest="to_dir", required=True, help="destination dir")
    replay_trim.add_argument("--name", required=True, help="sealed dataset name")
    replay_trim.add_argument("--from-ts", dest="from_ts", required=True, help="window start UTC")
    replay_trim.add_argument("--to-ts", dest="to_ts", required=True, help="window end UTC")
    replay_rebuild = replay_cmd.add_parser("rebuild-ticks", help="rebuild ticks from a recording")
    replay_rebuild.add_argument("--from", dest="from_dir", required=True, help="source dataset dir")
    replay_rebuild.add_argument("--to", dest="to_file", required=True, help="ticks file to write")
    replay_import = replay_cmd.add_parser("import", help="import an external tick file")
    replay_import.add_argument("--source", required=True, help="external JSONL tick file")
    replay_import.add_argument("--to", dest="to_dir", required=True, help="dataset dir to write")
    replay_import.add_argument("--name", required=True, help="sealed dataset name")


def _add_ledger(verbs: _VerbsAction, mode_option: _Parser) -> None:
    ledger = verbs.add_parser("ledger", parents=[mode_option], help="ledger backup and restore")
    ledger_cmd = ledger.add_subparsers(dest="cmd", required=True, metavar="LEDGER")
    backup = ledger_cmd.add_parser("backup", help="write a ledger copy under the state directory")
    backup.add_argument("--ledger", default="var/ledger.sqlite", help="active ledger path")
    restore = ledger_cmd.add_parser(
        "restore", help="verify then atomically replace the active ledger"
    )
    restore.add_argument("--ledger", default="var/ledger.sqlite", help="active ledger path")
    restore.add_argument("--from", dest="from_", required=True, help="candidate ledger to verify")


def _add_promotion(verbs: _VerbsAction, mode_option: _Parser) -> None:
    promotion = verbs.add_parser("promotion", parents=[mode_option], help="promotion verbs")
    promotion_cmd = promotion.add_subparsers(dest="cmd", required=True, metavar="PROMOTION")
    demote = promotion_cmd.add_parser("demote", help="roll a strategy back one stage")
    demote.add_argument("--strategy", required=True, help="strategy id to roll back")
    demote.add_argument("--by", default="human:operator", help="acting human (human:<name>)")


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
    _add_events(verbs, mode_option)
    _add_ledger(verbs, mode_option)
    _add_promotion(verbs, mode_option)
    _add_tail(verbs, mode_option)
    _add_onboarding(verbs, mode_option)
    return parser
