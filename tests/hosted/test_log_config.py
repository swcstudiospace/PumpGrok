"""HOST-08: only DEBUG/INFO/WARNING/ERROR; JSON in every profile."""

from __future__ import annotations

import logging

from pumpgrok.config.logging_config import log_level_from_env, setup_hosted_logging
from pumpgrok.config.settings import collect_startup_problems
from pumpgrok.logging.json import JsonFormatter


def test_bad_level_refused_at_startup() -> None:
    problems = collect_startup_problems({"PUMPGROK_LOG_LEVEL": "VERBOSE"})
    assert any("PUMPGROK_LOG_LEVEL" in p for p in problems)


def test_four_levels_accepted() -> None:
    for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        assert log_level_from_env({"PUMPGROK_LOG_LEVEL": level}) == level


def test_bad_level_raises() -> None:
    try:
        log_level_from_env({"PUMPGROK_LOG_LEVEL": "trace"})
    except ValueError:
        return
    raise AssertionError("bad level must raise")


def test_json_logging_in_every_profile() -> None:
    for profile in ("paper", "dev", "live"):
        setup_hosted_logging(mode="paper", profile=profile)
        root = logging.getLogger()
        assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers), profile
