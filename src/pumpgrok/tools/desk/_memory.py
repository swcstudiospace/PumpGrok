"""Seat memory bank: JSONL-backed retain/recall for desk tools (TOOL-007).

One file per bank directory; each line is one record. The in-memory index is
rebuilt from the file at construction, so restarts keep history. Refused
writes never reach the file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["MemoryBank"]


class MemoryBank:
    """JSONL record store with a key index for idempotent retains."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._records: list[dict[str, Any]] = []
        self._by_key: dict[str, str] = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                self._records.append(record)
                if "key" in record and "id" in record:
                    self._by_key[str(record["key"])] = str(record["id"])

    @property
    def path(self) -> Path:
        return self._path

    def retain(self, *, key: str, record: dict[str, Any]) -> str:
        """Append ``record`` under ``key``; a known key replays its id."""
        existing = self._by_key.get(key)
        if existing is not None:
            return existing
        digest = hashlib.sha256(
            json.dumps(record, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        stored = {"id": digest, "key": key, **record}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(stored) + "\n")
        self._records.append(stored)
        self._by_key[key] = digest
        return digest

    def recall(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Newest-first substring search over record content (case-insensitive)."""
        needle = query.lower()
        hits = [
            {k: v for k, v in record.items() if k != "key"}
            for record in reversed(self._records)
            if needle in str(record.get("content", "")).lower()
        ]
        return hits[:limit]
