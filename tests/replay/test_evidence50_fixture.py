<<<<<<< HEAD
"""evidence-50 fixture: >= 50 admitted candidates and loads via load_dataset."""

import subprocess
from pathlib import Path

from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset


def test_manifest_and_timestamps() -> None:
    dataset = load_dataset(Path("tests/fixtures/replay/evidence-50"))
    assert len(dataset.events) >= 50
    stamps = [parse_ts_utc(str(event["ts_utc"])) for event in dataset.events]
    assert stamps == sorted(stamps)
    assert all(isinstance(event["mint"], str) for event in dataset.events)


def test_admitted_candidates_at_least_50() -> None:
    dataset = load_dataset(Path("tests/fixtures/replay/evidence-50"))
    admitted = {
        event["mint"] for event in dataset.events if (int(event["S"]) // 1_000_000) % 100 >= 50
    }
    assert len(admitted) >= 50


def test_negative_control_budget_too_small() -> None:

    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/measure_grok_calls.py",
            "--dataset",
            "tests/fixtures/replay/evidence-50",
            "--budget",
            "5",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 2
=======
"""Synthetic evidence-50 replay fixture (PumpGrok v4 phase 14, plan 14-04: EVT-12, GRK-11).

The fixture is SYNTHETIC: deterministic rows built from the smoke fixtures by
``tests/fixtures/replay/evidence-50/generator.py``. It is not market evidence and its
manifest says so (``"provenance": "synthetic"``).

This module proves, with no network and no skips:

1. every file the manifest lists matches its sha256, and no unlisted data file sits beside them;
2. the manifest is labeled synthetic and records the command that regenerates it;
3. the generator reproduces the bytes on disk exactly;
4. events are strictly parsed and stay in time order;
5. at least 250 raw candidates, exactly 50 admitted by the real gateway prefilter, and the
   rest rejected by the real prefilter rules in the planned mix;
6. every admitted candidate replays a recorded outcome through the real gateway, and the recorded
   set holds exactly the admitted requests, nothing more and nothing less.

A missing, corrupt, zero-admission or replay-missing input fails the test. Nothing skips.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import socket
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import GrokGateway, prefilter
from pumpgrok.grok.transport import ReplayTransport, admit_replay
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.fixtures import CorruptFixture, read_jsonl, verify_manifest
from pumpgrok.replay.recorder import ReplayLlm

DATASET = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "evidence-50"
GENERATOR = DATASET / "generator.py"
MANIFEST = DATASET / "manifest.json"
EVENTS = DATASET / "events.jsonl"
SMOKE = DATASET.parent / "smoke"
SMOKE10M = DATASET.parent / "smoke-10m"
LLM = DATASET / "llm.jsonl"
MIN_RAW = 250
ADMITTED = 50
REJECTED_MIX = {
    "too_young": 50,
    "too_old": 50,
    "market_window_closed": 50,
    "too_few_buyers": 50,
    "low_prerank": 50,
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("evidence-50 replay must never open a connection")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    assert GENERATOR.is_file(), f"generator missing: {GENERATOR}"
    spec = importlib.util.spec_from_file_location("evidence50_generator", GENERATOR)
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


def test_manifest_hashes_match_the_bytes_on_disk() -> None:
    listed = _manifest()["sha256"]
    assert set(listed) == {"events.jsonl", "llm.jsonl"}
    for name, digest in listed.items():
        target = DATASET / name
        assert target.is_file() and not target.is_symlink(), f"listed file missing: {name}"
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest, f"sha256 drift: {name}"
    stray = sorted(path.name for path in DATASET.glob("*.jsonl") if path.name not in listed)
    assert stray == [], f"unlisted data files beside the manifest: {stray}"


def test_fixture_is_labeled_synthetic_and_records_its_command(generator: ModuleType) -> None:
    manifest = _manifest()
    assert manifest.get("provenance") == "synthetic"
    assert generator.COMMAND in manifest["notes"]


def test_generator_reproduces_the_files_byte_for_byte(generator: ModuleType) -> None:
    for name, data in generator.build_files().items():
        assert (DATASET / name).read_bytes() == data, f"regeneration drift: {name}"


def test_events_parse_strictly_and_stay_in_time_order() -> None:
    rows = read_jsonl(EVENTS)
    assert rows, "events.jsonl holds no candidates"
    stamps = [parse_ts_utc(row["ts_utc"]) for row in rows]
    assert stamps == sorted(stamps)


def test_raw_rows_and_exactly_fifty_admitted_by_the_real_prefilter(
    generator: ModuleType,
) -> None:
    observations = generator.observe(read_jsonl(EVENTS))
    assert len(observations) >= MIN_RAW, f"only {len(observations)} raw candidate rows"
    admitted = [o for o in observations if prefilter(o.request.candidate, now=o.now).admit]
    assert len(admitted) == ADMITTED, f"{len(admitted)} candidates admitted, expected {ADMITTED}"


def test_rejections_follow_the_planned_mix_from_the_real_prefilter(
    generator: ModuleType,
) -> None:
    observations = generator.observe(read_jsonl(EVENTS))
    verdicts = [prefilter(o.request.candidate, now=o.now) for o in observations]
    rejected = Counter(v.reason for v in verdicts if not v.admit)
    assert dict(rejected) == REJECTED_MIX, f"rejection mix drifted: {dict(rejected)}"
    assert sum(rejected.values()) == len(observations) - ADMITTED


async def test_admitted_candidates_replay_through_the_gateway_and_nothing_else_is_recorded(
    tmp_path: Path, generator: ModuleType
) -> None:
    observations = generator.observe(read_jsonl(EVENTS))
    llm_rows = read_jsonl(LLM)
    replay = ReplayTransport(ReplayLlm.from_rows(llm_rows))

    admitted = [o for o in observations if prefilter(o.request.candidate, now=o.now).admit]
    assert len(admitted) == ADMITTED, f"{len(admitted)} candidates admitted, expected {ADMITTED}"
    needed = {generator.request_key(o.request) for o in admitted}
    recorded = {row["request_hash"] for row in llm_rows}
    assert recorded == needed, (
        f"missing records: {len(needed - recorded)}, unused records: {len(recorded - needed)}"
    )

    clock = FixtureClock(start=observations[0].now)
    gateway = GrokGateway(
        clock=clock,
        transport=replay,
        cache=ResponseCache(tmp_path / "cache.sqlite", clock),
        budget=LayeredBudget(tmp_path / "budget.sqlite", clock),
    )
    fresh = 0
    for observation in observations:
        clock.advance_to(observation.now)
        outcome = await admit_replay(gateway, replay, observation.request, clock=clock)
        if prefilter(observation.request.candidate, now=observation.now).admit:
            assert outcome.status == "fresh", (observation.request.event_id, outcome.reason)
            assert outcome.response is not None
            fresh += 1
        else:
            assert outcome.status == "prefilter_skip", observation.request.event_id
    assert fresh == len(admitted) == ADMITTED


def _copy_with_provenance(source: Path, tmp_path: Path, value: str) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    manifest["provenance"] = value
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target


def test_loader_accepts_the_synthetic_provenance_label(tmp_path: Path) -> None:
    target = _copy_with_provenance(SMOKE10M, tmp_path, "synthetic")
    assert verify_manifest(target).provenance == "synthetic"


def test_loader_refuses_an_unknown_provenance_value(tmp_path: Path) -> None:
    target = _copy_with_provenance(SMOKE10M, tmp_path, "market")
    with pytest.raises(CorruptFixture):
        verify_manifest(target)


def test_bundled_smoke_manifests_still_verify_unchanged() -> None:
    assert verify_manifest(SMOKE).provenance is None
    assert verify_manifest(SMOKE10M).provenance is None
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
