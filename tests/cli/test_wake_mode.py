<<<<<<< HEAD
"""--wake-mode flag defaults to cadence and validates against the allowed set."""

import pytest

from pumpgrok.cli.parsing import build_parser
from pumpgrok.cli.wake_mode import (
    DEFAULT_WAKE_MODE,
    default_wake_mode,
    parse_wake_mode,
)


def test_default_is_cadence() -> None:
    assert DEFAULT_WAKE_MODE == "cadence"
    assert default_wake_mode() == "cadence"
    parser = build_parser()
    assert parser.parse_args(["run", "--mode", "paper", "--once"]).wake_mode == "cadence"
    assert (
        parser.parse_args(["run", "--mode", "paper", "--once", "--wake-mode", "event"]).wake_mode
        == "event"
    )


def test_unknown_mode_raises() -> None:
    with pytest.raises(ValueError):
        parse_wake_mode("hourly")


def test_valid_modes() -> None:
    assert parse_wake_mode("cadence") == "cadence"
    assert parse_wake_mode("event") == "event"
=======
"""The `--wake-mode` flag and the settings wake mode select event or cadence (EVT-10, EVT-13).

Cadence stays the default. The flag wins over settings when given; invalid values are refused
by the parser, which raises UsageError (cli/errors.py `_Parser.error`).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pumpgrok.cli.errors import UsageError
from pumpgrok.cli.parsing import build_parser
from pumpgrok.config.sections.v4 import WAKE_MODES, EventsSettings, resolve_wake_mode


def test_wake_modes_are_cadence_and_event() -> None:
    assert WAKE_MODES == ("cadence", "event")


def test_event_flag_selects_event_mode_on_run() -> None:
    args = build_parser().parse_args(["run", "--wake-mode", "event"])
    assert args.wake_mode == "event"
    assert resolve_wake_mode(args.wake_mode, EventsSettings().wake_mode) == "event"


def test_event_flag_selects_event_mode_on_doctor() -> None:
    args = build_parser().parse_args(["doctor", "--wake-mode", "event"])
    assert resolve_wake_mode(args.wake_mode, EventsSettings().wake_mode) == "event"


def test_no_flag_gives_cadence_by_default() -> None:
    args = build_parser().parse_args(["run", "--once", "--replay", "x"])
    assert args.wake_mode is None
    assert resolve_wake_mode(args.wake_mode, EventsSettings().wake_mode) == "cadence"


def test_no_flag_keeps_settings_event_mode() -> None:
    args = build_parser().parse_args(["run"])
    assert resolve_wake_mode(args.wake_mode, "event") == "event"


def test_explicit_flag_overrides_settings() -> None:
    args = build_parser().parse_args(["run", "--wake-mode", "cadence"])
    assert resolve_wake_mode(args.wake_mode, "event") == "cadence"


def test_invalid_wake_mode_is_refused() -> None:
    with pytest.raises(UsageError):
        build_parser().parse_args(["run", "--wake-mode", "live"])


def test_settings_default_is_cadence() -> None:
    assert EventsSettings().wake_mode == "cadence"


def test_settings_accept_event_wake_mode() -> None:
    assert EventsSettings(wake_mode="event").wake_mode == "event"


def test_settings_refuse_unknown_wake_mode() -> None:
    with pytest.raises(ValidationError):
        EventsSettings(wake_mode="live")
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
