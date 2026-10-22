"""Regression tests for Greptile finding 1: a fixture dataset name must not escape the replay dir.

A manifest with dataset ".." used to resolve the default ledger to var/ledger.sqlite, which the
replay reset then deleted. Names are now validated before any file is removed or written.
"""

import json
import shutil
from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.replay.fixtures import CorruptFixture, FixtureManifest, load_dataset
from pumpgrok.replay.runner import run_replay

SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"
SENTINEL_BYTES = b"real paper ledger contents, must survive"


def _copy_with_dataset(dest: Path, dataset: str) -> Path:
    """Copy the smoke fixture and rewrite only manifest.dataset (manifest.json is not hashed)."""
    shutil.copytree(SMOKE, dest)
    manifest_path = dest / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["dataset"] = dataset
    manifest_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return dest


@pytest.mark.parametrize(
    "dataset",
    ["..", "a/b", "../escape", "/abs/path", "nested/../x", "", ".hidden", "a\\b", "x..y"],
)
def test_manifest_rejects_non_plain_dataset_names(dataset: str) -> None:
    raw = json.loads((SMOKE / "manifest.json").read_text(encoding="utf-8"))
    raw["dataset"] = dataset
    with pytest.raises(ValueError):
        FixtureManifest.model_validate(raw)


@pytest.mark.parametrize("dataset", ["..", "a/b", "/abs/path", ".hidden", ""])
def test_replay_rejects_dataset_before_any_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dataset: str
) -> None:
    monkeypatch.chdir(tmp_path)
    replay_dir = tmp_path / "var" / "replay"
    replay_dir.mkdir(parents=True)
    # Stands where var/replay/<dataset>/ledger.sqlite would resolve for "..".
    outside = tmp_path / "var" / "ledger.sqlite"
    outside.write_bytes(SENTINEL_BYTES)
    fixture = _copy_with_dataset(tmp_path / "fixture", dataset)

    with pytest.raises(CorruptFixture):
        run_replay(fixture, FilterSettings())

    assert outside.read_bytes() == SENTINEL_BYTES
    assert not list(replay_dir.iterdir())


def test_ledger_outside_replay_dir_survives_dotdot_replay_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "var" / "replay").mkdir(parents=True)
    real_ledger = tmp_path / "var" / "ledger.sqlite"
    real_ledger.write_bytes(SENTINEL_BYTES)
    wal = tmp_path / "var" / "ledger.sqlite-wal"
    wal.write_bytes(b"wal sidecar")
    fixture = _copy_with_dataset(tmp_path / "fixture", "..")

    with pytest.raises(CorruptFixture):
        run_replay(fixture, FilterSettings())

    assert real_ledger.read_bytes() == SENTINEL_BYTES
    assert wal.read_bytes() == b"wal sidecar"


def test_plain_dataset_name_still_loads(tmp_path: Path) -> None:
    fixture = _copy_with_dataset(tmp_path / "fixture", "smoke-copy_1.v2")
    assert load_dataset(fixture).manifest.dataset == "smoke-copy_1.v2"
