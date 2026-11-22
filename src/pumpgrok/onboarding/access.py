"""Seat tool-access approvals (ONB-04, T-14-08-03).

Grants exist only as operator-choice ledger rows in the access-decisions
file. Default is no grant. Rows carry presence and source, never secrets.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.core.idempotency import canonical_json


def record_access(path: Path, seat: str) -> None:
    """Append one operator-choice grant row for `seat`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"seat": seat, "source": "operator-choice", "granted": True}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(row) + "\n")


def has_access(path: Path, seat: str) -> bool:
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if seat in line and "granted" in line and "true" in line:
            return True
    return False


def enabled_seats_without_access(path: Path, seats: tuple[str, ...]) -> list[str]:
    """Names of enabled seats without a recorded access decision."""
    return [seat for seat in seats if not has_access(path, seat)]
