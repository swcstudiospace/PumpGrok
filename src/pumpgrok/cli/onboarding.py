"""`pumpgrok onboarding`: operator-only tool access and RPC choice (ONB-04, ONB-08; D-08, D-09).

Every write needs three things, in this order: an interactive terminal on stdin and stdout, the
operator account that owns the operator key (see ``pumpgrok.ledger.operator_choices``), and the
exact confirmation phrase typed at the prompt. Agents and pipes get a refusal and nothing is
written. No secret is accepted on argv, read from the environment or printed.

Reads (``list`` and ``rpc`` without ``--endpoint``) need only the authority to be sound.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_OK
from pumpgrok.cli.errors import UsageError, _say
from pumpgrok.cli.validators import _utc_now
from pumpgrok.config.settings import Settings
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, effective_roster, roster_tool_names
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools import ensure_paper_genesis

KEY_PHRASE = "create operator key"


def _stdio_is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _confirm(phrase: str, *, operator: bool = True) -> str:
    """Require an interactive terminal, the operator account (when ``operator``) and the phrase.

    Returns the operator label, or an empty string when no operator identity is needed.
    """
    if not _stdio_is_interactive():
        raise oc.OperatorChoiceError(
            "refused: an interactive terminal is required; agents and pipes cannot record "
            "operator choices"
        )
    label = oc.writer_identity(oc.OPERATOR_DIR) if operator else ""
    typed = input(f"Type exactly '{phrase}' to record this choice: ")
    if typed.strip() != phrase:
        raise oc.OperatorChoiceError("refused: confirmation did not match; nothing was recorded")
    return label


def _check_seat(seat: str) -> None:
    if seat not in EXPECTED_SEAT_IDS:
        raise UsageError(f"unknown seat {seat!r}; want one of {', '.join(EXPECTED_SEAT_IDS)}")


def _tool_state(decision: oc.Decision | None, authority: str) -> str:
    if authority != "ok":
        return "unavailable"
    if decision is None:
        return "not_granted"
    if not decision.bound:
        return "unbound"
    return "granted" if decision.decision == "allow" else "denied"


def _list(_args: argparse.Namespace, _settings: Settings) -> int:
    authority = "ok"
    reason = ""
    decisions: dict[str, oc.Decision] = {}
    try:
        decisions = oc.read_authority(oc.OPERATOR_DIR, PAPER_LEDGER_PATH)
    except oc.OperatorChoiceError as exc:
        authority = "unavailable"
        reason = str(exc)
    seats: dict[str, list[dict[str, Any]]] = {}
    for seat in EXPECTED_SEAT_IDS:
        rows = []
        for entry in effective_roster(oc.DEFAULT_CONTRACTS_DIR, seat):
            name = str(entry["name"])
            decision = decisions.get(oc.tool_scope(seat, name))
            rows.append(
                {
                    "tool": name,
                    "side_effect": str(entry["side_effect"]),
                    "state": _tool_state(decision, authority),
                }
            )
        seats[seat] = rows
    rpc: dict[str, Any] = {"status": "unavailable"}
    if authority == "ok":
        status, endpoint = oc.rpc_status(oc.OPERATOR_DIR, PAPER_LEDGER_PATH)
        rpc = {"status": status}
        if endpoint is not None:
            rpc["endpoint"] = endpoint.as_dict()
    payload: dict[str, Any] = {"authority": authority, "seats": seats, "rpc": rpc}
    if reason:
        payload["reason"] = reason
    _say(sys.stdout, json.dumps(payload, indent=2, sort_keys=True))
    return EXIT_OK


def _init_key(_args: argparse.Namespace, _settings: Settings) -> int:
    _confirm(KEY_PHRASE, operator=False)
    oc.init_key(oc.OPERATOR_DIR)
    _say(sys.stdout, json.dumps({"operator_key": str(oc.OPERATOR_DIR / oc.KEY_NAME)}))
    return EXIT_OK


def _record_tool(
    args: argparse.Namespace, settings: Settings, decision: str, phrase_verb: str
) -> int:
    _check_seat(args.seat)
    if args.tool not in roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, args.seat):
        raise UsageError(f"{args.tool} is not in the roster of {args.seat}")
    phrase = f"{phrase_verb} {args.seat} {args.tool}"
    label = _confirm(phrase)
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        ensure_paper_genesis(store, settings.risk)
        oc.record_tool_choice(
            store,
            seat=args.seat,
            tool=args.tool,
            decision=decision,
            now=_utc_now(),
        )
    finally:
        store.close()
    _say(
        sys.stdout,
        json.dumps({"seat": args.seat, "tool": args.tool, "decision": decision, "by": label}),
    )
    return EXIT_OK


def _access(args: argparse.Namespace, settings: Settings) -> int:
    return _record_tool(args, settings, args.decision, args.decision)


def _revoke(args: argparse.Namespace, settings: Settings) -> int:
    return _record_tool(args, settings, "revoke", "revoke")


def _rpc(args: argparse.Namespace, settings: Settings) -> int:
    if args.endpoint is None:
        status, endpoint = oc.rpc_status(oc.OPERATOR_DIR, PAPER_LEDGER_PATH)
        payload: dict[str, Any] = {"status": status}
        if endpoint is not None:
            payload["endpoint"] = endpoint.as_dict()
        _say(sys.stdout, json.dumps(payload))
        return EXIT_OK
    try:
        chosen = oc.endpoint_choice(args.endpoint, settings.rpc.endpoints)
    except ValueError as exc:
        raise UsageError(f"bad --endpoint: {exc}") from exc
    label = _confirm(f"rpc {chosen.label()}")
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        oc.record_rpc_choice(
            store,
            url=args.endpoint,
            configured_urls=settings.rpc.endpoints,
            now=_utc_now(),
        )
    finally:
        store.close()
    _say(
        sys.stdout,
        json.dumps({"status": "explicit", "endpoint": chosen.as_dict(), "by": label}),
    )
    return EXIT_OK


_HANDLERS = {
    "init-key": _init_key,
    "list": _list,
    "access": _access,
    "revoke": _revoke,
    "rpc": _rpc,
}


def onboarding_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Run one onboarding subcommand. Authority refusals exit 1 and write nothing."""
    try:
        return _HANDLERS[args.cmd](args, settings)
    except oc.OperatorChoiceError as exc:
        _say(sys.stderr, str(exc))
        return EXIT_CONFIG
