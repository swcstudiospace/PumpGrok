"""Manifest-gated fixture loading (paper-engine.md 4.3, INV-R-30).

A dataset directory is trusted only after every file the manifest lists matches its
sha256, and no unlisted *.jsonl file sits beside them. Verification runs before any
ledger file is created. A failure is `CorruptFixture`, which the CLI maps to exit 4.

Readers are strict: a corrupt line raises with its line number; it is never skipped.
Error fields carry file names, line numbers and pydantic `loc`/`type` only, never the
offending input value.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.replay.clock import parse_ts_utc

MANIFEST_NAME = "manifest.json"
EVENTS_NAME = "events.jsonl"
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


class CorruptFixture(PumpgrokError):
    """A dataset failed verification or holds an unreadable line. CLI exit 4."""

    code = "corrupt_fixture"


class FixtureManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset: str = Field(min_length=1)
    recorded_from_utc: str
    recorded_to_utc: str
    seed_hint: int
    sources: dict[str, str] = Field(default_factory=dict)
    sha256: dict[str, str]
    notes: str = ""

    @field_validator("sha256")
    @classmethod
    def _plain_names_and_digests(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("at least one file must be listed")
        for name, digest in value.items():
            if not _NAME_RE.fullmatch(name) or ".." in name:
                raise ValueError("file names must be plain names inside the dataset")
            if not _DIGEST_RE.fullmatch(digest):
                raise ValueError("digests must be 64 lowercase hex characters")
        return value


@dataclass(frozen=True)
class FixtureDataset:
    manifest: FixtureManifest
    events: tuple[dict[str, Any], ...]


def event_epoch(event: dict[str, Any]) -> float:
    """Epoch seconds of a fixture event's `ts_utc`. Callers pass events already loaded."""
    return parse_ts_utc(str(event["ts_utc"]))


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name} is not allowed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(dataset_dir: Path) -> FixtureManifest:
    """Check manifest shape, listed sha256 digests and stray data files. Writes nothing."""
    manifest_path = dataset_dir / MANIFEST_NAME
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeDecodeError, ValueError):
        raise CorruptFixture("manifest is missing or not valid JSON", file=MANIFEST_NAME) from None

    try:
        manifest = FixtureManifest.model_validate(raw)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(part) for part in err['loc'])}: {err['type']}"
            for err in exc.errors(include_input=False, include_url=False, include_context=False)
        ]
        raise CorruptFixture("manifest is invalid", file=MANIFEST_NAME, problems=problems) from None

    for name, expected in sorted(manifest.sha256.items()):
        target = dataset_dir / name
        if not target.is_file():
            raise CorruptFixture("listed file is missing", file=name)
        if _sha256(target) != expected:
            raise CorruptFixture("sha256 does not match manifest", file=name)

    for stray in sorted(dataset_dir.glob("*.jsonl")):
        if stray.name not in manifest.sha256:
            raise CorruptFixture("data file is not listed in the manifest", file=stray.name)
    return manifest


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read every line as a JSON object. Any blank, unparseable or non-object line raises."""
    records: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                text = line.strip()
                if not text:
                    raise CorruptFixture("blank line", file=path.name, line=number)
                try:
                    record = json.loads(text, parse_constant=_reject_constant)
                except ValueError:
                    raise CorruptFixture(
                        "line is not valid JSON", file=path.name, line=number
                    ) from None
                if not isinstance(record, dict):
                    raise CorruptFixture("line is not a JSON object", file=path.name, line=number)
                records.append(record)
    except UnicodeDecodeError:
        raise CorruptFixture("file is not UTF-8", file=path.name) from None
    return records


def load_dataset(dataset_dir: Path) -> FixtureDataset:
    """Verify the manifest, then read and order-check events. Call before opening any ledger."""
    manifest = verify_manifest(dataset_dir)
    if EVENTS_NAME not in manifest.sha256:
        raise CorruptFixture("manifest does not list events.jsonl", file=MANIFEST_NAME)

    records = read_jsonl(dataset_dir / EVENTS_NAME)
    previous = float("-inf")
    for number, record in enumerate(records, 1):
        stamp_text = record.get("ts_utc")
        if not isinstance(stamp_text, str):
            raise CorruptFixture("event has no ts_utc", file=EVENTS_NAME, line=number)
        try:
            stamp = parse_ts_utc(stamp_text)
        except ValueError:
            raise CorruptFixture(
                "event ts_utc is not a UTC timestamp", file=EVENTS_NAME, line=number
            ) from None
        if stamp < previous:
            raise CorruptFixture("event timestamps go backwards", file=EVENTS_NAME, line=number)
        previous = stamp
    return FixtureDataset(manifest=manifest, events=tuple(records))
