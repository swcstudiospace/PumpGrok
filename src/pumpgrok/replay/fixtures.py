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
import io
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

    @field_validator("dataset")
    @classmethod
    def _plain_dataset_name(cls, value: str) -> str:
        # The dataset name becomes a path component under var/replay, so it must be one plain
        # name: no separators, no "..", no hidden or absolute forms.
        if not _NAME_RE.fullmatch(value) or ".." in value:
            raise ValueError("dataset must be a plain name without separators or '..'")
        return value

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


def _load_manifest(dataset_dir: Path) -> FixtureManifest:
    """Read and validate manifest.json. The listed files' digests are checked by `_verify`."""
    manifest_path = dataset_dir / MANIFEST_NAME
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeDecodeError, ValueError):
        raise CorruptFixture("manifest is missing or not valid JSON", file=MANIFEST_NAME) from None

    try:
        return FixtureManifest.model_validate(raw)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(part) for part in err['loc'])}: {err['type']}"
            for err in exc.errors(include_input=False, include_url=False, include_context=False)
        ]
        raise CorruptFixture("manifest is invalid", file=MANIFEST_NAME, problems=problems) from None


def _verify(dataset_dir: Path) -> tuple[FixtureManifest, dict[str, bytes]]:
    """Check the manifest, every listed digest and stray data files, reading each file once.

    Returns the verified bytes. Callers parse those bytes, never the path again, so a file
    replaced after its digest was checked cannot be the one that gets parsed.
    """
    manifest = _load_manifest(dataset_dir)
    contents: dict[str, bytes] = {}
    for name, expected in sorted(manifest.sha256.items()):
        target = dataset_dir / name
        # is_symlink() before is_file(): is_file() follows links, so a listed name could otherwise
        # resolve to a file outside the dataset directory.
        if target.is_symlink():
            raise CorruptFixture("listed file is a symlink", file=name)
        if not target.is_file():
            raise CorruptFixture("listed file is missing", file=name)
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise CorruptFixture("sha256 does not match manifest", file=name)
        contents[name] = data

    for stray in sorted(dataset_dir.glob("*.jsonl")):
        if stray.name not in manifest.sha256:
            raise CorruptFixture("data file is not listed in the manifest", file=stray.name)
    return manifest, contents


def verify_manifest(dataset_dir: Path) -> FixtureManifest:
    """Check manifest shape, listed sha256 digests and stray data files. Writes nothing."""
    manifest, _ = _verify(dataset_dir)
    return manifest


def _parse_jsonl(data: bytes, name: str) -> list[dict[str, Any]]:
    """Parse every line as a JSON object. Any blank, unparseable or non-object line raises."""
    records: list[dict[str, Any]] = []
    try:
        with io.TextIOWrapper(io.BytesIO(data), encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                text = line.strip()
                if not text:
                    raise CorruptFixture("blank line", file=name, line=number)
                try:
                    record = json.loads(text, parse_constant=_reject_constant)
                except ValueError:
                    raise CorruptFixture("line is not valid JSON", file=name, line=number) from None
                if not isinstance(record, dict):
                    raise CorruptFixture("line is not a JSON object", file=name, line=number)
                records.append(record)
    except UnicodeDecodeError:
        raise CorruptFixture("file is not UTF-8", file=name) from None
    return records


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read every line of a JSONL file as a JSON object. Any bad line raises."""
    return _parse_jsonl(path.read_bytes(), path.name)


def load_dataset(dataset_dir: Path) -> FixtureDataset:
    """Verify the manifest, then parse and order-check events. Call before opening any ledger."""
    manifest, contents = _verify(dataset_dir)
    if EVENTS_NAME not in manifest.sha256:
        raise CorruptFixture("manifest does not list events.jsonl", file=MANIFEST_NAME)

    records = _parse_jsonl(contents[EVENTS_NAME], EVENTS_NAME)
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
