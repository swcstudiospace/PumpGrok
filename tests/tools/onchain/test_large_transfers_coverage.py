"""onchain.large_transfers coverage: RPC lookup failures are never silent.

A scan where no transaction could be read after a lookup failed raises
``DataStale``; a scan where some lookups failed reports ``coverage == "partial"``;
a fully successful scan reports ``coverage == "complete"`` and returns its
transfers unchanged. No live network: every RPC call goes through one
``httpx.MockTransport`` handler.
"""

from __future__ import annotations

import json
import random
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import httpx
import pytest

from pumpgrok.core.errors import DataStale
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.onchain.large_transfers import LargeTransfersIn, run_large_transfers
from pumpgrok.tools.onchain.rpc import RpcClient

START = 1469918176.385
MINT = "So11111111111111111111111111111111111111112"
W1 = "7" * 44
W2 = "6" * 44
R1 = "5" * 44
SUPPLY = 100_000_000


def _sell_tx(wallet: str, block_time: int) -> dict[str, Any]:
    """Wallet drains 1,000,000 units (1% of supply) and gains SOL: a qualifying sell."""
    return {
        "blockTime": block_time,
        "meta": {
            "err": None,
            "preBalances": [1000, 0],
            "postBalances": [1010, 0],
            "preTokenBalances": [
                {"accountIndex": 0, "mint": MINT, "uiTokenAmount": {"amount": "1000000"}},
            ],
            "postTokenBalances": [
                {"accountIndex": 0, "mint": MINT, "uiTokenAmount": {"amount": "0"}},
                {"accountIndex": 1, "mint": MINT, "uiTokenAmount": {"amount": "1000000"}},
            ],
        },
        "transaction": {"message": {"accountKeys": [{"pubkey": wallet}, {"pubkey": R1}]}},
    }


def _rpc_error(body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32005, "message": "down"}},
    )


def _rpc(
    *,
    sigs_by_wallet: dict[str, list[dict[str, Any]]],
    txs: dict[str, dict[str, Any]],
    fail_sigs: frozenset[str] = frozenset(),
    fail_txs: frozenset[str] = frozenset(),
) -> RpcClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        method, params = body["method"], body["params"]
        if method == "getTokenSupply":
            result: Any = {"context": {"slot": 9}, "value": {"amount": str(SUPPLY), "decimals": 6}}
        elif method == "getSignaturesForAddress":
            if params[0] in fail_sigs:
                return _rpc_error(body)
            result = sigs_by_wallet.get(params[0], [])
        elif method == "getTransaction":
            if params[0] in fail_txs:
                return _rpc_error(body)
            result = txs[params[0]]
        else:
            raise AssertionError(f"unexpected method {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    return RpcClient(
        ["https://rpc.invalid"], client, FixtureClock(start=START), rng=random.Random(6)
    )


def _input(*wallets: str) -> LargeTransfersIn:
    return LargeTransfersIn(mint=MINT, wallets=list(wallets))


async def test_total_signature_failure_raises_data_stale() -> None:
    rpc = _rpc(sigs_by_wallet={}, txs={}, fail_sigs=frozenset({W1, W2}))
    with pytest.raises(DataStale) as info:
        await run_large_transfers(_input(W1, W2), rpc)
    assert "failed_lookups=2" in info.value.message


async def test_every_transaction_failing_raises_data_stale() -> None:
    rpc = _rpc(
        sigs_by_wallet={W1: [{"signature": "s1", "blockTime": 1000}]},
        txs={"s1": _sell_tx(W1, 1000)},
        fail_txs=frozenset({"s1"}),
    )
    with pytest.raises(DataStale):
        await run_large_transfers(_input(W1), rpc)


async def test_partial_wallet_failure_reports_incomplete_coverage() -> None:
    rpc = _rpc(
        sigs_by_wallet={W2: [{"signature": "s2", "blockTime": 2000}]},
        txs={"s2": _sell_tx(W2, 2000)},
        fail_sigs=frozenset({W1}),
    )
    out = await run_large_transfers(_input(W1, W2), rpc)
    assert out["coverage"] == "partial"
    assert [t["signature"] for t in out["transfers"]] == ["s2"]


async def test_partial_transaction_failure_keeps_readable_transfers() -> None:
    rpc = _rpc(
        sigs_by_wallet={W1: [{"signature": "s1", "blockTime": 1000}, {"signature": "s3"}]},
        txs={"s1": _sell_tx(W1, 1000)},
        fail_txs=frozenset({"s3"}),
    )
    out = await run_large_transfers(_input(W1), rpc)
    assert out["coverage"] == "partial"
    assert [t["signature"] for t in out["transfers"]] == ["s1"]


async def test_successful_scan_returns_transfers_unchanged() -> None:
    rpc = _rpc(
        sigs_by_wallet={
            W1: [{"signature": "s2", "blockTime": 2000}],
            W2: [{"signature": "s1", "blockTime": 1000}],
        },
        txs={"s1": _sell_tx(W2, 1000), "s2": _sell_tx(W1, 2000)},
    )
    out = await run_large_transfers(_input(W1, W2), rpc)
    assert out["coverage"] == "complete"
    assert [t["signature"] for t in out["transfers"]] == ["s1", "s2"]
    first = out["transfers"][0]
    assert first["from"] == W2
    assert first["to"] == R1
    assert first["amount_units"] == 1_000_000
    assert first["share"] == Decimal("0.01")
    assert first["kind"] == "sell"


async def test_successful_empty_scan_is_complete_not_stale() -> None:
    rpc = _rpc(sigs_by_wallet={W1: []}, txs={})
    out = await run_large_transfers(_input(W1), rpc)
    assert out["transfers"] == []
    assert out["coverage"] == "complete"
