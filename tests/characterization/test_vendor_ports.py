"""INV-R-28: duplicate and out-of-order WS events are idempotent.

Owning test for SAFETY_INVARIANTS.md section 3.3 row INV-R-28. The same
PumpPortal create/trade frame delivered twice produces one candidate and
one trade: the SeenSet bounds memory at MAX_REMEMBERED and pending is
capped at MAX_PENDING. Ports the vendor SeenSet behaviour
(monitor.py:41) against the ported LaunchMonitor.

Harness: synthetic create frames on FixtureClock; no wall clock, no network.
"""

from __future__ import annotations

from pumpgrok.config.settings import DataSettings, FilterSettings
from pumpgrok.engine.monitor import MAX_PENDING, MAX_REMEMBERED, LaunchMonitor, SeenSet
from pumpgrok.replay.clock import FixtureClock

NOW = 1_700_000_000.0
MINT = "Dup1111111111111111111111111111111111111111"


def _frame(mint: str, seq: int) -> dict:
    return {
        "txType": "create",
        "mint": mint,
        "timestamp": NOW * 1000,
        "name": f"Token {seq}",
        "symbol": "DUP",
        "vSolInBondingCurve": 1.0,
        "marketCapSol": 10.0,
    }


def _monitor(skips: list) -> LaunchMonitor:
    return LaunchMonitor(
        DataSettings(),
        FilterSettings(min_unique_buyers=1, min_age_seconds=0.0, require_metadata=False),
        FixtureClock(start=NOW),
        on_skip=lambda token, reason: skips.append((token.mint, reason)),
    )


def test_monitor_dedup_and_caps() -> None:
    """INV-R-28: one candidate per mint; seen and pending stay bounded."""
    skips: list = []
    monitor = _monitor(skips)
    assert monitor.handle_event(_frame(MINT, 1), NOW) is None
    assert monitor.handle_event(_frame(MINT, 2), NOW) is None
    assert monitor.handle_event({"txType": "trade", "mint": MINT}, NOW) is None
    assert len(monitor.pending) == 1
    for token in list(monitor.pending.values()):
        token.unique_buyers = 10
    first = monitor.sweep(NOW + 1.0)
    assert [token.mint for token in first] == [MINT]
    # Redelivery after emission is dropped by the seen set: still one signal.
    assert monitor.handle_event(_frame(MINT, 3), NOW + 2.0) is None
    for token in list(monitor.pending.values()):
        token.unique_buyers = 10
    assert monitor.sweep(NOW + 3.0) == []
    assert len(skips) == 0
    assert MINT in monitor._emitted
    assert len(monitor._emitted) == 1
    # Memory bounds hold under flood.
    seen = SeenSet(maxlen=8)
    for index in range(20):
        seen.add(f"mint-{index}")
    assert len(seen) <= 8
    assert len(seen) <= MAX_REMEMBERED
    for index in range(MAX_PENDING + 50):
        monitor.handle_event(_frame(f"Mint{index:044d}", index), NOW + 4.0)
    assert len(monitor.pending) <= MAX_PENDING
