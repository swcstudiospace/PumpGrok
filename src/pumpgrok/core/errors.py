"""Core error classes (interfaces.md 2.2)."""

from __future__ import annotations

from typing import Any, ClassVar


class PumpgrokError(Exception):
    """Base class. `code` is stable and machine-readable; it is what the journal stores."""

    code: ClassVar[str] = "pumpgrok_error"

    def __init__(self, message: str, **fields: Any) -> None:
        super().__init__(message)
        self.message = message
        self.fields: dict[str, Any] = fields


class PermissionDenied(PumpgrokError):
    """Registry refused to hand a tool to a bot (not in roster, or side effect too high)."""

    code = "permission_denied"


class LiveGateError(PermissionDenied):
    """A live-write path was reached. Always raised; never caught by trading code."""

    code = "live_gate"


class ToolTimeout(PumpgrokError):
    code = "tool_timeout"


class ToolRateLimited(PumpgrokError):
    code = "tool_rate_limited"


class LedgerUnavailable(PumpgrokError):
    code = "ledger_unavailable"


class DataStale(PumpgrokError):
    code = "data_stale"


class NotYetImplemented(PumpgrokError):
    """A backend that Phase 4 has not built yet (PaperAdapter, RiskEngine).

    Tools wired to such a backend let this propagate: the CLI prints the JSON
    error envelope and exits 5 (binding B5). It is never a fake fill/quote.
    """

    code = "not_yet_implemented"


class DataBlind(PumpgrokError):
    """No price for longer than the blind window; the position uses last_good marks."""

    code = "data_blind"


class ReplayMissingRecord(PumpgrokError):
    """Replay asked for an LLM outcome the fixture does not record. Fail, never invent."""

    code = "replay_missing_record"


class OrderRejectedError(Exception):
    """A paper order was refused; the refusal is on the ledger.

    Lives here (not in the execution package) so both the adapter and the
    exec tools can import it without a package cycle. Re-exported from
    ``pumpgrok.execution.paper_adapter`` for existing importers.
    """

    def __init__(
        self, reason: str, detail: str = "", *, stage: str, fees_lamports: int = 0
    ) -> None:
        super().__init__(f"{reason} at {stage}: {detail}")
        self.reason = reason
        self.detail = detail
        self.stage = stage
        self.fees_lamports = fees_lamports


class OrderUnknownError(OrderRejectedError):
    """Confirmation timed out: outcome UNKNOWN, never resubmitted.

    The `OrderPlaced` row persists with no outcome row; a repeat with the
    same decision returns this same error (single-send rule, constitution 3).
    """
