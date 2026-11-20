"""Event catalog and typed errors. Importing this package opens no store and no socket."""

from pumpgrok.events.errors import PoisonEvent, SidecarRefusal, TransientEvent
from pumpgrok.events.models import Event, EventKind, priority_of

__all__ = [
    "Event",
    "EventKind",
    "PoisonEvent",
    "SidecarRefusal",
    "TransientEvent",
    "priority_of",
]
