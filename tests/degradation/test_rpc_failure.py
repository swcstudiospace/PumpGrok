"""INV-R-33: RPC failure fails over, then goes BLIND with a breaker trip.

Faults are injected at the RPC boundary through FaultyRpcClient; the
assertions drive product code (DegradedState, ExecErrorsBreaker, RpcError)
and prove the fault fired before any recovery is claimed.
"""

from __future__ import annotations

import pytest

from harness.faults import FaultMode, FaultyRpcClient
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.breakers import EXEC_ERRORS_COOLDOWN_S, ExecErrorsBreaker
from pumpgrok.supervisor.scheduler import DegradedState
from pumpgrok.tools.onchain.rpc import RpcError

BASE = 1767225600.0


async def test_rpc_rate_limit_and_failover_then_blind() -> None:
    fake = FaultyRpcClient([FaultMode.RATE_LIMIT, FaultMode.RAISE])
    degraded = DegradedState(rpc_endpoints=[True, True])
    with pytest.raises(RpcError):
        await fake.call("getAccountInfo", ["mint"])
    assert fake.fired == 2
    assert fake.attempts == [0, 1]
    degraded.note_rpc_result(0, False)
    assert degraded.rpc_blind is False
    degraded.note_rpc_result(1, False)
    assert degraded.rpc_blind is True


async def test_rpc_blind_recovers_on_healthy_probe() -> None:
    degraded = DegradedState(rpc_endpoints=[False, False])
    assert degraded.rpc_blind is True
    fake = FaultyRpcClient([None])
    result = await fake.call("getAccountInfo", ["mint"])
    assert result["endpoint"] == 0
    assert fake.fired == 0
    degraded.note_rpc_result(0, True)
    assert degraded.rpc_blind is False


def test_exec_errors_breaker_trips_at_third_rpc_error() -> None:
    clock = FixtureClock(start=BASE)
    breaker = ExecErrorsBreaker(now=clock.now)
    breaker.note_reject(BASE, "rpc_error")
    breaker.note_reject(BASE + 1.0, "rpc_error")
    assert breaker.is_open is False
    breaker.note_reject(BASE + 2.0, "rpc_error")
    assert breaker.is_open is True
    assert breaker.state == "open"


def test_exec_errors_breaker_recovers_after_cooldown_probe() -> None:
    clock = FixtureClock(start=BASE)
    breaker = ExecErrorsBreaker(now=clock.now)
    for offset in (0.0, 1.0, 2.0):
        breaker.note_reject(BASE + offset, "rpc_error")
    assert breaker.is_open is True
    clock.advance_to(BASE + 2.0 + EXEC_ERRORS_COOLDOWN_S + 1.0)
    assert breaker.is_open is False
    assert breaker.admit_probe() is True
    breaker.resolve_probe(True)
    assert breaker.state == "closed"
