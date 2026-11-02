"""Backtest run manifest: identity for one backtest run (BT-01).

A run id pins the whole-dataset digest, the seed, the FilterSettings hash,
the parameter-set hash and the code version. The run id is the sha256 of the
canonical JSON of the manifest, so identical inputs always produce identical
ids and any changed byte in any dataset file produces a new id.

Money fields are not involved; every hash is a lowercase hex string. The
manifest carries no wall-clock timestamps, keeping reports byte-identical
for identical inputs. Datasets are addressed either as a directory path or
as a fixture name resolved under tests/fixtures/replay. The code version
defaults to the git HEAD sha read from the checkout files, with UNKNOWN-DEV
only when git is unavailable. Live trading stays refused; this module
places no orders and opens no network connections.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pumpgrok.backtest.candidate import CandidateParams, param_set_mapping
from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.idempotency import canonical_json

RUN_ID_VERSION = "1"

UNKNOWN_DEV = "UNKNOWN-DEV"

_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_SHA_RE = re.compile(r"[0-9a-f]{40}")


class RunManifest(BaseModel):
    """Frozen identity of one backtest run.

    run_id derives from every other field, so two manifests with equal
    inputs carry equal run ids and any input change carries a new run id.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id_version: str = RUN_ID_VERSION
    dataset: str = Field(min_length=1)
    dataset_digest: str
    seed: int
    filter_settings_hash: str
    param_set_hash: str
    code_version: str = Field(min_length=1)
    run_id: str

    @field_validator("run_id_version")
    @classmethod
    def _known_version(cls, value: str) -> str:
        if value != RUN_ID_VERSION:
            raise ValueError(f"run_id_version must be {RUN_ID_VERSION}")
        return value

    @field_validator("dataset_digest", "filter_settings_hash", "param_set_hash", "run_id")
    @classmethod
    def _hex_digests(cls, value: str) -> str:
        if not _DIGEST_RE.fullmatch(value):
            raise ValueError("hashes must be 64 lowercase hex characters")
        return value

    @field_validator("seed")
    @classmethod
    def _plain_seed(cls, value: int) -> int:
        if isinstance(value, bool):
            raise ValueError("seed must be an int, not a bool")
        return value


def file_digest(data: bytes) -> str:
    """sha256 hex of one file's bytes: the per-file digest dataset_digest folds."""
    return hashlib.sha256(data).hexdigest()


def dataset_digest(dataset_dir: Path | str) -> str:
    """sha256 over every file in a dataset directory.

    File names sort ascending; each file contributes its own sha256 hex;
    the digest is the sha256 of the concatenated per-file hex strings.
    """
    root = Path(dataset_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"dataset directory not found: {root}")
    names = sorted(entry.name for entry in root.iterdir() if entry.is_file())
    if not names:
        raise ValueError(f"dataset directory holds no files: {root}")
    per_file = [file_digest((root / name).read_bytes()) for name in names]
    return hashlib.sha256("".join(per_file).encode("utf-8")).hexdigest()


def _git_dir(start: Path) -> Path | None:
    """Locate the git dir for a path, following worktree gitfiles, else None."""
    for parent in (start, *start.parents):
        dotgit = parent / ".git"
        if dotgit.is_dir():
            return dotgit
        if dotgit.is_file():
            try:
                text = dotgit.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return None
            if not text.startswith("gitdir: "):
                return None
            target = (dotgit.parent / text[len("gitdir: ") :].strip()).resolve()
            return target if target.is_dir() else None
    return None


def _read_ref(gitdir: Path, common: Path, ref: str) -> str | None:
    """Resolve a ref to a commit sha via loose files then packed-refs, else None."""
    for base in (gitdir, common):
        try:
            text = base.joinpath(*ref.split("/")).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if _SHA_RE.fullmatch(text):
            return text
    for base in (common, gitdir):
        try:
            packed = (base / "packed-refs").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in packed.splitlines():
            if line.startswith(("#", "^")) or " " not in line:
                continue
            sha, name = line.split(" ", 1)
            if name == ref and _SHA_RE.fullmatch(sha):
                return sha
    return None


def default_code_version() -> str:
    """git HEAD sha for this checkout, or UNKNOWN-DEV when git is unavailable."""
    gitdir = _git_dir(Path(__file__).resolve())
    if gitdir is None:
        return UNKNOWN_DEV
    try:
        common_text = (gitdir / "commondir").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        common_text = ""
    common = (gitdir / common_text).resolve() if common_text else gitdir
    if not common.is_dir():
        common = gitdir
    try:
        head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return UNKNOWN_DEV
    if head.startswith("ref: "):
        sha = _read_ref(gitdir, common, head[len("ref: ") :])
        return sha if sha is not None else UNKNOWN_DEV
    return head if _SHA_RE.fullmatch(head) else UNKNOWN_DEV


def filter_settings_hash(settings: FilterSettings) -> str:
    """sha256 over the stable JSON of FilterSettings (sorted keys, fixed separators).

    Settings thresholds are floats by definition, so this hash uses plain
    JSON rather than canonical_json, which forbids float leaves. The output
    is deterministic for identical settings on any host.
    """
    raw = json.dumps(settings.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def param_set_hash(data: bytes) -> str:
    """Canonical identity of one parameter-set file: the CandidateParams content hash.

    The bytes parse into the same CandidateParams model the backtest CLI validates,
    so whitespace and key order never change the identity. The value is the hash the
    search winner, the promotion gate, the evidence and the active-set ledger carry.
    Invalid bytes raise ValueError.
    """
    return CandidateParams(**param_set_mapping(data)).content_hash


def run_id(manifest: RunManifest) -> str:
    """sha256 over the canonical JSON of a manifest, excluding run_id itself."""
    payload = manifest.model_dump(exclude={"run_id"})
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _resolve_dataset_dir(dataset: str) -> Path:
    """Return the directory for a dataset path or fixture name, else raise."""
    if not dataset:
        raise ValueError("dataset must be a non-empty path or fixture name")
    candidate = Path(dataset)
    if candidate.is_dir():
        return candidate
    for parent in Path(__file__).resolve().parents:
        fixture = parent / "tests" / "fixtures" / "replay" / dataset
        if fixture.is_dir():
            return fixture
    raise FileNotFoundError(f"dataset not found as a directory or fixture: {dataset}")


def build_manifest(
    dataset: str,
    seed: int,
    filter_settings_hash: str,
    param_set_hash: str,
    code_version: str | None = None,
) -> RunManifest:
    """Build the frozen manifest for a dataset and derive its run id.

    dataset is either a directory path or a fixture name resolved under
    tests/fixtures/replay. code_version defaults to the git HEAD sha via
    default_code_version when omitted.
    """
    payload: dict[str, Any] = {
        "run_id_version": RUN_ID_VERSION,
        "dataset": dataset,
        "dataset_digest": dataset_digest(_resolve_dataset_dir(dataset)),
        "seed": seed,
        "filter_settings_hash": filter_settings_hash,
        "param_set_hash": param_set_hash,
        "code_version": default_code_version() if code_version is None else code_version,
    }
    manifest_id = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return RunManifest(**payload, run_id=manifest_id)
