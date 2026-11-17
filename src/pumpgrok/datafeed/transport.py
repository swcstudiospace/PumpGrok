"""Recording wrappers and the one socket factory for the live-data paper path.

Only this module opens a network socket. Callers receive a transport from
``make_read_transport`` or an async iterator from ``open_websocket``. Frames are
redacted before they are recorded: header values are dropped, and query
parameters named api-key, key or token are replaced with REDACTED.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping
from typing import Protocol

import httpx
from websockets.asyncio.client import connect

from pumpgrok.datafeed.readonly import ReadOnlyBoundary, ReadTransport, _validate_endpoint
from pumpgrok.replay.clock import Clock
from pumpgrok.replay.live_recorder import TRANSACTION_STREAM

_QUERY_RE = re.compile(r"(?i)(?P<name>api-key|token|(?<![A-Za-z_-])key)=(?P<value>[^&\s\"']*)")
# Header names and a nested headers object. Dropped whole so no header value is recorded.
_DROPPED_KEYS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "api-key",
        "x-api-key",
        "headers",
    }
)
_HTTP_TIMEOUT_S = 10.0
_WS_MAX_QUEUE = 16


class _FrameRecorder(Protocol):
    def record_frame(self, raw: dict[str, object]) -> None: ...


class _Pinnable(Protocol):
    def pin(self) -> None: ...

    def release(self) -> None: ...


def redact_text(text: str) -> str:
    """Replace api-key, key and token query values. The parameter name stays."""
    return _QUERY_RE.sub(lambda match: f"{match.group('name')}=REDACTED", text)


def redact(value: object) -> object:
    """Drop header values and redact secret query parameters in any nested string."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        cleaned: dict[object, object] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _DROPPED_KEYS:
                continue
            cleaned[key] = redact(item)
        return cleaned
    return value


def _object_payload(raw: object) -> dict[str, object]:
    """Decode one inbound frame to a JSON object, then redact it."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    decoded: object = json.loads(raw) if isinstance(raw, str) else raw
    redacted = redact(decoded)
    if not isinstance(redacted, dict):
        raise ValueError("websocket frame is not a JSON object")
    return redacted


class HttpxJsonRpc:
    """JSON-RPC POST over httpx. Constructed only by ``make_read_transport``."""

    async def send(self, url: str, frame: dict[str, object]) -> object:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S, trust_env=False) as client:
            response = await client.post(url, json=frame)
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("JSON-RPC response is not an object")
        return body


def make_read_transport(endpoint: str) -> ReadTransport:
    """The only socket factory. Validates the endpoint, then builds the HTTP transport."""
    _validate_endpoint(endpoint)
    return HttpxJsonRpc()


async def open_websocket(url: str, *, stream: str) -> AsyncIterator[object]:
    """Open one read-only websocket and yield each decoded inbound message.

    ``stream`` names the feed (portal or logs) so a test double can route frames.
    The real opener does not use it beyond requiring the caller to name the feed.
    """
    del stream
    _validate_endpoint(url)
    async with connect(url, proxy=None, max_queue=_WS_MAX_QUEUE) as socket:
        async for message in socket:
            yield message


class RecordingWebSocket:
    """Yield inbound frames only after ``record_frame`` has persisted each one.

    The clock is pinned across the yield, so the consumer can pump the frame and
    stamp its observation with the same ts the frame was recorded under. The pin
    releases when the consumer asks for the next frame.
    """

    def __init__(
        self,
        frames: AsyncIterator[object],
        recorder: _FrameRecorder,
        *,
        stream: str,
        clock: _Pinnable,
    ) -> None:
        self._frames = frames
        self._recorder = recorder
        self._stream = stream
        self._clock = clock

    def __aiter__(self) -> AsyncIterator[dict[str, object]]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[dict[str, object]]:
        async for raw in self._frames:
            payload = _object_payload(raw)
            self._clock.pin()
            try:
                self._recorder.record_frame({"stream": self._stream, "payload": payload})
                yield payload
            finally:
                self._clock.release()


class RecordingJsonRpc:
    """Read transport that records getTransaction responses before returning them.

    ``rpc`` and ``portal`` go through ``ReadOnlyBoundary``, which refuses any
    method outside its allowlist before the inner transport is called. A
    getTransaction response is recorded as a transaction frame
    ``{signature, response}`` so a rebuild can answer that read from the feed.
    Other allowlisted methods are not feed frames: a rebuild refuses unknown
    streams, and a subscribe response does not produce an observation.
    """

    def __init__(
        self,
        endpoint: str,
        transport: ReadTransport,
        recorder: _FrameRecorder | None,
        clock: Clock,
    ) -> None:
        del clock
        self._inner = transport
        self._recorder = recorder
        self._boundary = ReadOnlyBoundary(endpoint=endpoint, transport=self)

    async def send(self, url: str, frame: dict[str, object]) -> object:
        response = await self._inner.send(url, frame)
        self._record_transaction(frame, response)
        return response

    async def rpc(self, method: str, params: list[object]) -> object:
        return await self._boundary.rpc(method, params)

    async def portal(self, method: str) -> object:
        return await self._boundary.portal(method)

    def _record_transaction(self, frame: Mapping[str, object], response: object) -> None:
        if self._recorder is None or frame.get("method") != "getTransaction":
            return
        params = frame.get("params")
        signature = params[0] if isinstance(params, list) and params else None
        if not isinstance(signature, str) or not isinstance(response, dict):
            return
        self._recorder.record_frame(
            {
                "stream": TRANSACTION_STREAM,
                "payload": {"signature": signature, "response": response},
            }
        )
