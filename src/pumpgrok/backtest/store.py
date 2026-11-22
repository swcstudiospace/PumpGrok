"""Deterministic persisted backtest run records (BT-13).

Records persist sorted by idempotence key as byte-stable JSON lines, so
two runs over the same inputs produce byte-equal store files. No
timestamps, no randomness: the same record always serializes identically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["RunStore", "idempotence_key", "dumps_record"]


def idempotence_key(dataset_digest: str, strategy_id: str, param_hash: str) -> str:
    """One run per (dataset digest, strategy id, param hash) triple."""
    return f"{dataset_digest}:{strategy_id}:{param_hash}"


def dumps_record(record: dict[str, Any]) -> bytes:
    """Byte-stable serialization of one record (sorted keys, newline terminated)."""
    return (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class RunStore:
    """Append/read store of backtest run records under a state path."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        """The backing file path."""
        return self._path

    def has(self, key: str) -> bool:
        """Whether a record with this idempotence key already persisted."""
        return any(record.get("idempotence_key") == key for record in self.load_all())

    def save(self, record: dict[str, Any]) -> dict[str, Any]:
        """Persist one record; returns the stored record unchanged."""
        with self._path.open("ab") as handle:
            handle.write(dumps_record(record))
        return record

    def load_all(self) -> list[dict[str, Any]]:
        """All persisted records in idempotence-key order (deterministic)."""
        if not self._path.is_file():
            return []
        records = [
            json.loads(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        records.sort(key=lambda record: str(record.get("idempotence_key", "")))
        return records

    def get(self, key: str) -> dict[str, Any] | None:
        """One record by idempotence key, or None when absent."""
        for record in self.load_all():
            if record.get("idempotence_key") == key:
                return record
        return None
