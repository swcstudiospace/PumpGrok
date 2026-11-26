"""Read-only ReadTransport double for the live-data paper root (test code only).

It records every frame it is handed and answers with canned read responses. A frame
whose method is outside the read allowlist is refused before it is recorded, so a
test can assert both that a send-like call never reaches the transport and that a
read does. It never opens a socket and holds no key material.
"""

from __future__ import annotations

READ_METHODS = frozenset(
    {
        "logsSubscribe",
        "getAccountInfo",
        "getTransaction",
        "subscribeNewToken",
        "subscribeMigration",
    }
)


class ReadOnlyDouble:
    """Canned, read-only transport: records accepted frames, refuses everything else."""

    def __init__(self) -> None:
        self.frames: list[tuple[str, dict[str, object]]] = []

    async def send(self, url: str, frame: dict[str, object]) -> object:
        if frame.get("method") not in READ_METHODS:
            raise PermissionError("double refuses a frame outside the read allowlist")
        self.frames.append((url, frame))
        return {"result": "fixture response"}
