"""Synthesise the soak-3d fixture from the smoke-10m shape (seed 20260101).

Three UTC days of 60 s ticks (two midnight boundaries), one graduation
(`complete=true` mid-day-2), one creator with two launches, deterministic
base58 mints, one recorded LLM ok outcome. Manifest carries the same keys
as smoke-10m/manifest.json including sha256 digests.

Usage: uv run python scripts/build_soak_fixture.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pumpgrok.replay.recorder import canonical_request_hash
from pumpgrok.replay.runner import llm_request_for

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _derive_mint(label: str, length: int = 44) -> str:
    """Derive a deterministic base58 mint from a domain-separated label."""
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    out = ""
    value = int.from_bytes(digest, "big")
    while len(out) < length:
        out += _B58[value % 58]
        value //= 58
        if value == 0:
            digest = hashlib.sha256((label + out).encode("utf-8")).digest()
            value = int.from_bytes(digest, "big")
    return out


DATASET = "soak-3d"
BASE_EPOCH = 1767225600.0  # 2026-01-01T00:00:00Z
STEP_S = 60.0
DAYS = 3
# Half-open day range: Jan 1 00:00 inclusive to Jan 4 00:00 exclusive, so the
# fixture touches exactly three UTC days (D6: one DailyRollover per day).
COUNT = DAYS * 86400 // int(STEP_S)
MINT_A = _derive_mint("soak-3d/mint-a")
MINT_B = _derive_mint("soak-3d/mint-b")
CREATOR = _derive_mint("soak-3d/creator", 32)
GRADUATION_INDEX = 86400 // int(STEP_S) + 43200 // int(STEP_S)
LAUNCH_INDEXES = (21600 // int(STEP_S), 86400 // int(STEP_S) + 7200 // int(STEP_S))
LATENCY_S = 1.9


def _stamp(n: int) -> str:
    moment = datetime.fromtimestamp(BASE_EPOCH + n * STEP_S, UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def build_events() -> list[dict[str, Any]]:
    """Three virtual days of gentle reserve drift, strictly ordered."""
    events: list[dict[str, Any]] = []
    for n in range(COUNT):
        mint = MINT_A if n % 2 == 0 else MINT_B
        event: dict[str, Any] = {
            "ts_utc": _stamp(n),
            "kind": "tick",
            "mint": mint,
            "S": 42_000_000_000 + n * 1_000_000 - (n % 5) * 400_000,
            "T": 766_428_571_428 - n * 30_000_000,
            "complete": n == GRADUATION_INDEX,
            "source": "rest" if n % 2 == 0 else "pumpportal",
        }
        if n in LAUNCH_INDEXES:
            event["creator"] = CREATOR
            event["launch"] = LAUNCH_INDEXES.index(n) + 1
        events.append(event)
    return events


def build_llm(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The one recorded model outcome the runner's request hash must hit."""
    request_hash = canonical_request_hash(llm_request_for(DATASET, events))
    return [
        {
            "request_hash": request_hash,
            "outcome": "ok",
            "latency_s": LATENCY_S,
            "response": {
                "model": "grok-replay",
                "verdict": "skip",
                "note": "synthesised soak-3d outcome",
            },
        }
    ]


def _lines(records: list[dict[str, Any]]) -> bytes:
    return ("".join(json.dumps(record) + "\n" for record in records)).encode("utf-8")


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "replay" / DATASET
    out_dir.mkdir(parents=True, exist_ok=True)
    events = build_events()
    llm = build_llm(events)
    files = {"events.jsonl": _lines(events), "llm.jsonl": _lines(llm)}
    manifest = {
        "dataset": DATASET,
        "recorded_from_utc": events[0]["ts_utc"],
        "recorded_to_utc": events[-1]["ts_utc"],
        "seed_hint": 20260101,
        "sources": {"rest": "synthesised", "pumpportal": "synthesised"},
        "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "notes": (
            "Synthesised CI soak dataset (not recorded from live feeds). Two derived "
            "44-char base58 mints, three UTC days of 60 s ticks (two midnight "
            "boundaries), one complete=true graduation mid-day-2, one creator with "
            "two launches, one recorded LLM ok outcome."
        ),
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    for name, data in files.items():
        (out_dir / name).write_bytes(data)
    (out_dir / "manifest.json").write_bytes(manifest_bytes)
    total = sum(len(data) for data in files.values()) + len(manifest_bytes)
    print(f"wrote {len(events)} events + {len(llm)} llm rows to {out_dir} ({total} bytes)")


if __name__ == "__main__":
    main()
