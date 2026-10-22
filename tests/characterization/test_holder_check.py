"""Characterization: top-holder snapshot (STRUCT-002).

Pins ``tools/onchain/holders.py`` against the retired ``holder_check``
root oracle (kept byte-identical per R53).

Divergence from the oracle (deliberate): the output drops the ``rpc`` URL
echo -- the endpoint URL must never leave the client boundary (T-02-01).
Method (``getTokenLargestAccounts``), the concentration math and the
sampled-only ``note`` string are byte-identical to ``holder_snapshot``.

Ports 1 root unittest case (R55): ``test_holder_main_exits_nonzero_on_error``
(root-oracle class retired in 05-08). The ported modules expose no ``main()``
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
from pumpgrok.tools.onchain.holders import holder_snapshot
from pumpgrok.tools.onchain.rpc import RpcClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "http"


def _body(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["http"]


@pytest.mark.characterization
async def test_holder_snapshot_concentration() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["method"] == "getTokenLargestAccounts"
        return httpx.Response(200, json=_body("holders.json"))

    rpc = RpcClient(
        ["https://rpc.invalid"],
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        FixtureClock(),
        rng=random.Random(7),
        max_attempts_per_endpoint=1,
    )
    result = await holder_snapshot("MintMintMintMintMintMintMintMintMintMintMint", rpc)
    assert result["ok"] is True
    assert result["holderCountReturned"] == 5
    assert result["totalUiAmountSampled"] == 1000.0
    assert result["top1Pct"] == 60.0
    assert result["top5Pct"] == 100.0
    assert result["top10Pct"] == 100.0
    assert result["holders"][0]["address"] == "Holder1111111111111111111111111111111111111"
    assert result["note"] == (
        "Percentages are of the sampled largest accounts only. "
        "LP and locked tokens are not auto-excluded. "
        "Cross-check with Solscan / gmgn for production decisions."
    )
    assert "rpc" not in result


@pytest.mark.characterization
async def test_holder_empty_value_is_ok_false() -> None:
    """Root case port: ok False is the exact predicate main() exits non-zero on."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"value": []}})

    rpc = RpcClient(
        ["https://rpc.invalid"],
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        FixtureClock(),
        rng=random.Random(7),
        max_attempts_per_endpoint=1,
    )
    result = await holder_snapshot("MintMintMintMintMintMintMintMintMintMintMint", rpc)
    assert result["ok"] is False
