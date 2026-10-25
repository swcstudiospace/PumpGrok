"""Verb routing, dispatch and the main entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable, Sequence

from pumpgrok.cli.backtest import _backtest_verb, _replay_verb
from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_FIXTURE, EXIT_LEDGER, _FIND_ONLY_ROUTES
from pumpgrok.cli.errors import UsageError, _not_implemented, _say
from pumpgrok.cli.parsing import build_parser
from pumpgrok.cli.verbs_ops import _doctor_verb, _live_verb, _report_verb, _verify_verb
from pumpgrok.cli.verbs_state import _killswitch, _paper, _run, _state, _ticket_verb
from pumpgrok.cli.wiring import _find_only, _tools_entry, _verb_label
from pumpgrok.config.settings import (
    ConfigError,
    Settings,
    current_profile,
    load_settings,
    refuse_cli_secrets,
)
from pumpgrok.core.errors import LedgerInconsistent
from pumpgrok.logging.json import setup_logging
from pumpgrok.replay.fixtures import CorruptFixture

log = logging.getLogger("pumpgrok.cli")


def _settings_kwargs(mode: str | None) -> dict[str, str]:
    # Passing mode=None would shadow PUMPGROK_MODE with a null init value; omit it instead.
    return {} if mode is None else {"mode": mode}


_VERB_HANDLERS: dict[str, Callable[[argparse.Namespace, Settings], int]] = {
    "doctor": _doctor_verb,
    "run": _run,
    "paper": _paper,
    "state": _state,
    "killswitch": _killswitch,
    "ticket": _ticket_verb,
    "live": _live_verb,
    "verify": _verify_verb,
    "report": _report_verb,
    "backtest": _backtest_verb,
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
