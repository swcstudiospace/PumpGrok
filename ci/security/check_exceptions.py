"""SEC-005 exceptions gate: every SECURITY.md exception row must be fresh.

The Exceptions table in SECURITY.md has columns
``Check | Fingerprint | Reason | Owner | Expiry (ISO)`` and starts empty: no
check is pre-listed, only genuinely failing ones with a fingerprint, a reason,
an owner and an ISO expiry date. An expired (or malformed) row fails this
check, which the guard suite in ci/tests/test_security_workflows.py enforces,
so an expired exception fails CI instead of silently lingering.
"""

from __future__ import annotations

import datetime as _datetime
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_MD = REPO_ROOT / "SECURITY.md"
SECTION = "## Exceptions"
EXPECTED_COLUMNS = ("Check", "Fingerprint", "Reason", "Owner", "Expiry (ISO)")


def _section_lines(text: str) -> list[str]:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == SECTION)
    except StopIteration:
        return []
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    return body


def check_text(text: str, today: _datetime.date) -> list[str]:
    """Return one error string per problem; empty means the table is valid."""
    body = _section_lines(text)
    rows = [line for line in body if line.strip().startswith("|")]
    if len(rows) < 2:
        return ["SECURITY.md Exceptions table is missing (want header plus separator)"]
    header = [cell.strip() for cell in rows[0].strip().strip("|").split("|")]
    if tuple(header) != EXPECTED_COLUMNS:
        return [f"SECURITY.md Exceptions header is {header!r}, want {list(EXPECTED_COLUMNS)!r}"]
    errors: list[str] = []
    for lineno, row in enumerate(rows[2:], start=3):
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if len(cells) != len(EXPECTED_COLUMNS):
            errors.append(f"Exceptions row {lineno} has {len(cells)} cells, want 5")
            continue
        check, _fingerprint, _reason, _owner, expiry = cells
        if not all(cells):
            errors.append(f"Exceptions row {lineno} ({check or '?'}) has an empty column")
            continue
        try:
            expires = _datetime.date.fromisoformat(expiry)
        except ValueError:
            errors.append(f"Exceptions row {lineno} ({check}) expiry {expiry!r} is not ISO")
            continue
        if expires < today:
            errors.append(f"Exceptions row {lineno} ({check}) expired {expiry}")
    return errors


def main() -> int:
    try:
        text = SECURITY_MD.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read {SECURITY_MD}: {exc}")
        return 1
    errors = check_text(text, _datetime.date.today())
    if errors:
        for error in errors:
            print(f"exceptions gate failed: {error}")
        return 1
    print("exceptions gate passed: no expired rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
