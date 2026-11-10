"""Durably record curve observations in the existing replay dataset format."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.replay.clock import Clock
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, FixtureManifest


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

    def record(self, observation: CurveObservation) -> None:
        if self._sealed or self._failed:
            raise RuntimeError("recorder is sealed or failed")
        epoch = observation.validate()
        if self._last_epoch is not None and epoch < self._last_epoch:
            raise ValueError("observation timestamps must not go backwards")
        FixtureManifest._plain_dataset_name(self.dataset_dir.name)
        data = (json.dumps(observation.replay_tick(), separators=(",", ":")) + "\n").encode("utf-8")
        try:
            _ensure_directory(self.dataset_dir)
            if (self.dataset_dir / MANIFEST_NAME).exists():
                raise FileExistsError("dataset is already sealed")
            if self._first_utc is None and any(self.dataset_dir.glob("*.jsonl")):
                raise FileExistsError("dataset already contains JSONL files")
            mode = "xb" if self._first_utc is None else "ab"
            with (self.dataset_dir / EVENTS_NAME).open(mode) as stream:
                if stream.write(data) != len(data):
                    raise OSError("incomplete observation write")
                stream.flush()
                os.fsync(stream.fileno())
            _sync_directory(self.dataset_dir)
        except OSError:
            self._failed = True
            raise
        if self._first_utc is None:
            self._first_utc = observation.ts_utc
        self._last_utc = observation.ts_utc
        self._last_epoch = epoch
        self._sources[observation.source] = observation.source

    def seal(self) -> None:
        if self._sealed or self._failed:
            raise RuntimeError("recorder is sealed or failed")
        if self._first_utc is None or self._last_utc is None:
            raise ValueError("cannot seal a dataset without observations")
        linked = False
        try:
            if any(path.name != EVENTS_NAME for path in self.dataset_dir.glob("*.jsonl")):
                raise ValueError("dataset contains an unlisted JSONL file")
            data = (self.dataset_dir / EVENTS_NAME).read_bytes()
            manifest = FixtureManifest(
                dataset=self.dataset_dir.name,
                recorded_from_utc=self._first_utc,
                recorded_to_utc=self._last_utc,
                seed_hint=0,
                sources=self._sources,
                sha256={EVENTS_NAME: hashlib.sha256(data).hexdigest()},
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
