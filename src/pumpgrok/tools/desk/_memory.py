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
        self._corrupt_lines = 0
        if path.is_file():
            for raw_line in path.read_bytes().splitlines():
                try:
                    line = raw_line.decode("utf-8").strip()
                except UnicodeDecodeError:
                    self._corrupt_lines += 1
                    continue
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    self._corrupt_lines += 1
                    continue
                if not isinstance(record, dict):
                    self._corrupt_lines += 1
                    continue
                self._records.append(record)
                if "key" in record and "id" in record:
                    self._by_key[str(record["key"])] = str(record["id"])

    @property
    def corrupt_lines(self) -> int:
        """Count of lines skipped at load; startup never fails on them."""
        return self._corrupt_lines

    @property
    def path(self) -> Path:
        return self._path

    def retain(self, *, key: str, record: dict[str, Any]) -> str:
        """Append ``record`` under ``key``; a known key replays its id."""
        existing = self._by_key.get(key)
        if existing is not None:
            return existing
        digest = hashlib.sha256(json.dumps(record, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        stored = {"id": digest, "key": key, **record}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # A torn final line (no newline) must not swallow the next record.
        needs_break = (
            self._path.is_file() and self._path.stat().st_size > 0 and not self._ends_with_newline()
        )
        with open(self._path, "a", encoding="utf-8") as handle:
            if needs_break:
                handle.write("\n")
            handle.write(json.dumps(stored) + "\n")
        self._records.append(stored)
        self._by_key[key] = digest
        return digest

    def _ends_with_newline(self) -> bool:
        with open(self._path, "rb") as handle:
            handle.seek(-1, 2)
            return handle.read(1) == b"\n"

    def recall(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Newest-first substring search over record content (case-insensitive)."""
        needle = query.lower()
        hits = [
            {k: v for k, v in record.items() if k != "key"}
            for record in reversed(self._records)
            if needle in str(record.get("content", "")).lower()
        ]
        return hits[:limit]
