"""One JSON object per log line, correlation-aware, and the single setup call (OBS-001, OBS-002).

Record shape: FOUNDATION_STACK 5.1. `correlation_id` is the ULID root or a `<ulid>.<n>` span,
bound by `core.ids.bind_correlation`; `seat` and `ticket_id` come from the contextvars below.
Keys are sorted and separators are compact, so each record is a canonical single line.

Text output is a development aid. `PUMPGROK_LOG_JSON=false` selects it only under the
`dev` profile; every other profile always emits JSON.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

from pumpgrok.core.ids import ambient_correlation
from pumpgrok.logging.redaction import STANDARD_ATTRS, RedactionFilter, redact_text

SEAT: ContextVar[str | None] = ContextVar("pumpgrok_seat", default=None)
TICKET: ContextVar[str | None] = ContextVar("pumpgrok_ticket", default=None)

# Extras promoted to top-level fields; every other extra goes to `data`.
PROMOTED_FIELDS = frozenset({"event", "correlation_id", "seat", "ticket_id", "mint", "duration_ms"})
TEXT_FORMAT = "%(asctime)s %(levelname)-7s %(name)-16s %(message)s"
HANDLER_MARK = "_pumpgrok_handler"


@contextmanager
def bind_seat(seat: str) -> Iterator[None]:
    token = SEAT.set(seat)
    try:
        yield
    finally:
        SEAT.reset(token)


@contextmanager
def bind_ticket(ticket_id: str) -> Iterator[None]:
    token = TICKET.set(ticket_id)
    try:
        yield
    finally:
        TICKET.reset(token)


def current_seat() -> str | None:
    return SEAT.get()


def _iso_millis(created: float) -> str:
    text = datetime.fromtimestamp(created, UTC).isoformat(timespec="milliseconds")
    return text.replace("+00:00", "Z")


class RedactingTextFormatter(logging.Formatter):
    """Dev text format. The whole rendered line passes through redaction, traceback included.

    Redacting only the message leaves ``exc_info`` unredacted: ``Formatter.format`` appends the
    formatted traceback, and a record's ``exc_text`` may already be cached raw by another handler.
    """

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


class JsonFormatter(logging.Formatter):
    """Render one record as a canonical single-line JSON object (FOUNDATION_STACK 5.1)."""

    def __init__(self, *, mode: str, profile: str) -> None:
        super().__init__()
        self._mode = mode
        self._profile = profile

    def format(self, record: logging.LogRecord) -> str:
        correlation = getattr(record, "correlation_id", None)
        if correlation is None:
            ambient = ambient_correlation()
            correlation = None if ambient is None else str(ambient)
        payload: dict[str, Any] = {
            "ts": _iso_millis(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "event": getattr(record, "event", None),
            "correlation_id": correlation,
            "seat": getattr(record, "seat", None) or SEAT.get(),
            "ticket_id": getattr(record, "ticket_id", None) or TICKET.get(),
            "mint": getattr(record, "mint", None),
            "mode": self._mode,
            "profile": self._profile,
            "data": self._data(record),
        }
        if hasattr(record, "duration_ms"):
            payload["duration_ms"] = record.duration_ms
        if record.exc_info and record.exc_info[0] is not None:
            exc_type, exc_value, _ = record.exc_info
            payload["exc"] = {
                "type": exc_type.__name__,
                "msg": redact_text(str(exc_value)),
                "stack": redact_text(self.formatException(record.exc_info)),
            }
        # default=str: a log line must always render. The ledger path is strict (canonical_json).
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _data(record: logging.LogRecord) -> dict[str, Any]:
        skipped = STANDARD_ATTRS | PROMOTED_FIELDS
        return {key: value for key, value in vars(record).items() if key not in skipped}


def setup_logging(
    *,
    mode: str,
    profile: str,
    environ: Mapping[str, str] | None = None,
    stream: TextIO | None = None,
) -> None:
    """Install the one handler on the root logger: redacted, JSON unless dev text is requested."""
    env = os.environ if environ is None else environ
    text_requested = env.get("PUMPGROK_LOG_JSON", "").strip().lower() == "false"
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.addFilter(RedactionFilter())
    if text_requested and profile == "dev":
        handler.setFormatter(RedactingTextFormatter(TEXT_FORMAT, datefmt="%H:%M:%S"))
    else:
        handler.setFormatter(JsonFormatter(mode=mode, profile=profile))
    root = logging.getLogger()
    for previous in [h for h in root.handlers if getattr(h, HANDLER_MARK, False)]:
        root.removeHandler(previous)
    setattr(handler, HANDLER_MARK, True)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
