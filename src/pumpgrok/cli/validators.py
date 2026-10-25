"""CLI argument validators and small shared helpers."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pumpgrok.cli.codes import _BASE58, APPROVAL_RE, TICKET_RE
from pumpgrok.cli.errors import UsageError
from pumpgrok.core.ids import mint_approval_id
from pumpgrok.core.units import sol_to_lamports
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.replay.clock import WallClock
from pumpgrok.risk.killswitch import SEAT_RE

log = logging.getLogger("pumpgrok.cli")


def _ticket(value: str) -> str:
    if not TICKET_RE.fullmatch(value):
        raise UsageError(f"bad --ticket {value!r}: want SOL-YYYYMMDD-NNN")
    return value


def _mint(value: str) -> str:
    if not 32 <= len(value) <= 44 or any(char not in _BASE58 for char in value):
        raise UsageError("bad --mint: want 32-44 base58 characters")
    return value


def _size_sol(value: str) -> Decimal:
    """Parse --size-sol once, at the CLI boundary (R28): Decimal in, lamports out."""
    try:
        size = Decimal(value)
        valid = size.is_finite() and size > 0
    except InvalidOperation:
        valid = False
    if not valid:
        raise UsageError(f"bad --size-sol {value!r}: want a positive number") from None
    return size


def _slippage_bps(value: str) -> int:
    try:
        bps = int(value)
    except ValueError:
        raise UsageError(f"bad --slippage-bps {value!r}: want 0-10000") from None
    if not 0 <= bps <= 10000:
        raise UsageError(f"bad --slippage-bps {value!r}: want 0-10000")
    return bps


def _approval_id(value: str) -> str:
    if not APPROVAL_RE.fullmatch(value):
        raise UsageError("bad --approval-id: want apr-<26 char ULID>")
    return value


def size_sol_to_lamports(size_sol: Decimal) -> int:
    """Convert a SOL size to lamports once, here, so every path shares one rounding."""
    return sol_to_lamports(size_sol)


def _human_by(value: str | None, verb: str) -> str:
    """Validate human attribution (R22): ``human:<name>``, never a seat id."""
    if (
        value is None
        or not value.startswith("human:")
        or SEAT_RE.match(value.removeprefix("human:"))
    ):
        raise UsageError(f"bad --by {value!r} for `{verb}`: want human:<name>")
    return value


def _mint_approval_id() -> str:
    """Mint one ``apr-<ULID>`` id for a CLI-recorded approval (R29).

    Thin wrapper over :func:`pumpgrok.core.ids.mint_approval_id`, the
    single OS-entropy root for approval ids (INT-05, D-06).
    """
    return mint_approval_id()


def _utc_now() -> datetime:
    """Current wall time for CLI verbs (replay paths inject FixtureClock instead)."""
    return datetime.fromtimestamp(WallClock().now(), UTC)


def _jsonable(value: Any) -> Any:
    """Coerce a settings dump to canonical_json input: floats become repr strings."""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _report_date(raw: str | None, flag: str) -> str:
    """YYYY-MM-DD for a report flag; today (UTC) when omitted. Refuses non-dates."""
    if raw is None:
        return _utc_now().strftime("%Y-%m-%d")
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise UsageError(f"bad {flag} {raw!r}: want a real date YYYY-MM-DD") from exc


def _ledger_id_or_none() -> str:
    """Ledger id for the confirmation record, read-only; "none" when absent."""
    ledger = Path.cwd() / PAPER_LEDGER_PATH
    if not ledger.exists():
        return "none"
    try:
        uri = f"file:{ledger.resolve().as_posix()}?mode=ro"
        db = sqlite3.connect(uri, uri=True)
        try:
            row = db.execute("SELECT value FROM meta WHERE key = 'ledger_id'").fetchone()
        finally:
            db.close()
    except sqlite3.Error:
        return "none"
    return str(row[0]) if row else "none"
