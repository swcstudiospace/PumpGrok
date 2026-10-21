"""Manifest-gated fixture loading (INV-R-30, T-01-51)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from pumpgrok.replay import CorruptFixture, load_dataset, verify_manifest
from pumpgrok.replay.fixtures import read_jsonl

SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"


def _copy_smoke(tmp_path: Path) -> Path:
    target = tmp_path / "dataset"
    shutil.copytree(SMOKE, target)
    return target


def _rehash_events(dataset: Path) -> None:
    raw = json.loads((dataset / "manifest.json").read_text())
    digest = hashlib.sha256((dataset / "events.jsonl").read_bytes()).hexdigest()
    raw["sha256"]["events.jsonl"] = digest
    (dataset / "manifest.json").write_text(json.dumps(raw))


def test_smoke_fixture_passes_manifest_verification() -> None:
    manifest = verify_manifest(SMOKE)
    assert manifest.dataset == "smoke"
    assert list(manifest.sha256) == ["events.jsonl"]


def test_smoke_fixture_loads_four_ordered_events() -> None:
    dataset = load_dataset(SMOKE)
    assert len(dataset.events) == 4
    assert [event["kind"] for event in dataset.events] == ["tick"] * 4


def test_tampered_byte_raises_corrupt_fixture_and_creates_no_ledger(tmp_path: Path) -> None:
    dataset = _copy_smoke(tmp_path)
    events = dataset / "events.jsonl"
    data = bytearray(events.read_bytes())
    data[10] ^= 0x01
    events.write_bytes(bytes(data))

    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    with pytest.raises(CorruptFixture) as excinfo:
        load_dataset(dataset)
    assert excinfo.value.code == "corrupt_fixture"
    assert excinfo.value.fields["file"] == "events.jsonl"
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before
    assert not list(tmp_path.rglob("*.sqlite*"))


def test_unlisted_jsonl_file_is_rejected(tmp_path: Path) -> None:
    dataset = _copy_smoke(tmp_path)
    (dataset / "extra.jsonl").write_text('{"ts_utc":"2026-01-01T00:00:00.000Z"}\n')
    with pytest.raises(CorruptFixture) as excinfo:
        verify_manifest(dataset)
    assert excinfo.value.fields["file"] == "extra.jsonl"


def test_missing_listed_file_is_rejected(tmp_path: Path) -> None:
    dataset = _copy_smoke(tmp_path)
    (dataset / "events.jsonl").unlink()
    with pytest.raises(CorruptFixture) as excinfo:
        verify_manifest(dataset)
    assert excinfo.value.fields["file"] == "events.jsonl"


def test_manifest_with_path_traversal_name_is_rejected(tmp_path: Path) -> None:
    dataset = _copy_smoke(tmp_path)
    raw = json.loads((dataset / "manifest.json").read_text())
    raw["sha256"] = {"../events.jsonl": raw["sha256"]["events.jsonl"]}
    (dataset / "manifest.json").write_text(json.dumps(raw))
    with pytest.raises(CorruptFixture) as excinfo:
        verify_manifest(dataset)
    assert any(problem.startswith("sha256") for problem in excinfo.value.fields["problems"])


def test_manifest_error_report_carries_no_input_values(tmp_path: Path) -> None:
    dataset = _copy_smoke(tmp_path)
    raw = json.loads((dataset / "manifest.json").read_text())
    raw["seed_hint"] = "SECRET-VALUE-DO-NOT-ECHO"  # pragma: allowlist secret: planted no-echo value
    (dataset / "manifest.json").write_text(json.dumps(raw))
    with pytest.raises(CorruptFixture) as excinfo:
        verify_manifest(dataset)
    assert "SECRET-VALUE-DO-NOT-ECHO" not in repr(excinfo.value.fields)  # pragma: allowlist secret
    assert "SECRET-VALUE-DO-NOT-ECHO" not in str(excinfo.value)  # pragma: allowlist secret


def test_out_of_order_timestamps_are_rejected(tmp_path: Path) -> None:
    dataset = _copy_smoke(tmp_path)
    lines = (dataset / "events.jsonl").read_text().splitlines()
    lines[0], lines[1] = lines[1], lines[0]
    (dataset / "events.jsonl").write_text("\n".join(lines) + "\n")
    _rehash_events(dataset)
    with pytest.raises(CorruptFixture, match="backwards"):
        load_dataset(dataset)


def test_strict_reader_raises_on_corrupt_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ok": 1}\n{not json\n{"ok": 2}\n')
    with pytest.raises(CorruptFixture) as excinfo:
        read_jsonl(path)
    assert excinfo.value.fields == {"file": "bad.jsonl", "line": 2}


def test_strict_reader_rejects_non_finite_numbers_and_non_objects(tmp_path: Path) -> None:
    path = tmp_path / "odd.jsonl"
    path.write_text('{"x": NaN}\n')
    with pytest.raises(CorruptFixture):
        read_jsonl(path)
    path.write_text("[1, 2]\n")
    with pytest.raises(CorruptFixture):
        read_jsonl(path)


def test_symlinked_listed_file_is_refused(tmp_path: Path) -> None:
    # A listed name must resolve to a file inside the dataset directory, never through a link.
    dataset = _copy_smoke(tmp_path)
    outside = tmp_path / "outside.jsonl"
    shutil.copyfile(dataset / "events.jsonl", outside)
    (dataset / "events.jsonl").unlink()
    (dataset / "events.jsonl").symlink_to(outside)
    with pytest.raises(CorruptFixture, match="symlink"):
        load_dataset(dataset)
