"""Usage errors, parser base and JSON error envelopes."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, NoReturn, TextIO

from pumpgrok.cli.codes import (
    _EXIT_BY_CODE,
    EXIT_CONFIG,
    EXIT_NOT_IMPLEMENTED,
    FORBIDDEN_OWNERS,
)

log = logging.getLogger("pumpgrok.cli")


class UsageError(Exception):
    """A malformed command line. Exit 1, never argparse's 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def _say(stream: TextIO, *lines: str) -> None:
    for line in lines:
        stream.write(line + "\n")


def _exit_for_code(code: str) -> int:
    """Map a tool error code to the CLI exit contract (docstring); unknown codes exit 1."""
    return _EXIT_BY_CODE.get(code, EXIT_CONFIG)


def _tool_error(verb: str, code: str, message: str) -> int:
    """Print the JSON error envelope (T-03-07-03: code+message only) with the mapped exit."""
    _say(sys.stdout, json.dumps({"ok": False, "code": code, "message": message}))
    _say(sys.stderr, f"{verb} failed: {code}: {message}")
    return _exit_for_code(code)


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
