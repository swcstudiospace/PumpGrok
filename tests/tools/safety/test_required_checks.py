"""safety.score_report: a required check left out of ``checks`` forces KILL (R-07).

A required check that the request omits was never evaluated, so it must force the
verdict to KILL exactly like a blind required check. Omitting only advisory checks
keeps the clean CLEAR verdict. MockTransport only.
"""

from __future__ import annotations

import base64
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.onchain.curve_layout import CURVE_ACCOUNT_SIZE, encode_curve_fixture
from pumpgrok.tools.onchain.rpc import RpcClient
from pumpgrok.tools.safety.checks import ADVISORY_IDS, CHECK_IDS, REQUIRED_IDS
from pumpgrok.tools.safety.score_report import ScoreReportIn, run_score_report

START = 1469918176.385
MINT = "So11111111111111111111111111111111111111112"
CURVE = "8" * 44
CREATOR = "9" * 44

_NOW = int(time.time())


def _curve_b64() -> str:
    raw = encode_curve_fixture(
        virtual_sol_reserves_lamports=30_000_000_000,
        virtual_token_reserves_units=1_000_000_000_000_000,
        real_sol_reserves_lamports=30_000_000_000,
        real_token_reserves_units=970_000_000_000_000,
        total_supply_units=1_000_000_000_000_000,
        complete=False,
    )
    assert len(raw) == CURVE_ACCOUNT_SIZE
    return base64.b64encode(raw).decode("ascii")


def _clean_handler(request: httpx.Request) -> httpx.Response:
    """Clean on-chain data: no authorities, no extensions, healthy holders and curve."""
    body = json.loads(request.content.decode("utf-8"))
    method, params = body["method"], body["params"]
    result: Any
    if method == "getAccountInfo":
        if params[1].get("encoding") == "jsonParsed":
            result = {
                "context": {"slot": 11},
                "value": {
                    "data": {
                        "parsed": {
                            "info": {
                                "mintAuthority": None,
                                "freezeAuthority": None,
                                "decimals": 6,
                                "supply": "1000000000000",
                                "isInitialized": True,
                                "extensions": [],
                            }
                        }
                    }
                },
            }
        else:
            result = {
                "context": {"slot": 7},
                "value": {
                    "data": [_curve_b64(), "base64"],
                    "executable": False,
                    "lamports": 1,
                    "owner": "o",
                    "rentEpoch": 1,
                },
            }
    elif method == "getTokenLargestAccounts":
        result = {
            "value": [
                {"address": "A" * 44, "uiAmount": 50.0, "decimals": 6},
                {"address": "B" * 44, "uiAmount": 30.0, "decimals": 6},
                {"address": "C" * 44, "uiAmount": 20.0, "decimals": 6},
            ]
        }
    elif method == "getTokenSupply":
        result = {"context": {"slot": 9}, "value": {"amount": "1000000000000", "decimals": 6}}
    elif method == "getSignaturesForAddress":
        result = [{"signature": "d1", "slot": 1, "blockTime": _NOW - 100}]
    else:
        raise AssertionError(f"unexpected method {method}")
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})


async def _score(payload: ScoreReportIn) -> dict[str, Any]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_clean_handler))
    rpc = RpcClient(["https://rpc.invalid"], client, FixtureClock(start=START), random.Random(9))
    try:
        return await run_score_report(payload, rpc)
    finally:
        await client.aclose()


def _payload(checks: list[str] | None) -> ScoreReportIn:
    return ScoreReportIn(mint=MINT, curve_account=CURVE, creator=CREATOR, checks=checks)


async def test_full_request_on_clean_data_is_clear() -> None:
    # Control: with every check requested, the same clean data is CLEAR.
    out = await _score(_payload(None))
    assert out["verdict_recommendation"] == "CLEAR"


@pytest.mark.parametrize("omitted", sorted(REQUIRED_IDS))
async def test_omitted_required_check_forces_kill(omitted: str) -> None:
    # Holds for every required id, including the SAFE-4/SAFE-8 holder pair: the
    # advisory amendment covers blind data, not a check the request never asked for.
    checks = [c for c in CHECK_IDS if c != omitted]
    out = await _score(_payload(checks))
    assert omitted not in {row["id"] for row in out["checks"]}
    assert out["verdict_recommendation"] == "KILL"


async def test_empty_request_forces_kill() -> None:
    out = await _score(_payload([]))
    assert out["verdict_recommendation"] == "KILL"


async def test_omitting_only_advisory_checks_stays_clear() -> None:
    checks = [c for c in CHECK_IDS if c not in ADVISORY_IDS]
    out = await _score(_payload(checks))
    assert out["verdict_recommendation"] == "CLEAR"
