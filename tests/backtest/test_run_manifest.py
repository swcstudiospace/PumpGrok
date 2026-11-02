"""BT-01: the run manifest pins dataset, seed, settings, params and code version.

The manifest holds the whole-dataset digest over every file in the dataset
directory, the seed, the FilterSettings hash, the parameter-set hash and the
code version. The run id is deterministic for identical inputs, and changing
one byte of any dataset file changes the run id. Checked-in fixtures are
only read; every mutation happens on tmp_path copies.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from pumpgrok.backtest.candidate import CandidateParams
from pumpgrok.backtest.manifest import (
    RUN_ID_VERSION,
    RunManifest,
    build_manifest,
    dataset_digest,
    default_code_version,
    filter_settings_hash,
    param_set_hash,
    run_id,
)
from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.idempotency import canonical_json

SMOKE10M = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke-10m"
SEED = 20260101
CODE_VERSION = "TESTCODEVERSION"
PARAMS_RAW = json.dumps({"filter": {"min_unique_buyers": 5}}, sort_keys=True).encode("utf-8")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")

FILTER_HEX = "filter_settings_hash"
PARAM_HEX = "param_set_hash"


def _copy_dataset(dest: Path) -> Path:
    """Copy the checked-in smoke-10m fixture to dest; the original is never written."""
    shutil.copytree(SMOKE10M, dest)
    return dest


def _build(root: str) -> RunManifest:
    return build_manifest(
        root,
        SEED,
        filter_settings_hash(FilterSettings()),
        param_set_hash(PARAMS_RAW),
        CODE_VERSION,
    )


def _expected_digest(root: Path) -> str:
    """Independent recomputation: sorted names, concatenated per-file sha256, hashed."""
    parts = []
    for name in sorted(entry.name for entry in root.iterdir() if entry.is_file()):
        parts.append(hashlib.sha256((root / name).read_bytes()).hexdigest())
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()


def _flip_first_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[0] ^= 0x01
    path.write_bytes(bytes(data))


def test_manifest_holds_all_inputs(tmp_path: Path) -> None:
    """BT-01: manifest carries dataset digest, seed, settings, params and code hash."""
    root = _copy_dataset(tmp_path / "work")
    manifest = _build(str(root))
    assert manifest.dataset == str(root)
    assert manifest.dataset_digest == dataset_digest(root)
    assert manifest.dataset_digest == _expected_digest(root)
    assert manifest.seed == SEED
    assert manifest.filter_settings_hash == filter_settings_hash(FilterSettings())
    assert manifest.param_set_hash == CandidateParams(**json.loads(PARAMS_RAW)).content_hash
    assert manifest.code_version == CODE_VERSION
    assert manifest.run_id_version == RUN_ID_VERSION
    assert _DIGEST_RE.fullmatch(manifest.run_id)


def test_run_id_deterministic_for_identical_inputs(tmp_path: Path) -> None:
    """BT-01: identical inputs always produce the identical run id."""
    root = _copy_dataset(tmp_path / "work")
    first = _build(str(root))
    second = _build(str(root))
    assert first == second
    assert first.run_id == second.run_id
    assert run_id(first) == first.run_id
    payload = {
        "run_id_version": first.run_id_version,
        "dataset": first.dataset,
        "dataset_digest": first.dataset_digest,
        "seed": first.seed,
        FILTER_HEX: first.filter_settings_hash,
        PARAM_HEX: first.param_set_hash,
        "code_version": first.code_version,
    }
    assert hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest() == first.run_id


def test_one_changed_byte_changes_run_id(tmp_path: Path) -> None:
    """BT-01: a single changed byte in any dataset file changes the run id."""
    baseline = _build(str(_copy_dataset(tmp_path / "base")))
    names = sorted(entry.name for entry in SMOKE10M.iterdir() if entry.is_file())
    assert names, "smoke-10m fixture holds no files to tamper"
    for name in names:
        root = _copy_dataset(tmp_path / f"case-{name}")
        _flip_first_byte(root / name)
        mutated = _build(str(root))
        assert mutated.dataset_digest != baseline.dataset_digest, name
        assert mutated.run_id != baseline.run_id, name


def test_fixture_name_resolves_to_checked_in_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BT-01: a fixture name resolves under tests/fixtures/replay."""
    monkeypatch.chdir(tmp_path)
    manifest = _build("smoke-10m")
    assert manifest.dataset == "smoke-10m"
    assert manifest.dataset_digest == dataset_digest(SMOKE10M)


def test_unknown_dataset_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """BT-01: an unknown dataset name fails loudly instead of hashing nothing."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        build_manifest(
            "NO-SUCH-DATASET",
            SEED,
            filter_settings_hash(FilterSettings()),
            param_set_hash(PARAMS_RAW),
            CODE_VERSION,
        )


def test_filter_settings_hash_distinguishes() -> None:
    """BT-01: the settings hash is stable and sensitive to settings changes."""
    assert filter_settings_hash(FilterSettings()) == filter_settings_hash(FilterSettings())
    other = FilterSettings(min_unique_buyers=6)
    assert filter_settings_hash(other) != filter_settings_hash(FilterSettings())


def test_default_code_version_shape() -> None:
    """BT-01: the code version is a commit sha, or UNKNOWN-DEV off git."""
    code = default_code_version()
    assert code == "UNKNOWN-DEV" or re.fullmatch(r"[0-9a-f]{40}", code)


def test_run_manifest_is_frozen(tmp_path: Path) -> None:
    """BT-01: the manifest cannot be mutated after construction."""
    manifest = _build(str(_copy_dataset(tmp_path / "work")))
    with pytest.raises(ValidationError):
        manifest.seed = SEED + 1  # type: ignore[misc]


def test_param_set_hash_is_the_candidate_content_hash() -> None:
    """Spelling does not change identity; the value is the CandidateParams content hash."""
    mapping = {"filter": {"min_unique_buyers": 7, "require_metadata": False}}
    compact = json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode("utf-8")
    reordered = json.dumps(
        {"filter": {"require_metadata": False, "min_unique_buyers": 7}}, indent=4
    ).encode("utf-8")
    assert compact != reordered
    assert param_set_hash(compact) == param_set_hash(reordered)
    assert param_set_hash(compact) == CandidateParams(**mapping).content_hash


def test_param_set_hash_separates_different_sets() -> None:
    """Two different parameter sets keep different identities."""
    first = json.dumps({"filter": {"min_unique_buyers": 7}}).encode("utf-8")
    second = json.dumps({"filter": {"min_unique_buyers": 8}}).encode("utf-8")
    assert param_set_hash(first) != param_set_hash(second)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[1]",
        b'{"top_k": 10}',
        b'{"filter": {"min_total_score": 0.5}}',
        b'{"filter": {"min_unique_buyers": 5.0}}',
    ],
)
def test_param_set_hash_refuses_invalid_bytes(raw: bytes) -> None:
    """Invalid parameter-set bytes raise ValueError, the error the CLI maps to a usage error."""
    with pytest.raises(ValueError):
        param_set_hash(raw)
