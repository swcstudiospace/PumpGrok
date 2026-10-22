"""Characterization: priority-fee estimate (STRUCT-002).

Pins ``tools/onchain/priority_fee.py`` against the retired ``priority_fee``
root oracle (kept byte-identical per R53).

Divergence from the oracle (deliberate, decided per MIGRATION_MAP row 77):
``recommended_lamports_per_cu`` is kept as an explicit documented alias for
``recommended_micro_lamports`` -- never silently carried, never silently
dropped. The ``rpc`` URL echo is dropped (T-02-01); percentile math and the
``note`` string are byte-identical.

Ports 1 root unittest case (R55): ``test_priority_fee_main_exits_nonzero_on_error``
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
from pumpgrok.tools.onchain.priority_fee import estimate_priority_fee
from pumpgrok.tools.onchain.rpc import RpcClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "http"


def _body(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["http"]


@pytest.mark.characterization
async def test_priority_fee_percentile_math() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["method"] == "getRecentPrioritizationFees"
        return httpx.Response(200, json=_body("priority_fee.json"))

    rpc = RpcClient(
        ["https://rpc.invalid"],
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        FixtureClock(),
        rng=random.Random(7),
        max_attempts_per_endpoint=1,
    )
    result = await estimate_priority_fee(rpc, percentile=50, multiplier=1.2)
    assert result["ok"] is True
    assert result["samples"] == 5
    assert result["min"] == 0
    assert result["median"] == 2000
    assert result["mean"] == 2000
    assert result["max"] == 4000
    assert result["percentile_fee"] == 2000
    assert result["recommended_micro_lamports"] == 2400
    assert result["recommended_lamports_per_cu"] == 2400
    assert result["note"] == (
        "Value is micro-lamports per compute unit. "
        "Use with ComputeBudgetProgram.set_compute_unit_price."
    )
    assert "rpc" not in result


@pytest.mark.characterization
async def test_priority_fee_empty_response_is_ok_false() -> None:
    """Root case port: ok False is the exact predicate main() exits non-zero on."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": []})

    rpc = RpcClient(
        ["https://rpc.invalid"],
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        FixtureClock(),
        rng=random.Random(7),
        max_attempts_per_endpoint=1,
    )
    result = await estimate_priority_fee(rpc)
    assert result["ok"] is False
