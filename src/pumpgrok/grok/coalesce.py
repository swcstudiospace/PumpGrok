"""In-flight coalescing (GRK-04).

N identical concurrent requests share one transport call: the first runs the
factory, the rest await the same future. Distinct keys never share.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class Coalescer:
    def __init__(self) -> None:
        self._in_flight: dict[str, asyncio.Future[T]] = {}

    async def run(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        if key in self._in_flight:
            return await self._in_flight[key]
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        self._in_flight[key] = future
        try:
            result = await factory()
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
            raise
        else:
            if not future.done():
                future.set_result(result)
            return result
        finally:
            self._in_flight.pop(key, None)

    @property
    def in_flight(self) -> int:
        return len(self._in_flight)
