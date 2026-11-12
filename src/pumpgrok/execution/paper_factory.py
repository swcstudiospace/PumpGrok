"""Paper adapter composition: the one production construction boundary (13-03).

:func:`build_paper_adapter` is the only production path that builds a
:class:`PaperAdapter` with an entry policy. BUY entries need replay authority:
:func:`verify_replay` loads the dataset through the verifying loader and binds
the one :class:`FixtureCurveSource` built from that result. Every other
composition (no source, an injected source, a live source) installs a policy
that refuses each BUY read before it happens. Sells, flatten and protective
exits keep their curve reads.

This module never imports ``pumpgrok.execution.live`` and never signs or moves
funds. Time comes from the injected clock; money is integer lamports. Live
composition is not admitted here; plan 13-04 completes it.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.entry_hook import BoundEntryPolicy, EntryPolicy
from pumpgrok.execution.latency import P_DROP
from pumpgrok.execution.paper_adapter import PaperAdapter, PriceSource
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.fixtures import FixtureDataset, load_dataset
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.limits import EngineLimits

if TYPE_CHECKING:
    from pumpgrok.execution.paper_adapter import CurveSnapshot
    from pumpgrok.replay.sources import FixtureCurveSource

__all__ = ["VerifiedReplay", "build_paper_adapter", "verify_replay"]

# Module-private mint token: only verify_replay holds it, so a VerifiedReplay
# cannot be assembled by a caller that merely names the class.
_MINT: Final = object()


class VerifiedReplay:
    """Replay entry authority: one verified dataset and the curve source bound to it.

    Minted only by :func:`verify_replay`. Both attributes are read-only, so a
    caller cannot swap in a different curve source after verification.
    """

    __slots__ = ("_curves", "_dataset")

    def __init__(
        self, *, dataset: FixtureDataset, curves: FixtureCurveSource, _mint: object
    ) -> None:
        if _mint is not _MINT:
            raise ValueError("VerifiedReplay is minted only by verify_replay")
        self._dataset = dataset
        self._curves = curves

    @property
    def dataset(self) -> FixtureDataset:
        """The dataset that passed the verifying loader."""
        return self._dataset

    @property
    def curves(self) -> FixtureCurveSource:
        """The one curve source bound to the verified dataset."""
        return self._curves


class _NoReplayEntries:
    """Entry policy for compositions without replay authority: every BUY read is refused.

    It never reads the source, so no BUY can price from any curve. Sells and
    flatten never consult the entry policy.
    """

    __slots__ = ()

    def check_source(self, source: object | None) -> str | None:
        return "entry source has no verified replay binding"

    def check_snapshot(self, snapshot: CurveSnapshot) -> str | None:
        return "entry source has no verified replay binding"


def verify_replay(dataset_dir: str | Path, clock: Clock) -> VerifiedReplay:
    """Load ``dataset_dir`` through the verifying loader and bind its curve source.

    The loader checks every manifest digest and the event order before anything
    is built. A tampered dataset raises :class:`CorruptFixture`, and no authority
    exists for it.
    """
    # Lazy: replay.sources imports pumpgrok.execution.paper_adapter, so a
    # module-level import here would cycle through pumpgrok.execution.
    from pumpgrok.replay.sources import FixtureCurveSource

    dataset = load_dataset(Path(dataset_dir))
    curves = FixtureCurveSource(dataset, clock)
    return VerifiedReplay(dataset=dataset, curves=curves, _mint=_MINT)


def build_paper_adapter(
    settings: object,
    *,
    store: LedgerStore,
    risk: RiskEngine,
    ids: IdFactory,
    clock: Clock,
    rng: random.Random,
    price_source: PriceSource | None = None,
    replay: VerifiedReplay | None = None,
    source: Literal["paper", "replay", "manual"] = "paper",
    p_drop: float = P_DROP,
) -> PaperAdapter:
    """Build the production PaperAdapter. BUY entries need verified replay authority.

    With ``replay``, entries price only from ``replay.curves``, the exact object
    :func:`verify_replay` bound, and the ledger source must be ``"replay"``.
    Without it, ``price_source`` (if any) serves sells and reads only, and every
    BUY is refused with ``data_unavailable``. The operator risk budget and engine
    limits come from ``settings`` (``risk`` / ``limits``); objects without those
    attributes fall back to defaults.
    """
    policy: EntryPolicy
    if replay is None:
        policy = _NoReplayEntries()
    else:
        if source != "replay":
            raise ValueError("verified replay composes only the replay ledger source")
        if price_source is not None and price_source is not replay.curves:
            raise ValueError("price source is not the verified replay curve source")
        from pumpgrok.replay.sources import FixtureCurveSource

        policy = BoundEntryPolicy(replay.curves, supported=(FixtureCurveSource,))
        price_source = replay.curves
    budget = getattr(settings, "risk", None)
    if budget is None:
        budget = RiskBudget()
    limits = getattr(settings, "limits", None)
    if limits is None:
        limits = EngineLimits()
    return PaperAdapter(
        store=store,
        risk=risk,
        ids=ids,
        clock=clock,
        rng=rng,
        budget=budget,
        limits=limits,
        price_source=price_source,
        entry_policy=policy,
        source=source,
        p_drop=p_drop,
    )
