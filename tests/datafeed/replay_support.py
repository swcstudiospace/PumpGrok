"""Verified replay authority for datafeed tests.

Same contract as ``tests/execution/replay_support.py``: ticks are written as a
manifest-checked dataset, loaded by the verifying loader, and the curve source
bound to it is the only price source a verified BUY or mark may read. No test
injects a fixture-labelled curve to get trust.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pumpgrok.core.ids import Clock
from pumpgrok.execution import VerifiedReplay, verify_replay
from pumpgrok.replay.clock import format_ts_utc

__all__ = ["replay_authority", "tick", "write_dataset"]


def tick(
    epoch: float, mint: str, s_lamports: int, t_units: int, *, complete: bool = False
) -> dict[str, Any]:
    """One curve tick event at ``epoch``, in fixture ``ts_utc`` format."""
    return {
        "ts_utc": format_ts_utc(epoch),
        "kind": "tick",
        "mint": mint,
        "S": s_lamports,
        "T": t_units,
        "complete": complete,
        "source": "rest",
    }


def write_dataset(root: Path, events: list[dict[str, Any]], *, name: str = "replay") -> Path:
    """Write ``events`` (already in ts_utc order) as a manifest-checked dataset."""
    dataset = root / name
    dataset.mkdir(parents=True)
    data = "".join(json.dumps(event) + "\n" for event in events)
    (dataset / "events.jsonl").write_text(data, encoding="utf-8")
    manifest = {
        "dataset": name,
        "recorded_from_utc": str(events[0]["ts_utc"]),
        "recorded_to_utc": str(events[-1]["ts_utc"]),
        "seed_hint": 20260201,
        "sources": {"rest": "hand-authored"},
        "sha256": {"events.jsonl": hashlib.sha256(data.encode("utf-8")).hexdigest()},
        "notes": "datafeed test dataset",
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dataset


def replay_authority(
    root: Path, clock: Clock, events: list[dict[str, Any]], *, name: str = "replay"
) -> VerifiedReplay:
    """Verify a dataset of ``events`` and return the replay authority bound to it."""
    return verify_replay(write_dataset(root, events, name=name), clock)
