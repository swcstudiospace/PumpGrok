"""Generate the hand-authored smoke-10m fixture (paper-engine.md 4.6, PAPER-004).

Forty-one ticks spanning ten minutes at fifteen-second cadence, alternating
two mints with one graduated (``complete: true``) tick for realism. Gaps stay
far below the runner's 120 s silence budget so ``verify`` passes; the DataStale
path is covered by a synthetic gapped dataset in the determinism test, not by
this fixture. The recorded LLM outcome answers the runner's model-resolution
request, whose hash is computed with the same helpers the runner uses.

Re-running this script regenerates byte-identical files; the manifest pins
every listed file with its sha256 digest.
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
    out: list[str] = []
    counter = 0
    while len(out) < length:
        first = hashlib.sha256(f"smoke-10m/{label}:{counter}".encode()).digest()
        second = hashlib.sha256(first).digest()
        for byte in first + second:
            if len(out) >= length:
                break
            out.append(_B58[byte % 58])
        counter += 1
    return "".join(out)


DATASET = "smoke-10m"
BASE_EPOCH = 1767225600.0  # 2026-01-01T00:00:00Z
STEP_S = 15.0
COUNT = 41
MINT_A = _derive_mint("mint-a")
MINT_B = _derive_mint("mint-b")
LATENCY_S = 1.9


def _stamp(n: int) -> str:
    moment = datetime.fromtimestamp(BASE_EPOCH + n * STEP_S, UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def build_events() -> list[dict[str, Any]]:
    """Hand-author the tick stream: gentle reserve drift, no gaps."""
    events: list[dict[str, Any]] = []
    for n in range(COUNT):
        mint = MINT_A if n % 2 == 0 else MINT_B
        events.append(
            {
                "ts_utc": _stamp(n),
                "kind": "tick",
                "mint": mint,
                "S": 42_000_000_000 + n * 12_000_000 - (n % 3) * 5_000_000,
                "T": 766_428_571_428_571 - n * 380_000_000,
                "complete": n == 21,
                "source": "rest" if n % 2 == 0 else "pumpportal",
            }
        )
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
                "note": "hand-authored smoke-10m outcome",
            },
        }
    ]


def _lines(records: list[dict[str, Any]]) -> bytes:
    return ("".join(json.dumps(record) + "\n" for record in records)).encode("utf-8")


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    events = build_events()
    llm = build_llm(events)
    files = {"events.jsonl": _lines(events), "llm.jsonl": _lines(llm)}
    manifest = {
        "dataset": DATASET,
        "recorded_from_utc": events[0]["ts_utc"],
        "recorded_to_utc": events[-1]["ts_utc"],
        "seed_hint": 20260101,
        "sources": {"rest": "hand-authored", "pumpportal": "hand-authored"},
        "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "notes": (
            "Hand-authored CI smoke dataset (not recorded from live feeds). "
            "Two derived 44-char base58 mints (sha256 over smoke-10m/mint-a and "
            "smoke-10m/mint-b), 41 ticks over ten minutes, one complete=true "
            "tick, one recorded LLM ok outcome."
        ),
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    for name, data in files.items():
        (out_dir / name).write_bytes(data)
    (out_dir / "manifest.json").write_bytes(manifest_bytes)


if __name__ == "__main__":
    main()
