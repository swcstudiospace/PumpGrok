"""Verb routing, dispatch and the main entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence

from pumpgrok.cli.backtest import _backtest_verb
from pumpgrok.cli.codes import (
    _FIND_ONLY_ROUTES,
    EXIT_CONFIG,
    EXIT_FIXTURE,
    EXIT_LEDGER,
    EXIT_LIVE,
)
from pumpgrok.cli.errors import UsageError, _not_implemented, _say
from pumpgrok.cli.events import events_verb
from pumpgrok.cli.ledger import _ledger_verb
from pumpgrok.cli.onboarding import onboarding_verb
from pumpgrok.cli.promotion_verb import _promotion_verb
from pumpgrok.cli.parsing import build_parser
from pumpgrok.cli.verbs_ops import (
    _doctor_verb,
    _live_verb,
    _replay_verb,
    _report_verb,
    _verify_verb,
)
from pumpgrok.cli.verbs_state import _killswitch, _paper, _run, _state, _ticket_verb
from pumpgrok.cli.wiring import _find_only, _tools_entry, _verb_label
from pumpgrok.config.settings import (
    ConfigError,
    Settings,
    confirm_wallet_allowlist,
    current_profile,
    load_settings,
    refuse_cli_secrets,
)
from pumpgrok.ledger.store import LedgerInconsistent
from pumpgrok.logging.json import setup_logging
from pumpgrok.replay.fixtures import CorruptFixture

log = logging.getLogger("pumpgrok.cli")


def _settings_kwargs(mode: str | None) -> dict[str, str]:
    # Passing mode=None would shadow PUMPGROK_MODE with a null init value; omit it instead.
    return {} if mode is None else {"mode": mode}


# Verbs that start live work. A live start needs each allowlist address retyped by the operator.
_WALLET_CONFIRM_VERBS = frozenset({"run", "live"})


def _stdio_is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _confirm_live_wallet(args: argparse.Namespace, settings: Settings) -> None:
    """Refuse a live start unless an interactive operator retypes every allowlist address.

    Runs after settings load, which already resolved the effective mode without reading the
    wallet on the paper path. Paper and read-only verbs are not affected.
    """
    if args.verb not in _WALLET_CONFIRM_VERBS:
        return
    if settings.effective_mode != "live" or not settings.wallet.allowlist:
        return
    if not _stdio_is_interactive():
        raise ConfigError(
            ["live start refused: retyping the wallet allowlist needs an interactive terminal"]
        )
    confirm_wallet_allowlist(settings.wallet.allowlist, input)


def _events_handler(args: argparse.Namespace, settings: Settings) -> int:
    """Run the events verb. The handler is selected only for that verb."""
    return events_verb(args, settings)


def _ledger_handler(args: argparse.Namespace, settings: Settings) -> int:
    """Run the ledger backup/restore verb. Selected only for that verb."""
    return _ledger_verb(args, settings)


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
    "replay": _replay_verb,
    "events": _events_handler,
    "onboarding": onboarding_verb,
    "promotion": _promotion_verb,
    "ledger": _ledger_handler,
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


def _apply_wake_mode(args: argparse.Namespace, settings: Settings) -> Settings:
    """The `--wake-mode` flag overrides events.wake_mode; only run and doctor carry the flag."""
    wake_mode = getattr(args, "wake_mode", None)
    if wake_mode is None:
        return settings
    events = settings.events.model_copy(update={"wake_mode": wake_mode})
    return settings.model_copy(update={"events": events})


def _refuse_disabled_live(args: argparse.Namespace) -> int | None:
    """Refuse live mode for record and serve before settings or wallet confirmation.

    A configured live wallet must not turn this refusal into exit 1. One stderr line names it.
    """
    if getattr(args, "mode", None) != "live":
        return None
    verb = getattr(args, "verb", None)
    if verb == "run" and getattr(args, "record", None) is not None:
        _say(sys.stderr, "refused: run --record does not run in live mode")
        return EXIT_LIVE
    if verb == "live" and getattr(args, "cmd", None) == "serve":
        _say(sys.stderr, "refused: live serve does not run in live mode")
        return EXIT_LIVE
    return None


def _dispatch(argv: Sequence[str]) -> int:
    refuse_cli_secrets(argv)
    if argv and argv[0] == "tools":
        return _tools_entry(list(argv[1:]))
    args = build_parser().parse_args(list(argv))
    refused = _refuse_disabled_live(args)
    if refused is not None:
        return refused
    settings = _apply_wake_mode(args, load_settings(**_settings_kwargs(args.mode)))
    _confirm_live_wallet(args, settings)
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
