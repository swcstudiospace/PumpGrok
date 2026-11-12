# A sealed observation dataset is verified by the real replay loader.

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from pumpgrok.datafeed.bridge import ObservationBridge
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay import live_recorder as recorder_module
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import CorruptFixture, load_dataset
from pumpgrok.replay.live_recorder import DatasetConflict, LiveRecorder


async def _handle(_event: Event) -> None:
    pass


async def test_recorded_observation_seals_as_one_verified_replay_tick(tmp_path: Path) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = CurveObservation(
        mint="MintAAAA1111111111111111111111111111111111",
        ts_utc=clock.utc_iso(),
        s_lamports=42_000_000_000,
        t_units=764_608_076_000_000,
        complete=False,
        source="fixture-rpc",
    )
    bus = EventBus(clock=clock, handler=_handle, dlq=lambda _event: None)
    recorder = LiveRecorder(tmp_path, clock=clock)
    bridge = ObservationBridge(bus=bus, recorder=recorder)

    await bridge.publish(observation)
    assert bus.pending_p2(EventKind.curve_tick, observation.mint) is not None
    recorder.seal()
    dataset = load_dataset(tmp_path)

    assert len(dataset.events) == 1
    assert dataset.events[0] == {
        "kind": "tick",
        "mint": observation.mint,
        "ts_utc": observation.ts_utc,
        "S": observation.s_lamports,
        "T": observation.t_units,
        "complete": observation.complete,
        "source": observation.source,
    }
    assert type(dataset.events[0]["S"]) is int
    assert type(dataset.events[0]["T"]) is int
    events_path = tmp_path / "events.jsonl"
    assert (
        dataset.manifest.sha256["events.jsonl"]
        == hashlib.sha256(events_path.read_bytes()).hexdigest()
    )

    with events_path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(CorruptFixture):
        load_dataset(tmp_path)


async def test_directory_entries_are_synced_before_publish_and_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture")
    dataset_dir = tmp_path / "outer" / "dataset"
    operations: list[tuple[str, Path | None]] = []
    real_sync_dir = recorder_module._sync_directory
    real_fsync = os.fsync

    def sync_dir(path: Path) -> None:
        operations.append(("directory", path))
        real_sync_dir(path)

    def sync_file(fd: int) -> None:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            operations.append(("file", None))
        real_fsync(fd)

    class TrackingBus(EventBus):
        async def publish(self, event: Event) -> None:
            operations.append(("publish", None))
            await super().publish(event)

    monkeypatch.setattr(recorder_module, "_sync_directory", sync_dir)
    monkeypatch.setattr(os, "fsync", sync_file)
    bus = TrackingBus(clock=clock, handler=_handle, dlq=lambda _event: None)
    recorder = LiveRecorder(dataset_dir, clock=clock)
    await ObservationBridge(bus=bus, recorder=recorder).publish(observation)
    recorder.seal()

    assert operations == [
        ("directory", tmp_path),
        ("directory", tmp_path / "outer"),
        ("file", None),
        ("directory", dataset_dir),
        ("publish", None),
        ("file", None),
        ("directory", dataset_dir),
    ]
    assert len(load_dataset(dataset_dir).events) == 1


async def test_directory_sync_failure_prevents_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture")
    bus = EventBus(clock=clock, handler=_handle, dlq=lambda _event: None)
    recorder = LiveRecorder(tmp_path, clock=clock)

    def fail_directory_sync(_path: Path) -> None:
        raise OSError("directory fsync failed")

    monkeypatch.setattr(recorder_module, "_sync_directory", fail_directory_sync)
    with pytest.raises(OSError, match="directory fsync failed"):
        await ObservationBridge(bus=bus, recorder=recorder).publish(observation)
    assert bus.pending_p2(EventKind.curve_tick, observation.mint) is None
    with pytest.raises(RuntimeError, match="failed"):
        recorder.seal()


async def test_manifest_directory_sync_failure_refuses_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture")
    recorder = LiveRecorder(tmp_path, clock=clock)
    recorder.record(observation)

    attempts: list[bool] = []
    real_sync = recorder_module._sync_directory

    def fail_directory_sync(path: Path) -> None:
        attempts.append((path / "manifest.json").exists())
        if len(attempts) == 1:
            raise OSError("directory fsync failed")
        real_sync(path)

    monkeypatch.setattr(recorder_module, "_sync_directory", fail_directory_sync)
    with pytest.raises(OSError, match="directory fsync failed"):
        recorder.seal()
    assert not (tmp_path / "manifest.json").exists()
    assert attempts == [True, False]
    with pytest.raises(RuntimeError, match="failed"):
        recorder.seal()


