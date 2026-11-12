"""Injected entry policy: BUY curve reads are bound to one source object.

The adapter asks the policy before and after every awaited BUY read. A replaced
source, a class outside the supported set, a refused snapshot or a read error all
deny the entry. Sells and flatten never consult the policy, so protective exits
stay available. The policy never signs, never sends and never moves funds.

Replay provenance is granted only by a :class:`VerifiedReplay` token minted by
``verify_replay``. Without the token a bound policy still checks source identity,
but its curve reads carry no verified provenance and every BUY is refused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pumpgrok.tools.onchain.curve_layout import CurveProvenance, rpc_curve_price_allowed

if TYPE_CHECKING:
    from pumpgrok.execution.paper_adapter.models import CurveSnapshot
    from pumpgrok.execution.paper_factory import VerifiedReplay

__all__ = [
    "BoundEntryPolicy",
    "EntryDenied",
    "EntryPolicy",
    "bound_replay_source",
    "entry_provenance",
]


class EntryDenied(Exception):
    """An entry read was refused; ``detail`` is the operator-facing reason."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class EntryPolicy(Protocol):
    """Typed entry authority the adapter consults around each BUY read."""

    def check_source(self, source: object | None) -> str | None:
        """Refusal detail when ``source`` is not the bound, supported object; None admits."""

    def check_snapshot(self, snapshot: CurveSnapshot) -> str | None:
        """Refusal detail for an entry snapshot; None admits it."""


class BoundEntryPolicy:
    """Entry policy bound to one source object and the exact classes it may be.

    Membership is by exact type, so a subclass of a supported class is refused.
    Construction fails closed when the bound object is not itself supported.

    Provenance is per instance: only a policy built with ``replay`` (the
    ``VerifiedReplay`` token whose ``curves`` is this source) admits snapshots as
    verified replay. A policy built without the token admits nothing.
    """

    __slots__ = ("_bound", "_provenance", "_supported")

    def __init__(
        self,
        source: object,
        *,
        supported: tuple[type, ...],
        replay: VerifiedReplay | None = None,
    ) -> None:
        if not supported:
            raise ValueError("entry policy needs at least one supported source class")
        self._supported = frozenset(supported)
        if type(source) not in self._supported:
            raise ValueError(f"unsupported entry source {type(source).__qualname__}")
        if replay is None:
            self._provenance = CurveProvenance.UNKNOWN
        else:
            # Lazy: the factory imports this module at load time.
            from pumpgrok.execution.paper_factory import VerifiedReplay

            if not isinstance(replay, VerifiedReplay) or replay.curves is not source:
                raise ValueError("entry policy replay token does not bind this source")
            self._provenance = CurveProvenance.VERIFIED_REPLAY
        self._bound = source

    @property
    def source(self) -> object:
        """The one source object this policy admits reads from."""
        return self._bound

    @property
    def provenance(self) -> CurveProvenance:
        """VERIFIED_REPLAY only when constructed from a verify_replay token."""
        return self._provenance

    def check_source(self, source: object | None) -> str | None:
        if source is not self._bound:
            return "entry source replaced or absent"
        if type(source) not in self._supported:
            return f"unsupported entry source {type(source).__qualname__}"
        return None

    def check_snapshot(self, snapshot: CurveSnapshot) -> str | None:
        if not rpc_curve_price_allowed(curve_source=snapshot.source, provenance=self._provenance):
            return f"curve layout {snapshot.source} reads are ASSUMED"
        return None


def bound_replay_source(policy: EntryPolicy | None) -> object | None:
    """The replay curve source a verified policy is bound to; None otherwise."""
    if (
        isinstance(policy, BoundEntryPolicy)
        and policy.provenance is CurveProvenance.VERIFIED_REPLAY
    ):
        return policy.source
    return None


def entry_provenance(policy: EntryPolicy | None, snapshot: CurveSnapshot) -> CurveProvenance:
    """Provenance of a BUY snapshot, from how its read was bound.

    A verified policy admitted this read through its source identity checks
    (:meth:`BoundEntryPolicy.check_source` before and after the await), so the
    read is verified replay. Otherwise nothing establishes replay: the snapshot's
    own label decides between a live RPC read, a non-replay fixture, or unknown.
    """
    if bound_replay_source(policy) is not None:
        return CurveProvenance.VERIFIED_REPLAY
    if snapshot.source == "rpc":
        return CurveProvenance.LIVE_RPC
    if snapshot.source == "fixture":
        return CurveProvenance.UNVERIFIED_FIXTURE
    return CurveProvenance.UNKNOWN
