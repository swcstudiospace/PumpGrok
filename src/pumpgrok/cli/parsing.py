"""Argparse graph: per-verb flags and the top-level parser."""

from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING

from pumpgrok.cli.errors import _Parser
from pumpgrok.cli.validators import _approval_id, _mint, _size_sol, _slippage_bps, _ticket

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
    paper_buy = paper_cmd.add_parser("buy", help="paper buy against the paper engine")
    _add_paper_trade_flags(paper_buy)
    paper_sell = paper_cmd.add_parser("sell", help="paper sell against the paper engine")
    _add_paper_trade_flags(paper_sell)
    live = verbs.add_parser("live", parents=[mode_option], help="live verbs")
    live_cmd = live.add_subparsers(dest="cmd", required=True, metavar="LIVE")
    live_confirm = live_cmd.add_parser("confirm", help="record a human live-gate confirmation")
    live_confirm.add_argument("--by", required=True, help="confirming human (human:<name>)")
    live_confirm.add_argument("--notional-cap", required=True, help="cap SOL, 0 < cap <= 1")
    live_confirm.add_argument("--expires", required=True, help="confirmation expiry UTC (ISO-8601)")
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
