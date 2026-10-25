"""safety.provider: paid-RPC-provider signal for BLIND advisory handling.

While no paid RPC provider is recorded, SAFE-4 holder-concentration and
SAFE-8 deployer-history BLIND results are advisory (amendment 2026-10-25).
The signal is env PUMPGROK_PAID_RPC_PROVIDER; empty or unset means none
recorded. The value is never logged.
"""

from __future__ import annotations

import os

PAID_RPC_PROVIDER_ENV_VAR = "PUMPGROK_PAID_RPC_PROVIDER"


def paid_rpc_provider_recorded() -> bool:
    """True when a paid RPC provider is recorded; empty or unset means none."""
    return bool(os.environ.get(PAID_RPC_PROVIDER_ENV_VAR, "").strip())
