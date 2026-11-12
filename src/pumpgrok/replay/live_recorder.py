"""Durably record curve observations in the existing replay dataset format."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import IO

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.datafeed.resync import Gap
from pumpgrok.replay.clock import Clock, parse_ts_utc
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, FixtureManifest, load_dataset

# Closed feed gaps. The file exists only once a gap has closed.
GAPS_NAME = "gaps.jsonl"
# The only data files a live dataset may hold. Any other *.jsonl is refused at seal time.
_DATA_FILES = (EVENTS_NAME, GAPS_NAME)


class DatasetConflict(PumpgrokError):
    """The dataset directory already holds entries, so no fresh dataset can start there."""

    code = "dataset_conflict"


def _sync_directory(path: Path) -> None:
    """Persist directory entries before acknowledging their creation."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_directory(path: Path) -> None:
    """Create each missing ancestor and persist its entry in its parent."""
    if path.is_dir():
        return
    _ensure_directory(path.parent)
    try:
        path.mkdir()
    except FileExistsError:
        if not path.is_dir():
            raise
    else:
        _sync_directory(path.parent)


def _require_fresh_dataset(path: Path) -> None:
    """Refuse any existing entry before the first observation is accepted."""
    if not path.exists():
        return
    if not path.is_dir():
        raise DatasetConflict("dataset path is not a directory", dataset=path.name)
    entries = sorted(entry.name for entry in path.iterdir())
    if entries:
        raise DatasetConflict("dataset directory is not empty", dataset=path.name, entries=entries)


def _write_durably(stream: IO[bytes], data: bytes) -> None:
    if stream.write(data) != len(data):
        raise OSError("incomplete observation write")
    stream.flush()
    os.fsync(stream.fileno())


def _append_record(path: Path, data: bytes) -> None:
    """Append one durable record. A new file's bytes are durable before its name is synced.

    The first observation is published only after this returns, so a crash cannot leave a
    published tick whose file name or bytes are not yet durable.
    """
    if path.exists():
        with path.open("ab") as stream:
            _write_durably(stream, data)
        return
    with path.open("xb") as stream:
        _write_durably(stream, data)
    _sync_directory(path.parent)


def _digest_data_files(dataset_dir: Path) -> dict[str, str]:
    """Digest every permitted data file. Any other *.jsonl is refused, never omitted."""
    if any(path.name not in _DATA_FILES for path in dataset_dir.glob("*.jsonl")):
        raise ValueError("dataset contains an unlisted JSONL file")
    return {
        name: hashlib.sha256((dataset_dir / name).read_bytes()).hexdigest()
        for name in _DATA_FILES
        if (dataset_dir / name).exists()
    }


class LiveRecorder:
    """Append ticks before publication and seal their exact bytes with a manifest."""

    def __init__(self, dataset_dir: Path, *, clock: Clock) -> None:
        self.dataset_dir = dataset_dir
        self.clock = clock
        self._first_utc: str | None = None
        self._last_utc: str | None = None
        self._last_epoch: float | None = None
        self._sources: dict[str, str] = {}
        self._failed = False
        self._sealed = False
        self._claimed = False

    def record(self, observation: CurveObservation) -> None:
        if self._sealed or self._failed:
            raise RuntimeError("recorder is sealed or failed")
        epoch = observation.validate()
        if self._last_epoch is not None and epoch < self._last_epoch:
            raise ValueError("observation timestamps must not go backwards")
        FixtureManifest._plain_dataset_name(self.dataset_dir.name)
        data = (json.dumps(observation.replay_tick(), separators=(",", ":")) + "\n").encode("utf-8")
        self._persist(EVENTS_NAME, data)
        if self._first_utc is None:
            self._first_utc = observation.ts_utc
        self._last_utc = observation.ts_utc
        self._last_epoch = epoch
        self._sources[observation.source] = observation.source

    def record_gap(self, gap: Gap) -> None:
        """Durably append one closed feed gap to gaps.jsonl. An open gap has no end to record."""
        if self._sealed or self._failed:
            raise RuntimeError("recorder is sealed or failed")
        if gap.end_ts_utc is None:
            raise ValueError("only closed gaps are recorded")
        if parse_ts_utc(gap.end_ts_utc) < parse_ts_utc(gap.start_ts_utc):
            raise ValueError("gap ends before it starts")
        FixtureManifest._plain_dataset_name(self.dataset_dir.name)
        line = {
            "start_ts_utc": gap.start_ts_utc,
            "end_ts_utc": gap.end_ts_utc,
            "reason": gap.reason,
        }
        data = (json.dumps(line, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        self._persist(GAPS_NAME, data)

    def _claim_dataset(self) -> None:
        """Refuse a directory holding foreign entries before this recorder's first write."""
        if not self._claimed:
            # Refused before anything is written, so a conflicting directory stays untouched.
            _require_fresh_dataset(self.dataset_dir)
            self._claimed = True

    def _persist(self, name: str, data: bytes) -> None:
        """Durably append to one data file. Any OSError fails the recorder for good."""
        self._claim_dataset()
        try:
            _ensure_directory(self.dataset_dir)
            if (self.dataset_dir / MANIFEST_NAME).exists():
                raise FileExistsError("dataset is already sealed")
            _append_record(self.dataset_dir / name, data)
        except OSError:
            self._failed = True
            raise

    def seal(self) -> None:
        if self._sealed or self._failed:
            raise RuntimeError("recorder is sealed or failed")
        if self._first_utc is None or self._last_utc is None:
            raise ValueError("cannot seal a dataset without observations")
        linked = False
        try:
            manifest = FixtureManifest(
                dataset=self.dataset_dir.name,
                recorded_from_utc=self._first_utc,
                recorded_to_utc=self._last_utc,
                seed_hint=0,
                sources=self._sources,
                sha256=_digest_data_files(self.dataset_dir),
                notes="Read-only curve observations",
            )
            encoded = (manifest.model_dump_json(indent=2) + "\n").encode("utf-8")
            with tempfile.NamedTemporaryFile(dir=self.dataset_dir, delete=False) as stream:
                temporary = Path(stream.name)
                try:
                    if stream.write(encoded) != len(encoded):
                        raise OSError("incomplete manifest write")
                    stream.flush()
                    os.fsync(stream.fileno())
                    os.link(temporary, self.dataset_dir / MANIFEST_NAME)
                    linked = True
                finally:
                    temporary.unlink(missing_ok=True)
            # The replay loader is the acceptance test: a dataset it refuses is never sealed.
            load_dataset(self.dataset_dir)
            _sync_directory(self.dataset_dir)
        except BaseException:
            self._failed = True
            if linked:
                try:
                    (self.dataset_dir / MANIFEST_NAME).unlink()
                    _sync_directory(self.dataset_dir)
                except BaseException as cleanup_error:
                    raise RuntimeError(
                        "manifest rollback durability is indeterminate"
                    ) from cleanup_error
            raise
        self._sealed = True
