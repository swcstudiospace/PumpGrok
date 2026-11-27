"""Paper start gate (ONB-03, T-14-08-04).

Paper start refuses until required paper inputs are present and every
enabled seat has a recorded operator access decision. No grant by default.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pumpgrok.onboarding.access import enabled_seats_without_access
from pumpgrok.onboarding.doctor_report import doctor_records, failing_records

DEFAULT_ACCESS_PATH = Path("var/desk/access-decisions.jsonl")
DEFAULT_SEATS: tuple[str, ...] = ("bot-01-scout", "bot-02-risk", "bot-06-exit")


def check_start(
    env: Mapping[str, str],
    mode: str,
    access_path: Path | None = None,
    seats: tuple[str, ...] = DEFAULT_SEATS,
) -> list[str]:
    """Missing input names for `mode`. Empty means the desk may start."""
    path = access_path if access_path is not None else DEFAULT_ACCESS_PATH
    missing = [record.name for record in failing_records(doctor_records(env, mode))]
    if mode == "paper":
        missing.extend(enabled_seats_without_access(path, seats))
        if not enabled_seats_without_access(path, seats):
            missing = [name for name in missing if name != "seat_tool_access"]
    return missing
