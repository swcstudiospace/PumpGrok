"""Injected entry policy: BUY curve reads are bound to one source object.

The adapter asks the policy before and after every awaited BUY read. A replaced
source, a class outside the supported set, a refused snapshot or a read error all
deny the entry. Sells and flatten never consult the policy, so protective exits
stay available. The policy never signs, never sends and never moves funds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pumpgrok.tools.onchain.curve_layout import rpc_curve_price_allowed

if TYPE_CHECKING:
    from pumpgrok.execution.paper_adapter.models import CurveSnapshot

__all__ = ["BoundEntryPolicy", "EntryDenied", "EntryPolicy"]


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
    """

    __slots__ = ("_bound", "_supported")

    def __init__(self, source: object, *, supported: tuple[type, ...]) -> None:
        if not supported:
            raise ValueError("entry policy needs at least one supported source class")
        self._supported = frozenset(supported)
        if type(source) not in self._supported:
            raise ValueError(f"unsupported entry source {type(source).__qualname__}")
        self._bound = source

    @property
    def source(self) -> object:
        """The one source object this policy admits reads from."""
        return self._bound

    def check_source(self, source: object | None) -> str | None:
        if source is not self._bound:
            return "entry source replaced or absent"
        if type(source) not in self._supported:
            return f"unsupported entry source {type(source).__qualname__}"
        return None

    def check_snapshot(self, snapshot: CurveSnapshot) -> str | None:
        if not rpc_curve_price_allowed(curve_source=snapshot.source):
            return f"curve layout {snapshot.source} reads are ASSUMED"
        return None
