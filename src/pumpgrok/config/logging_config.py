"""Log config: PUMPGROK_LOG_LEVEL validation and JSON logging in every profile (HOST-08)."""

from __future__ import annotations

import os

from pumpgrok.config.settings import LOG_LEVELS, valid_log_level
from pumpgrok.logging.json import setup_logging


def log_level_from_env(environ: dict[str, str] | None = None) -> str:
    """Validated level from PUMPGROK_LOG_LEVEL; defaults to INFO."""
    env = os.environ if environ is None else environ
    raw = (env.get("PUMPGROK_LOG_LEVEL") or "").strip()
    if not raw:
        return "INFO"
    if not valid_log_level(raw):
        raise ValueError(f"PUMPGROK_LOG_LEVEL must be one of: {', '.join(LOG_LEVELS)}")
    return raw


def setup_hosted_logging(*, mode: str = "paper", profile: str = "paper") -> str:
    """Configure JSON logging in every profile; returns the active level."""
    level = log_level_from_env()
    setup_logging(mode=mode, profile=profile)
    return level
