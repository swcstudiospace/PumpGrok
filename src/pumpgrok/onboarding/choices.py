"""Operator choice records (ONB, T-14-08-03).

Choices are append-only rows keyed by name. RPC values are stored by host
only; the full endpoint, path, query, userinfo, or key never lands here.
"""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.onboarding.validators import host_only


def record_choice(path: Path, name: str, value: str) -> dict[str, str]:
    """Append one operator-choice row. RPC endpoint values are host-only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = host_only(value) if "://" in value else value
    row = {"name": name, "value": stored, "source": "operator-choice"}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(row) + "\n")
    return row


def read_choices(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows
