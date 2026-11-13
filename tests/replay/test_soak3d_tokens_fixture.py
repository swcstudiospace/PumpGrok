"""Synthetic soak-3d-tokens replay fixture (PumpGrok v4 phase 14, plan 14-04: GRK-11).

The dataset derives token facts from the soak-3d ticks (see its generator.py docstring). It is
SYNTHETIC and says so in its manifest. This module proves, with no network and no skips:

1. the manifest verifies every listed file, nothing unlisted sits beside them, and it is labeled
   ``"provenance": "synthetic"`` with the regeneration command;
2. the notes record the soak-3d source hashes, and that source verifies;
3. the generator reproduces the files byte for byte;
4. at least one candidate is admitted by the real gateway prefilter, and every row's verdict
   matches a fresh prefilter run;
5. ``llm.jsonl`` holds exactly one ok record per admitted request, keyed by the gateway request key;
6. a missing or tampered soak-3d source fails the test instead of skipping it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import socket
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from pumpgrok.grok.gateway import prefilter
from pumpgrok.replay.fixtures import CorruptFixture, read_jsonl, verify_manifest

DATASET = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "soak-3d-tokens"
SOURCE = DATASET.parent / "soak-3d"
GENERATOR = DATASET / "generator.py"
MANIFEST = DATASET / "manifest.json"
EVENTS = DATASET / "events.jsonl"
LLM = DATASET / "llm.jsonl"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("soak-3d-tokens replay must never open a connection")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    assert GENERATOR.is_file(), f"generator missing: {GENERATOR}"
    spec = importlib.util.spec_from_file_location("soak3d_tokens_generator", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so dataclasses in the generator can resolve their module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict[str, Any]:
    assert MANIFEST.is_file(), f"manifest missing: {MANIFEST}"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict), "manifest is not a JSON object"
    return manifest


def test_manifest_hashes_verify_and_no_stray_data_files() -> None:
    verify_manifest(DATASET)
    listed = _manifest()["sha256"]
    assert set(listed) == {"events.jsonl", "llm.jsonl"}
    for name, digest in listed.items():
        target = DATASET / name
        assert target.is_file() and not target.is_symlink(), f"listed file missing: {name}"
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest, f"sha256 drift: {name}"
    stray = sorted(path.name for path in DATASET.glob("*.jsonl") if path.name not in listed)
    assert stray == [], f"unlisted data files beside the manifest: {stray}"


def test_fixture_is_labeled_synthetic_and_records_its_command(generator: ModuleType) -> None:
    assert verify_manifest(DATASET).provenance == "synthetic"
    assert _manifest().get("provenance") == "synthetic"
    assert generator.COMMAND in _manifest()["notes"]


def test_notes_record_the_soak_3d_source_hashes_and_the_source_verifies() -> None:
    source_manifest = verify_manifest(SOURCE)
    assert source_manifest.dataset == "soak-3d"
    source_events = hashlib.sha256((SOURCE / "events.jsonl").read_bytes()).hexdigest()
    source_manifest_bytes = hashlib.sha256((SOURCE / "manifest.json").read_bytes()).hexdigest()
    notes = _manifest()["notes"]
    assert f"events.jsonl sha256 {source_events}" in notes
    assert f"manifest.json sha256 {source_manifest_bytes}" in notes


def test_generator_reproduces_the_files_byte_for_byte(generator: ModuleType) -> None:
    for name, data in generator.build_files().items():
        assert (DATASET / name).read_bytes() == data, f"regeneration drift: {name}"


def test_at_least_one_admitted_by_the_real_prefilter(generator: ModuleType) -> None:
    observations = generator.observe(read_jsonl(EVENTS))
    source_rows = read_jsonl(SOURCE / "events.jsonl")
    assert len(observations) == len(source_rows), "every soak-3d tick must be one candidate"
    admitted = [o for o in observations if prefilter(o.request.candidate, now=o.now).admit]
    assert len(admitted) >= 1, "the real prefilter admitted no candidate"
    for observation in observations:
        fresh = prefilter(observation.request.candidate, now=observation.now)
        assert observation.verdict == fresh, observation.request.event_id


def test_llm_records_hold_exactly_the_admitted_request_keys(generator: ModuleType) -> None:
    observations = generator.observe(read_jsonl(EVENTS))
    admitted = [o for o in observations if prefilter(o.request.candidate, now=o.now).admit]
    llm_rows = read_jsonl(LLM)
    keys = [row["request_hash"] for row in llm_rows]
    assert len(keys) == len(set(keys)), "duplicate llm records for one request key"
    assert all(row["outcome"] == "ok" for row in llm_rows)
    needed = {generator.request_key(o.request) for o in admitted}
    assert set(keys) == needed, (
        f"missing records: {len(needed - set(keys))}, unused records: {len(set(keys) - needed)}"
    )


def test_missing_source_fails_instead_of_skipping(
    generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generator, "SOURCE_DIR", tmp_path / "absent")
    with pytest.raises(CorruptFixture):
        generator.build_files()


def test_tampered_source_fails_instead_of_skipping(
    generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tampered = tmp_path / "soak-3d"
    shutil.copytree(SOURCE, tampered, ignore=shutil.ignore_patterns("__pycache__"))
    with (tampered / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    monkeypatch.setattr(generator, "SOURCE_DIR", tampered)
    with pytest.raises(CorruptFixture):
        generator.build_files()
