"""Characterization: mint authority check (STRUCT-002).

Pins ``tools/onchain/authorities.py`` against ``tools/authority_check.py``
(root oracle, kept byte-identical per R53).

Divergence from the oracle (deliberate, see 02-RESEARCH.md Pitfall 5):
the output drops the ``rpc`` URL echo -- the endpoint URL must never leave
the client boundary (T-02-01). Method (``getAccountInfo``), params
(``[mint, {"encoding": "jsonParsed"}]``) and every other output key are
identical to ``check_mint``.

Ports 1 root unittest case (R55): ``test_authority_main_exits_nonzero_on_error``
(``tests/test_tools_cli.py:107``). The ported modules expose no ``main()``
(CLI verbs land in a later plan), so the non-zero-exit contract is pinned via
its exact predicate: an ``ok: False`` result.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import httpx
import pytest

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.onchain.authorities import check_mint
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "http"


def _body(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["http"]


def _client(handler: httpx.MockTransport | None, **kwargs) -> tuple[RpcClient, FixtureClock]:
    clock = FixtureClock()
    transport = (
        handler
        if handler is not None
        else httpx.MockTransport(
            lambda request: httpx.Response(200, json=_body("authority_ok.json"))
        )
    )
    http = httpx.AsyncClient(transport=transport)
    rpc = RpcClient(
        ["https://rpc.invalid"],
        http,
        clock,
        rng=random.Random(7),
        max_attempts_per_endpoint=1,
        **kwargs,
    )
    return rpc, clock


@pytest.mark.characterization
async def test_check_mint_ok() -> None:
    rpc, _ = _client(None)
    result = await check_mint("So11111111111111111111111111111111111111112", rpc)
    assert result == {
        "ok": True,
        "mint": "So11111111111111111111111111111111111111112",
        "mintAuthority": None,
        "freezeAuthority": None,
        "decimals": 9,
        "supply": "1000000000000000",
        "isInitialized": True,
        "extensions": [],
        "hasMintAuthority": False,
        "hasFreezeAuthority": False,
    }
    assert "rpc" not in result


@pytest.mark.characterization
async def test_check_mint_not_found_is_ok_false() -> None:
    """Root case port: ok False is the exact predicate main() exits non-zero on."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["method"] == "getAccountInfo"
        assert json.loads(request.content)["params"][1] == {"encoding": "jsonParsed"}
        return httpx.Response(200, json=_body("authority_not_found.json"))

    rpc, _ = _client(httpx.MockTransport(handler))
    result = await check_mint("NoSuchMint11111111111111111111111111111111", rpc)
    assert result["ok"] is False
    assert result["error"] == "Mint account not found or not a token mint"


class _RecordingClock:
    """Test double for the Clock protocol: records sleeps, never blocks."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def now(self) -> float:
        return 0.0

    def monotonic(self) -> float:
        return 0.0

    def utc_iso(self) -> str:
        return "1970-01-01T00:00:00.000000Z"

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def timeout(self, seconds: float):  # pragma: no cover - unused here
        raise NotImplementedError


@pytest.mark.characterization
async def test_retry_uses_injected_clock_and_seeded_wait() -> None:
    """Tenacity must sleep via the injected clock with rng-seeded delays."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": "flaky node"})
        return httpx.Response(200, json=_body("authority_ok.json"))

    clock: _RecordingClock = _RecordingClock()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    rng = random.Random(7)
    rpc = RpcClient(["https://rpc.invalid"], http, clock, rng=rng)  # type: ignore[arg-type]
    result = await check_mint("So11111111111111111111111111111111111111112", rpc)
    assert result["ok"] is True
    expected = random.Random(7)
    ceiling = 0.1
    assert clock.sleeps == [ceiling + expected.uniform(0, ceiling)]


@pytest.mark.characterization
async def test_failover_tries_endpoints_in_order() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "first.invalid" in str(request.url):
            return httpx.Response(500, json={"error": "down"})
        return httpx.Response(200, json=_body("authority_ok.json"))

    clock = FixtureClock()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    rpc = RpcClient(
        ["https://first.invalid", "https://second.invalid"],
        http,
        clock,
        rng=random.Random(7),
        max_attempts_per_endpoint=1,
    )
    result = await check_mint("So11111111111111111111111111111111111111112", rpc)
    assert result["ok"] is True
    assert [url.split("//")[1] for url in seen] == ["first.invalid", "second.invalid"]


@pytest.mark.characterization
async def test_errors_never_carry_url_or_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    clock = FixtureClock()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    rpc = RpcClient(
        ["https://secret.invalid"],
        http,
        clock,
        rng=random.Random(7),
        max_attempts_per_endpoint=1,
    )
    with pytest.raises(RpcError) as caught:
        await rpc.call("getAccountInfo", ["x"])
    assert "secret.invalid" not in str(caught.value)
