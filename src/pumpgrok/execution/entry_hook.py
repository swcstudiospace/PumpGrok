"""Entry-gate hook on exec.place (FEE-01, V4-12, T-13-03c).

Enforces, on buys only, the ``rpc_curve_price_allowed`` allowlist and the
graduation refusal. Exit and flatten sells pass through untouched.
"""

from __future__ import annotations

from pumpgrok.datafeed.graduation import entry_refused
from pumpgrok.risk.entry_checks import EntryChecks, MintFacts
from pumpgrok.tools.onchain.curve_layout import rpc_curve_price_allowed

class EntryRefusedError(ValueError):
    """A buy was refused by the entry gate; sells never raise this."""

    code = "entry_refused"

class EntryHook:
    """Stateless entry gate consulted before a buy fill."""

    def check_place(
        self,
        *,
        side: str,
        curve_source: str,
        complete: bool = False,
        entry_checks: EntryChecks | None = None,
        mint_facts: MintFacts | None = None,
    ) -> None:
        """Raise EntryRefusedError for a gated buy; pass through otherwise.

        When ``entry_checks`` and ``mint_facts`` are supplied, the Phase 17
        fail-closed entry checks run after the allowlist and graduation
        refusals and before any order reaches the adapter. With them
        absent the pre-existing hook behaviour is unchanged.
        """
        if side != "buy":
            return
        if not rpc_curve_price_allowed(curve_source=curve_source):
            raise EntryRefusedError(f"entry refused: source {curve_source!r} is not allowed")
        if entry_refused(complete=complete):
            raise EntryRefusedError("entry refused: curve is complete")
        if entry_checks is not None and mint_facts is not None:
            refusal = entry_checks.check(mint_facts)
            if refusal is not None:
                raise EntryRefusedError(f"entry refused: {refusal}")
