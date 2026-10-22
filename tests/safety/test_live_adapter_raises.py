"""Live adapter refuses every write and audits it (INV-C-03).

Even with every precondition met, no live write happens in this
release: ``LiveAdapterStub.place``/``cancel`` append one
``LiveWriteAttempted`` row and raise ``LiveGateError``. Precondition (8)
(``adapter_registered``) is structurally unmet because no implementation
ships.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.errors import LiveGateError
from pumpgrok.core.ids import IdFactory
from pumpgrok.execution.live.live_adapter import LiveAdapterStub
from pumpgrok.execution.live.live_gate import LiveGate
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng

EPOCH_START = 1767225600.0
MINT = "So11111111111111111111111111111111111111112"


def _harness(tmp_path: Path) -> tuple[LiveAdapterStub, LedgerStore, OrderRequest]:
    ledger = LedgerStore(tmp_path / "ledger.sqlite")
    gate = LiveGate(mode="paper", environ={}, root=tmp_path)
    clock = FixtureClock(start=EPOCH_START)
    stub = LiveAdapterStub(gate=gate, ledger=ledger, clock=clock, ids=IdFactory(clock, make_rng()))
    request = OrderRequest(
        ticket_id="SOL-20260101-001",
        mint=MINT,
        side="buy",
        size_lamports=1_000_000,
        max_slippage_bps=100,
        decision_id="01" + "A" * 24,
        approval_id="apr-" + "C" * 26,
        correlation_id="01" + "J" * 24,
    )
    return stub, ledger, request


async def test_live_adapter_place_raises_and_audits(tmp_path: Path) -> None:
    """INV-C-03: place appends LiveWriteAttempted then raises LiveGateError."""
    stub, ledger, request = _harness(tmp_path)
    try:
        await stub.place(request)
    except LiveGateError:
        pass
    else:
        raise AssertionError("place did not raise LiveGateError")
    rows = ledger.read()
    assert [row["type"] for row in rows] == ["LiveWriteAttempted"]
    assert rows[0]["payload"]["method"] == "place"


async def test_live_adapter_cancel_raises_and_audits(tmp_path: Path) -> None:
    """INV-C-03: cancel appends LiveWriteAttempted then raises LiveGateError."""
    stub, ledger, request = _harness(tmp_path)
    try:
        await stub.cancel("order-1", request.ticket_id, request.decision_id)
    except LiveGateError:
        pass
    else:
        raise AssertionError("cancel did not raise LiveGateError")
    rows = ledger.read()
    assert [row["type"] for row in rows] == ["LiveWriteAttempted"]
    assert rows[0]["payload"]["method"] == "cancel"


def test_adapter_precondition_unmet_because_nothing_ships(tmp_path: Path) -> None:
    """INV-C-03: precondition (8) is unmet with no implementation."""
    gate = LiveGate(mode="live", environ={"PUMPGROK_LIVE_ENABLE": "1"}, root=tmp_path)
    by_id = {item.id: item for item in gate.evaluate()}
    assert by_id["adapter_registered"].met is False
