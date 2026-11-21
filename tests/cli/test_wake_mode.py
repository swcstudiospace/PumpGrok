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
        parser.parse_args(
            ["run", "--mode", "paper", "--once", "--wake-mode", "event"]
        ).wake_mode
        == "event"
    )


def test_unknown_mode_raises() -> None:
    with pytest.raises(ValueError):
        parse_wake_mode("hourly")


def test_valid_modes() -> None:
    assert parse_wake_mode("cadence") == "cadence"
    assert parse_wake_mode("event") == "event"
