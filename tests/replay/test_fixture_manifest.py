"""INV-R-30: corrupt fixtures are refused with exit 4 before any seat starts.

Owning test for SAFETY_INVARIANTS.md section 3.4 row INV-R-30. A dataset
whose manifest digests do not match its bytes, or whose JSONL holds a
malformed line, is refused with exit 4 before any seat starts and no
ledger file is created. The smoke-10m and soak-3d manifests verify in CI
(the soak set is skipped with a clear reason when absent).

Harness: synthetic datasets plus a tampered copy of smoke-10m driven
through the real CLI entry point; no wall clock, no network.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import load_settings
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.fixtures import CorruptFixture, load_dataset, verify_manifest
from pumpgrok.tools import ensure_paper_genesis

SMOKE10M = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke-10m"
SOAK3D = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "soak-3d"


AUTHORITY_AT = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _record_complete_authority() -> None:
    """Real operator authority for every seat, recorded as the onboarding verbs record it.

    The paper genesis is written first, as ``_record_tool`` does, then the operator key and an
    allow per roster tool. Each allow is an HMAC-authenticated protected record bound to a
    ConfigChanged row in the paper ledger, the same records the startup gate reads.
    """
    oc.init_key(oc.OPERATOR_DIR)
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        ensure_paper_genesis(store, load_settings(mode="paper").risk)
        for seat in EXPECTED_SEAT_IDS:
            for tool in sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat)):
                oc.record_tool_choice(
                    store,
                    seat=seat,
                    tool=tool,
                    decision="allow",
                    now=AUTHORITY_AT,
                    operator_dir=oc.OPERATOR_DIR,
                )
    finally:
        store.close()


def _write_dataset(root: Path, name: str, files: dict[str, str]) -> Path:
    dataset = root / name
    dataset.mkdir(parents=True)
    for filename, data in files.items():
        (dataset / filename).write_text(data, encoding="utf-8")
    manifest = {
        "dataset": name,
        "recorded_from_utc": "2026-01-01T00:00:00.000Z",
        "recorded_to_utc": "2026-01-01T00:00:15.000Z",
        "seed_hint": 20260101,
        "sources": {"rest": "hand-authored"},
        "sha256": {
            filename: hashlib.sha256(data.encode("utf-8")).hexdigest()
            for filename, data in files.items()
        },
        "notes": "synthetic INV-R-30 dataset",
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dataset


def _events(n: int = 2) -> str:
    lines = []
    for index in range(n):
        lines.append(
            json.dumps(
                {
                    "ts_utc": f"2026-01-01T00:00:{index:02d}.000Z",
                    "kind": "tick",
                    "mint": "MintAAAA1111111111111111111111111111111111",
                    "S": 42000000000,
                    "T": 764608076000000,
                    "complete": False,
                    "source": "rest",
                }
            )
        )
    return "".join(line + "\n" for line in lines)


def test_corrupt_fixture_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-R-30: digest mismatch and malformed lines exit 4 with no ledger."""
    monkeypatch.chdir(tmp_path)
    _record_complete_authority()
    good = _write_dataset(tmp_path, "good", {"events.jsonl": _events()})
    assert verify_manifest(good).dataset == "good"
    assert len(load_dataset(good).events) == 2
    # Corrupt the bytes without updating the manifest: digest mismatch.
    tampered = _write_dataset(tmp_path, "tampered", {"events.jsonl": _events()})
    with (tampered / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(CorruptFixture):
        verify_manifest(tampered)
    assert main(["run", "--mode", "paper", "--once", "--replay", str(tampered)]) == 4
    assert not (tmp_path / "var" / "replay" / "tampered" / "ledger.sqlite").exists()
    # Malformed line with a matching digest: refused before any seat starts.
    broken = _write_dataset(tmp_path, "broken", {"events.jsonl": _events() + "not json\n"})
    with pytest.raises(CorruptFixture):
        load_dataset(broken)
    assert main(["run", "--mode", "paper", "--once", "--replay", str(broken)]) == 4
    assert not (tmp_path / "var" / "replay" / "broken" / "ledger.sqlite").exists()
    # Bundled CI datasets verify as shipped.
    assert verify_manifest(SMOKE10M).dataset == "smoke-10m"
    if SOAK3D.is_dir():
        verify_manifest(SOAK3D)
    else:
        pytest.skip("soak-3d dataset absent (nightly artifact)")
