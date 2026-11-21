"""Entry-gate hook on exec.place (FEE-01, V4-12, T-13-03c).

Enforces, on buys only, the ``rpc_curve_price_allowed`` allowlist and the
graduation refusal. Exit and flatten sells pass through untouched.
"""

from __future__ import annotations

from pumpgrok.datafeed.graduation import entry_refused
from pumpgrok.tools.onchain.curve_layout import rpc_curve_price_allowed


class EntryRefusedError(ValueError):
    """A buy was refused by the entry gate; sells never raise this."""

    code = "entry_refused"


class EntryHook:
    """Stateless entry gate consulted before a buy fill."""

    def check_place(self, *, side: str, curve_source: str, complete: bool = False) -> None:
        """Raise EntryRefusedError for a gated buy; pass through otherwise."""
        if side != "buy":
            return
        if not rpc_curve_price_allowed(curve_source=curve_source):
            raise EntryRefusedError(f"entry refused: source {curve_source!r} is not allowed")
        if entry_refused(complete=complete):
            raise EntryRefusedError("entry refused: curve is complete")
