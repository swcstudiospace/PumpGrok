"""Gateway ledger (GRK-08, T-14-01-03).

Records every call with integer lamports and request hashes only. Prompt
text and secret values never enter a row.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LedgerRow:
    request_hash: str
    agent: str
    outcome: str
    lamports: int


class GatewayLedger:
    def __init__(self) -> None:
        self._rows: list[LedgerRow] = []
        self._transport_calls = 0

    def record(self, *, request_hash: str, agent: str, outcome: str, lamports: int) -> LedgerRow:
        row = LedgerRow(
            request_hash=request_hash, agent=agent, outcome=outcome, lamports=int(lamports)
        )
        self._rows.append(row)
        if outcome == "transport":
            self._transport_calls += 1
        return row

    @property
    def transport_calls(self) -> int:
        return self._transport_calls

    @property
    def rows(self) -> list[LedgerRow]:
        return list(self._rows)

    def to_jsonl(self) -> str:
        lines = [
            json.dumps(
                {
                    "agent": row.agent,
                    "lamports": row.lamports,
                    "outcome": row.outcome,
                    "request_hash": row.request_hash,
                },
                sort_keys=True,
            )
            for row in self._rows
        ]
        return "\n".join(lines) + ("\n" if lines else "")

    def snapshot(self) -> dict[str, Any]:
        return {
            "transport_calls": self._transport_calls,
            "rows": [
                {
                    "agent": row.agent,
                    "lamports": row.lamports,
                    "outcome": row.outcome,
                    "request_hash": row.request_hash,
                }
                for row in self._rows
            ],
        }
