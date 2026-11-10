"""Temporary RED interface for the held-position marking scheduler.

This interface is deliberately nonfunctional and must be replaced in GREEN.
"""

from pumpgrok.core.ids import Clock
from pumpgrok.datafeed.graduation import GapSettings
from pumpgrok.execution.paper_adapter import PaperAdapter


class HeldMarkScheduler:
    def __init__(
        self,
        *,
        adapter: PaperAdapter,
        clock: Clock,
        settings: GapSettings,
        max_observations: int,
    ) -> None:
        pass

    async def holdings_changed(self) -> None:
        """Reconcile the schedule with the adapter's current ledger positions."""

    async def close(self) -> None:
        """Cancel the scheduler and release its timer."""
