"""Operator input inventory (ONB-01, T-14-08-01).

Every operator input with required/optional/forbidden/not-read per mode,
snapshot-pinned so an inventory edit is a visible digest change.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pumpgrok.core.idempotency import canonical_json


@dataclass(frozen=True)
class InputSpec:
    name: str
    required_in: frozenset[str]
    forbidden_in: frozenset[str]
    not_read_in: frozenset[str]
    source: str

    def kind_for(self, mode: str) -> str:
        if mode in self.forbidden_in:
            return "forbidden"
        if mode in self.not_read_in:
            return "not-read"
        if mode in self.required_in:
            return "required"
        return "optional"


#: x.ai key: required to call Grok; empty counts as missing; never echoed.
#: Wallet public address: never read in paper, required in live.
#: RPC endpoint: optional with a recorded public default.
#: Seat tool-access approvals: required per enabled seat in both modes.
#: HMAC confirmation key: forbidden in live.
INVENTORY: tuple[InputSpec, ...] = (
    InputSpec(
        name="xai_api_key",
        required_in=frozenset({"paper", "live"}),
        forbidden_in=frozenset(),
        not_read_in=frozenset(),
        source="PUMPGROK_GROK__API_KEY",
    ),
    InputSpec(
        name="wallet_public_address",
        required_in=frozenset({"live"}),
        forbidden_in=frozenset(),
        not_read_in=frozenset({"paper"}),
        source="wallet.allowlist",
    ),
    InputSpec(
        name="rpc_endpoint",
        required_in=frozenset(),
        forbidden_in=frozenset(),
        not_read_in=frozenset(),
        source="rpc.endpoints",
    ),
    InputSpec(
        name="seat_tool_access",
        required_in=frozenset({"paper", "live"}),
        forbidden_in=frozenset(),
        not_read_in=frozenset(),
        source="access-decisions.jsonl",
    ),
    InputSpec(
        name="hmac_confirmation_key",
        required_in=frozenset(),
        forbidden_in=frozenset({"live"}),
        not_read_in=frozenset(),
        source="PUMPGROK_CONFIRMATION_KEY",
    ),
)

SPEC_BY_NAME: dict[str, InputSpec] = {spec.name: spec for spec in INVENTORY}


def inventory_snapshot_hash() -> str:
    """sha256 of the canonical inventory. Any edit changes the digest."""
    body = [
        {
            "name": spec.name,
            "required_in": sorted(spec.required_in),
            "forbidden_in": sorted(spec.forbidden_in),
            "not_read_in": sorted(spec.not_read_in),
            "source": spec.source,
        }
        for spec in INVENTORY
    ]
    return hashlib.sha256(canonical_json({"inputs": body}).encode()).hexdigest()
