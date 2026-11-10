"""Event-package errors. Messages name an index or a path constant, never a payload."""

from __future__ import annotations

from pumpgrok.core.errors import PumpgrokError


class PoisonEvent(PumpgrokError):
    """A handler rejected the event as poison. The index is the only detail."""

    code = "event_poison"

    def __init__(self, *, index: int) -> None:
        super().__init__(f"poison event at index {index}")


class TransientEvent(PumpgrokError):
    """A handler failed in a way a later plan may retry. The index is the only detail."""

    code = "event_transient"

    def __init__(self, *, index: int) -> None:
        super().__init__(f"transient event at index {index}")


class SidecarRefusal(PumpgrokError):
    """The sidecar path or a row index was refused. No payload is included."""

    code = "sidecar_refusal"

    def __init__(self, *, index: int | None = None, path_name: str = "EVENTS_SIDECAR_PATH") -> None:
        if index is None:
            super().__init__(f"sidecar refused path {path_name}")
        else:
            super().__init__(f"sidecar refused index {index}")


class EventBusClosed(PumpgrokError):
    """publish() or start() after shutdown() began. The bus accepts no new work."""

    code = "event_bus_closed"

    def __init__(self) -> None:
        super().__init__("event bus is closed")
