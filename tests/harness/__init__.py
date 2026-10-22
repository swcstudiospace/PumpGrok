"""Test harness shared by conftest and the replay/degraded-mode tests."""

from harness.faults import (
    FaultInjector,
    FaultMode,
    FaultyDataSource,
    FaultyExecutionAdapter,
    FaultyLedgerStore,
    FaultyLLMClient,
    FaultyPriceSource,
    FaultyRpcClient,
    InjectedFault,
    InjectedRateLimit,
    InjectedUnknown,
)

__all__ = [
    "FaultInjector",
    "FaultMode",
    "FaultyDataSource",
    "FaultyExecutionAdapter",
    "FaultyLLMClient",
    "FaultyLedgerStore",
    "FaultyPriceSource",
    "FaultyRpcClient",
    "InjectedFault",
    "InjectedRateLimit",
    "InjectedUnknown",
]


class NetworkBlocked(RuntimeError):
    """A test reached for the network without an explicit mock transport."""
