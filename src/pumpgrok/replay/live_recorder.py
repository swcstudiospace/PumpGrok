"""Live recorder (REC-01, REC-02, T-13-01b/c).

Writes ticks plus gaps into a dataset directory; ``seal`` writes
``manifest.json`` with the sha256 of every listed file so the sealed
dataset passes :func:`pumpgrok.replay.fixtures.load_dataset` unchanged.
Ticks land in ``events.jsonl`` (the name ``load_dataset`` requires);
gaps land in ``gaps.jsonl``. Non-decreasing ``ts_utc`` is enforced at
write time; a torn trailing line is truncated on startup and recorded.
No back-fill, no interpolation, no external history. Never opens
``var/ledger.sqlite``. Writes go through tmp plus ``os.replace``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from pumpgrok.datafeed.events import CurveTick, GapEvent
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, FixtureManifest

GAPS_NAME = "gaps.jsonl"
_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


def validate_dataset_name(name: str) -> str:
    """Mirror ``FixtureManifest.dataset``: one plain name, no separators or '..'."""
    if not _NAME_RE.fullmatch(name) or ".." in name:
        raise ValueError("dataset must be a plain name without separators or '..'")
    return name


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class LiveRecorder:
    """Append ticks/gaps; seal into a self-verifying dataset."""

    def __init__(self, dataset_dir: Path) -> None:
        self._dir = Path(dataset_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._notes: list[str] = []
        self._recover(EVENTS_NAME)
        self._recover(GAPS_NAME)
        self._last_ts: float | None = None
        self._seed_last_ts()

    @property
    def notes(self) -> tuple[str, ...]:
        return tuple(self._notes)

    def _recover(self, name: str) -> None:
        """Truncate a torn trailing line to the last complete line; record it."""
        path = self._dir / name
        if not path.is_file():
            return
        data = path.read_bytes()
        if not data or data.endswith(b"\n"):
            return
        last_newline = data.rfind(b"\n")
        kept = data[: last_newline + 1] if last_newline >= 0 else b""
        removed = len(data) - len(kept)
        _atomic_write(path, kept)
        self._notes.append(f"recovered {name}: truncated {removed} torn bytes")

    def _seed_last_ts(self) -> None:
        path = self._dir / EVENTS_NAME
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                self._last_ts = parse_ts_utc(str(record["ts_utc"]))
            except (ValueError, KeyError):
                continue

    def _append(self, name: str, record: dict[str, Any]) -> None:
        path = self._dir / name
        line = json.dumps(record, sort_keys=True).encode() + b"\n"
        existing = path.read_bytes() if path.is_file() else b""
        _atomic_write(path, existing + line)

    def record_tick(self, tick: CurveTick) -> None:
        stamp = parse_ts_utc(tick.ts_utc)
        if self._last_ts is not None and stamp < self._last_ts:
            raise ValueError("tick timestamps must be non-decreasing")
        record = tick.model_dump(mode="json")
        self._append(EVENTS_NAME, record)
        self._last_ts = stamp

    def record_gap(self, gap: GapEvent) -> None:
        self._append(GAPS_NAME, gap.model_dump(mode="json"))

    def seal(self, dataset_name: str, *, seed_hint: int = 0) -> Path:
        """Write manifest.json listing every data file; return the dataset dir."""
        validate_dataset_name(dataset_name)
        sha: dict[str, str] = {}
        ticks_path = self._dir / EVENTS_NAME
        if ticks_path.is_file():
            sha[EVENTS_NAME] = _sha256(ticks_path.read_bytes())
        gaps_path = self._dir / GAPS_NAME
        if gaps_path.is_file():
            sha[GAPS_NAME] = _sha256(gaps_path.read_bytes())
        if not sha:
            raise ValueError("nothing recorded; seal refuses an empty dataset")
        first = last = ""
        if ticks_path.is_file():
            lines = ticks_path.read_text(encoding="utf-8").splitlines()
            if lines:
                first = str(json.loads(lines[0])["ts_utc"])
                last = str(json.loads(lines[-1])["ts_utc"])
        if not first:
            stamp = format_ts_utc(0.0)
            first = last = stamp
        manifest = FixtureManifest(
            dataset=dataset_name,
            recorded_from_utc=first,
            recorded_to_utc=last,
            seed_hint=seed_hint,
            sources={"recorder": "live_recorder"},
            sha256=sha,
            notes="; ".join(self._notes),
        )
        payload = json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True).encode()
        _atomic_write(self._dir / MANIFEST_NAME, payload)
        return self._dir
