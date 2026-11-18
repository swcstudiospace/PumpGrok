"""Live-data paper composition root (MKT-09, criterion 10).

:func:`build_live_paper_root` is the one composition of the live-data paper path: a
read-only boundary over an injected transport, the curve bridge feeding the exact
:class:`LivePriceSource`, and the paper adapter bound to that source by identity. The
path can read live curves and price paper fills. It cannot sign or send anything: this
module holds no signing or sending symbol, and the import graph guard keeps the live
adapter out of its closure.

Refusals come first and do no I/O: a mode other than ``"paper"``, then an absent or
empty endpoint. There is no default endpoint; the owner names one at deployment (owner
decision 4). The transport is injected, and this module opens no socket.

ATA rent (FEE-01): with ``rent_rpc`` the rent-exempt minimum is read from RPC once at build time
(:func:`read_ata_rent`); a failed read fails the build. Without it the recorded offline pin
(:data:`PAPER_DEFAULT_FEE_MODEL`) is used.
"""

from __future__ import annotations

from contextlib import ExitStack, closing
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol

from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.datafeed.bridge import ObservationBridge, build_observation_bridge
from pumpgrok.datafeed.price import LivePriceSource, ReservesCache
from pumpgrok.datafeed.readonly import ReadOnlyBoundary, ReadTransport
from pumpgrok.events.models import Event
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.execution.entry_hook import EntryGate
from pumpgrok.execution.fees import PAPER_DEFAULT_FEE_MODEL, FeeModel, read_ata_rent
from pumpgrok.execution.paper_adapter import PaperAdapter
from pumpgrok.execution.paper_factory import build_paper_adapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.live_recorder import LiveRecorder
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import killswitch_file
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.tools import RESERVES_CACHE_CAPACITY, ensure_paper_genesis

__all__ = ["LivePaperRoot", "build_live_paper_root"]

LEDGER_FILE = "ledger.sqlite"
CURSOR_FILE = "live-cursor.sqlite"
TICKS_DIR = "live-ticks"


async def _no_event_consumers(_event: Event) -> None:
    """The live-data root has no event consumers; curves reach it through the bridge."""


def _dead_letter(event: Event) -> None:
    """Refuse silently losing an event: a failed event stops the publish loudly."""
    raise RuntimeError(f"live-data paper root has no dead-letter sink for {event.kind}")


class RentRpc(Protocol):
    """The one JSON-RPC call the rent read makes. The caller owns the client.

    :class:`ReadOnlyBoundary` is not used here: its read allowlist does not admit
    ``getMinimumBalanceForRentExemption``.
    """

    async def call(self, method: str, params: list[Any]) -> Any: ...


@dataclass(frozen=True)
class LivePaperRoot:
    """The wired live-data paper path. Call :meth:`close` to release its stores."""

    boundary: ReadOnlyBoundary
    health: SourceSupervisor
    prices: LivePriceSource
    bridge: ObservationBridge
    risk: RiskEngine
    adapter: PaperAdapter
    fees: FeeModel
    store: LedgerStore

    def close(self) -> None:
        self.store.close()
        self.health.close()


async def build_live_paper_root(
    *,
    mode: str,
    endpoint: str,
    transport: ReadTransport,
    clock: Clock,
    rng_seed: int,
    data_dir: Path,
    budget: RiskBudget,
    limits: EngineLimits,
    max_age_s: float,
    max_observations: int,
    rent_rpc: RentRpc | None = None,
    entry_gate: EntryGate | None = None,
) -> LivePaperRoot:
    """Build the live-data paper root over a read-only ``endpoint`` and ``transport``.

    Raises ValueError, before any I/O, for a mode other than ``"paper"`` or an absent
    endpoint. ``endpoint`` has no default: the owner chooses it at deployment. The
    read-only boundary validates the endpoint's scheme and shape before any read.

    An RPC client in ``rent_rpc`` supplies the ATA rent: it is read once, here, with
    :func:`read_ata_rent`, and a failed or invalid read fails the build. Without it, the
    recorded offline pin (:data:`PAPER_DEFAULT_FEE_MODEL`) is used.
    """
    if mode != "paper":
        raise ValueError("live-data paper root builds in paper mode only")
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError("live-data paper root needs an explicit read-only endpoint")
    boundary = ReadOnlyBoundary(endpoint=endpoint, transport=transport)
    fees: FeeModel = PAPER_DEFAULT_FEE_MODEL
    if rent_rpc is not None:
        fees = await read_ata_rent(rent_rpc)

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    rng = make_rng(rng_seed)
    with ExitStack() as stack:
        cursor = SourceSupervisor(clock, rng, path=data_dir / CURSOR_FILE)
        health = stack.enter_context(closing(cursor))
        store = stack.enter_context(closing(LedgerStore(str(data_dir / LEDGER_FILE))))
        ensure_paper_genesis(store, budget)
        prices = LivePriceSource(
            clock=clock,
            health=health,
            max_age_s=max_age_s,
            max_observations=max_observations,
        )
        reserves = ReservesCache(capacity=RESERVES_CACHE_CAPACITY)
        bridge = build_observation_bridge(
            clock=clock,
            handler=_no_event_consumers,
            dlq=_dead_letter,
            recorder=LiveRecorder(data_dir / TICKS_DIR, clock=clock),
            price=prices,
        )
        risk = RiskEngine(
            store=store,
            budget=budget,
            ids=IdFactory(clock, rng),
            clock=clock,
            limits=limits,
            mode="paper",
            killswitch_path=killswitch_file(data_dir),
            get_reserves=reserves.get,
        )
        adapter = build_paper_adapter(
            SimpleNamespace(risk=budget, limits=limits),
            store=store,
            risk=risk,
            ids=IdFactory(clock, rng),
            clock=clock,
            rng=rng,
            live_source=prices,
            reserves_observer=reserves.observe,
            entry_gate=entry_gate,
            fees=fees,
            source="paper",
        )
        root = LivePaperRoot(
            boundary=boundary,
            health=health,
            prices=prices,
            bridge=bridge,
            risk=risk,
            adapter=adapter,
            fees=fees,
            store=store,
        )
        stack.pop_all()
    return root
