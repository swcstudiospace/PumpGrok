# Temporary typed read-only boundary for the Task 2 RED only.
from typing import Protocol


class ReadTransport(Protocol):
    async def send(self, url: str, frame: dict[str, object]) -> object: ...


class ReadOnlyBoundary:
    def __init__(self, *, endpoint: str, transport: ReadTransport) -> None:
        self.endpoint = endpoint
        self.transport = transport

    async def rpc(self, method: str, params: list[object]) -> object:
        return None

    async def portal(self, method: str) -> object:
        return None
