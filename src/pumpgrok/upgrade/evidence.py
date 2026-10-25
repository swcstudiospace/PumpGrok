"""Promotion evidence manifest (UPG-03; CONTEXT D-06, G-05).

record_promotion writes one JSON manifest under var/upgrade/promotions/
named by the new hash, holding the candidate hash, the backtest run id,
the holdout id, the divergence result, the trial count, and the bounds
snapshot, plus a ledger JournalNote referencing the file. The record is
complete data, never a placeholder. Callers must run the promotion gate
first; the recorder trusts the gate verdict and records faithfully.

The manifest bytes are deterministic for identical inputs (sorted keys),
so the same promotion always writes the same file. Hashes are identity
only: they name the exact set and run and never act as a score, a metric,
or a verdict.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.backtest.divergence import DivergenceVerdict
from pumpgrok.core.atomic_write import atomic_write_json
from pumpgrok.upgrade.bounds import Bounds

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "bounds_snapshot",
    "promotion_manifest_path",
    "promotion_note_text",
    "record_promotion",
]

#: Default manifest directory, mirroring the trial-ledger var/ precedent.
PROMOTIONS_DIR = Path("var/upgrade/promotions")

_HASH_RE = re.compile(r"[0-9a-f]{64}")


def promotion_note_text(candidate_hash: str, manifest_name: str) -> str:
    """Journal text for a promotion record (names the new hash and its file)."""
    return f"promotion evidence {candidate_hash} recorded at {manifest_name}"


def bounds_snapshot(bounds: Bounds) -> dict[str, dict[str, list[Any]]]:
    """Freeze bounds as plain data: each key maps to its [min, max] pair.

    Keys sort so identical bounds always snapshot identically. Bool bounds
    keep their bool type; the snapshot is evidence of the exact ranges the
    gate enforced, never a score.
    """
    return {
        section: {key: [bound.minimum, bound.maximum] for key, bound in sorted(entries.items())}
        for section, entries in (
            ("filter", bounds.filter),
            ("exits", bounds.exits),
        )
    }


def promotion_manifest_path(candidate_hash: str, promotions_dir: Path | str | None = None) -> Path:
    """Manifest path for a candidate hash: <dir>/<hash>.json."""
    if not isinstance(candidate_hash, str) or not _HASH_RE.fullmatch(candidate_hash):
        raise ValueError("candidate_hash must be a 64-hex content hash")
    directory = Path(promotions_dir) if promotions_dir is not None else PROMOTIONS_DIR
    return directory / f"{candidate_hash}.json"


def record_promotion(
    store: LedgerStore,
    *,
    candidate_hash: str,
    run_id: str,
    holdout_id: str,
    divergence: DivergenceVerdict,
    trial_count: int,
    bounds: Bounds,
    promotions_dir: Path | str | None = None,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> Path:
    """Write the promotion manifest and its ledger JournalNote; return the path.

    The manifest holds the candidate hash, backtest run id, holdout id,
    divergence result, trial count, and bounds snapshot. The JournalNote
    (seat desk, note_kind note) references the manifest file. Inputs fail
    closed: a malformed hash, an empty run or holdout id, or a trial count
    below 1 raises ValueError and writes nothing.
    """
    if not isinstance(candidate_hash, str) or not _HASH_RE.fullmatch(candidate_hash):
        raise ValueError("candidate_hash must be a 64-hex content hash")
    if not run_id:
        raise ValueError("run_id must be a non-empty backtest run id")
    if not holdout_id:
        raise ValueError("holdout_id must be a non-empty holdout id")
    if isinstance(trial_count, bool) or not isinstance(trial_count, int):
        raise ValueError(f"trial_count must be an int, found {trial_count!r}")
    if trial_count < 1:
        raise ValueError(f"trial_count must be at least 1, found {trial_count}")
    manifest: dict[str, Any] = {
        "bounds_snapshot": bounds_snapshot(bounds),
        "candidate_hash": candidate_hash,
        "divergence": {
            "blocks_promotion": divergence.blocks_promotion,
            "reasons": list(divergence.reasons),
            "return_gap_pp": divergence.return_gap_pp,
            "sharpe_gap": divergence.sharpe_gap,
        },
        "holdout_id": holdout_id,
        "run_id": run_id,
        "trial_count": trial_count,
    }
    path = promotion_manifest_path(candidate_hash, promotions_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, manifest)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == manifest, "manifest must round-trip through JSON"
    store.append(
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
        idempotency_key=f"promotion-evidence|{candidate_hash}|{ts_utc}",
        type="JournalNote",
        payload={
            "source": source,
            "seat": "desk",
            "note_kind": "note",
            "text": promotion_note_text(candidate_hash, path.name),
            "refs": [],
        },
    )
    return path
