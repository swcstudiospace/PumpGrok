"""Durably record curve observations in the existing replay dataset format."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.replay.clock import Clock
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, FixtureManifest


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
        data = (json.dumps(observation.replay_tick(), separators=(",", ":")) + "\n").encode("utf-8")
        try:
            self.dataset_dir.mkdir(parents=True, exist_ok=True)
            if (self.dataset_dir / MANIFEST_NAME).exists():
                raise FileExistsError("dataset is already sealed")
            mode = "xb" if self._first_utc is None else "ab"
            with (self.dataset_dir / EVENTS_NAME).open(mode) as stream:
                if stream.write(data) != len(data):
                    raise OSError("incomplete observation write")
                stream.flush()
                os.fsync(stream.fileno())
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
        try:
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
                finally:
                    temporary.unlink(missing_ok=True)
        except (OSError, ValueError):
            self._failed = True
            raise
        self._sealed = True