def test_seal_refuses_unlisted_jsonl(tmp_path: Path) -> None:
    clock = FixtureClock(1_767_225_600.0)
    recorder = LiveRecorder(tmp_path, clock=clock)
    recorder.record(CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture"))
    (tmp_path / "other.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unlisted JSONL"):
        recorder.seal()
    assert not (tmp_path / "manifest.json").exists()


@pytest.mark.parametrize(
    ("conflict", "expected"),
    [
        ("invalid-name", ValueError),
        ("existing-jsonl", DatasetConflict),
        ("stray-file", DatasetConflict),
    ],
)
async def test_dataset_conflicts_are_refused_before_publication(
    tmp_path: Path, conflict: str, expected: type[Exception]
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture")
    dataset = tmp_path / (".invalid" if conflict == "invalid-name" else "dataset")
    if conflict == "existing-jsonl":
        dataset.mkdir()
        (dataset / "other.jsonl").write_text("{}\n", encoding="utf-8")
    if conflict == "stray-file":
        dataset.mkdir()
        (dataset / "notes.txt").write_text("stray\n", encoding="utf-8")
    bus = EventBus(clock=clock, handler=_handle, dlq=lambda _event: None)
    recorder = LiveRecorder(dataset, clock=clock)

    with pytest.raises(expected):
        await ObservationBridge(bus=bus, recorder=recorder).publish(observation)
    assert bus.pending_p2(EventKind.curve_tick, observation.mint) is None
    assert not (dataset / "events.jsonl").exists()
    assert not (dataset / "manifest.json").exists()


async def test_new_dataset_directory_sync_failure_prevents_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture")
    dataset_dir = tmp_path / "outer" / "dataset"
    real_sync = recorder_module._sync_directory

    def fail_parent_sync(path: Path) -> None:
        if path == tmp_path:
            raise OSError("parent directory fsync failed")
        real_sync(path)

    monkeypatch.setattr(recorder_module, "_sync_directory", fail_parent_sync)
    bus = EventBus(clock=clock, handler=_handle, dlq=lambda _event: None)
    recorder = LiveRecorder(dataset_dir, clock=clock)

    with pytest.raises(OSError, match="parent directory fsync failed"):
        await ObservationBridge(bus=bus, recorder=recorder).publish(observation)
    assert bus.pending_p2(EventKind.curve_tick, observation.mint) is None
    assert not (dataset_dir / "events.jsonl").exists()
    with pytest.raises(RuntimeError, match="failed"):
        recorder.seal()


def test_seal_rolls_back_when_replay_loader_refuses_the_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    recorder = LiveRecorder(tmp_path, clock=clock)
    recorder.record(CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture"))

    def refuse(_dataset_dir: Path) -> None:
        raise CorruptFixture("refused by test")

    monkeypatch.setattr(recorder_module, "load_dataset", refuse)
    with pytest.raises(CorruptFixture, match="refused by test"):
        recorder.seal()
    assert not (tmp_path / "manifest.json").exists()
    with pytest.raises(RuntimeError, match="failed"):
        recorder.seal()


def test_temporary_unlink_failure_rolls_back_manifest_and_syncs_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    recorder = LiveRecorder(tmp_path, clock=clock)
    recorder.record(CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture"))
    original_unlink = Path.unlink
    real_sync = recorder_module._sync_directory
    synced_manifest_states: list[bool] = []

    def fail_temporary_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.parent == tmp_path and path.name not in {"manifest.json", "events.jsonl"}:
            raise OSError("temporary unlink failed")
        original_unlink(path)

    def sync_dir(path: Path) -> None:
        synced_manifest_states.append((path / "manifest.json").exists())
        real_sync(path)

    monkeypatch.setattr(Path, "unlink", fail_temporary_unlink)
    monkeypatch.setattr(recorder_module, "_sync_directory", sync_dir)
    with pytest.raises(OSError, match="temporary unlink failed"):
        recorder.seal()
    assert not (tmp_path / "manifest.json").exists()
    assert synced_manifest_states == [False]


def test_failed_rollback_sync_reports_indeterminate_durability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    recorder = LiveRecorder(tmp_path, clock=clock)
    recorder.record(CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture"))

    def fail_directory_sync(_path: Path) -> None:
        raise OSError("directory fsync failed")

    monkeypatch.setattr(recorder_module, "_sync_directory", fail_directory_sync)
    with pytest.raises(RuntimeError, match="rollback durability is indeterminate"):
        recorder.seal()
    assert not (tmp_path / "manifest.json").exists()
    with pytest.raises(RuntimeError, match="failed"):
        recorder.seal()


def test_failed_manifest_unlink_reports_indeterminate_durability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    recorder = LiveRecorder(tmp_path, clock=clock)
    recorder.record(CurveObservation("Mint111", clock.utc_iso(), 10, 20, False, "fixture"))
    original_unlink = Path.unlink

    def fail_manifest_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "manifest.json":
            raise OSError("manifest unlink failed")
        original_unlink(path)

    def fail_directory_sync(_path: Path) -> None:
        raise OSError("directory fsync failed")

    monkeypatch.setattr(Path, "unlink", fail_manifest_unlink)
    monkeypatch.setattr(recorder_module, "_sync_directory", fail_directory_sync)
    with pytest.raises(RuntimeError, match="rollback durability is indeterminate"):
        recorder.seal()
    assert (tmp_path / "manifest.json").exists()
