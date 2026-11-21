"""Doctor readiness report (ONB-02, T-14-08-01).

One record per inventory input: name, required_for_mode, status, source.
Status is `present`, `missing`, `default`, `forbidden-present`, or
`not-read`. No secret value ever enters a record.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pumpgrok.onboarding.inventory import INVENTORY

#: Env vars that mark an input present. Values are never read beyond
#: non-emptiness; an empty x.ai key counts as missing.
_ENV_BY_INPUT: dict[str, str] = {
    "xai_api_key": "PUMPGROK_GROK__API_KEY",
    "hmac_confirmation_key": "PUMPGROK_CONFIRMATION_KEY",
}


@dataclass(frozen=True)
class InputRecord:
    name: str
    required_for_mode: bool
    status: str
    source: str


def doctor_records(env: Mapping[str, str], mode: str) -> list[InputRecord]:
    records: list[InputRecord] = []
    for spec in INVENTORY:
        kind = spec.kind_for(mode)
        env_name = _ENV_BY_INPUT.get(spec.name)
        present = env_name is not None and bool(env.get(env_name, "").strip())
        if spec.name == "wallet_public_address":
            present = False
        if spec.name == "seat_tool_access":
            present = False
        if kind == "forbidden":
            status = "forbidden-present" if present else "missing"
        elif kind == "not-read":
            status = "not-read"
        elif spec.name == "rpc_endpoint":
            status = "present" if present else "default"
        elif kind == "required":
            status = "present" if present else "missing"
        else:
            status = "present" if present else "missing"
        records.append(
            InputRecord(
                name=spec.name,
                required_for_mode=kind == "required",
                status=status,
                source=spec.source,
            )
        )
    return records


def failing_records(records: list[InputRecord]) -> list[InputRecord]:
    """Records that fail the readiness check for their mode."""
    failures: list[InputRecord] = []
    for record in records:
        if record.status == "forbidden-present":
            failures.append(record)
        elif record.required_for_mode and record.status == "missing":
            failures.append(record)
    return failures
