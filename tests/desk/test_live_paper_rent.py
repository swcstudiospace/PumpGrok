"""FEE-01 ATA rent on the composition roots (owner decision 2026-11-15).

The live-data paper root reads the rent-exempt minimum from an injected RPC client when one
is configured, and otherwise uses the recorded offline pin. The replay root always uses the
pin and takes no RPC client. Offline only: the RPC client and the transport are doubles.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from datafeed.readonly_double import ReadOnlyDouble
from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.fees import (
    ATA_RENT_OFFLINE_EPOCH,
    ATA_RENT_OFFLINE_LAMPORTS,
    ATA_RENT_OFFLINE_SOURCE,
    ATA_TOKEN_ACCOUNT_DATA_LEN,
    PAPER_DEFAULT_FEE_MODEL,
)
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor.live_paper import LivePaperRoot, build_live_paper_root
from pumpgrok.supervisor.scheduler import open_replay_runtime

ENDPOINT = "https://rpc.example.invalid"
START = 1_767_225_600.0
SEED = 20260101
RENT_METHOD = "getMinimumBalanceForRentExemption"
#: A test-double answer for the RPC read. It is not a network value and not a pin.
RPC_ANSWER = 1_234_567
SMOKE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "replay" / "smoke"


class RentRpcDouble:
    """Canned RPC client: answers the rent read and records every call."""

    def __init__(self, answer: object = RPC_ANSWER) -> None:
        self.answer = answer
        self.calls: list[tuple[str, list[Any]]] = []

    async def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, params))
        return self.answer


async def _build(
    tmp_path: Path, transport: ReadOnlyDouble, *, rent_rpc: RentRpcDouble | None = None
) -> LivePaperRoot:
    return await build_live_paper_root(
        mode="paper",
        endpoint=ENDPOINT,
        transport=transport,
        clock=FixtureClock(START),
        rng_seed=7,
        data_dir=tmp_path / "desk",
        budget=RiskBudget(),
        limits=EngineLimits(),
        max_age_s=10.0,
        max_observations=4,
        rent_rpc=rent_rpc,
    )


async def test_configured_rpc_rent_is_used_on_live_root(tmp_path: Path) -> None:
    rpc = RentRpcDouble()
    transport = ReadOnlyDouble()
    root = await _build(tmp_path, transport, rent_rpc=rpc)
    try:
        assert rpc.calls == [(RENT_METHOD, [ATA_TOKEN_ACCOUNT_DATA_LEN])]
        assert root.fees.ata_rent_lamports == RPC_ANSWER
        assert root.fees.ata_rent_epoch is None
        assert root.fees.ata_rent_source == "rpc:getMinimumBalanceForRentExemption(165)"
        # The adapter prices fills with the same model the root reports.
        assert root.adapter._fees is root.fees
        assert transport.frames == []
    finally:
        root.close()


@pytest.mark.parametrize("answer", [None, "1488440", 0, -1, True, 1.5])
async def test_invalid_rpc_rent_refuses_build_and_writes_nothing(
    tmp_path: Path, answer: object
) -> None:
    with pytest.raises(ValueError):
        await _build(tmp_path, ReadOnlyDouble(), rent_rpc=RentRpcDouble(answer))

    assert not (tmp_path / "desk").exists()


async def test_live_root_without_rpc_uses_recorded_pin(tmp_path: Path) -> None:
    transport = ReadOnlyDouble()
    root = await _build(tmp_path, transport)
    try:
        assert root.fees is PAPER_DEFAULT_FEE_MODEL
        assert root.fees.ata_rent_lamports == ATA_RENT_OFFLINE_LAMPORTS
        assert root.fees.ata_rent_epoch == ATA_RENT_OFFLINE_EPOCH
        assert root.fees.ata_rent_source == ATA_RENT_OFFLINE_SOURCE
        assert transport.frames == []
    finally:
        root.close()


def test_replay_root_uses_recorded_pin(tmp_path: Path) -> None:
    runtime = open_replay_runtime(SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "l.db")
    try:
        fees = runtime.adapter._fees
        assert fees is PAPER_DEFAULT_FEE_MODEL
        assert fees.ata_rent_lamports == ATA_RENT_OFFLINE_LAMPORTS
        assert fees.ata_rent_epoch == ATA_RENT_OFFLINE_EPOCH
        assert fees.ata_rent_source == ATA_RENT_OFFLINE_SOURCE
    finally:
        runtime.store.close()


def test_replay_root_takes_no_rpc_client() -> None:
    names = inspect.signature(open_replay_runtime).parameters
    assert [name for name in names if "rpc" in name or "rent" in name] == []
