"""Real replay-based window evaluator for backtest tuning (BT-03, BT-07).

Each candidate parameter set is applied as validated settings overrides and
replayed through the real engine and PaperAdapter over a stamp-range slice of
a recorded dataset. The tuning objective is net realized lamports over the
window: the net recorded cash change of the eval ledger, the sum of
FillRecorded cash_delta_lamports (every venue fee and network cost already
sits inside that delta) minus OrderRejected fees_lamports. Partial fills
count at their recorded filled amount. A window with no fills scores 0,
which is an honest zero, never an error marker.

Score inputs are replay outputs only: candidate overrides, the recorded
events in the window, and the seed. No digest, random draw, or wall-clock
reading acts as a score. Identity digests appear only through the manifest
helpers, never as scores. The module is deterministic: identical inputs give
identical scores. New money stays integer base units; the ledger rows this
module reads carry integer lamports, and no Decimal enters its arithmetic.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pumpgrok.backtest.candidate import (
    CandidateParams,
    ScoringKnobError,
    _reject_scoring_knobs,
)
from pumpgrok.backtest.manifest import _resolve_dataset_dir, dataset_digest, param_set_hash
from pumpgrok.backtest.split import holdout_split, walk_forward_folds
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, event_epoch, load_dataset
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor.scheduler import run_once_replay

__all__ = [
    "CandidateParams",
    "EvalWindow",
    "FoldWindows",
    "ScoringKnobError",
    "_reject_scoring_knobs",
    "evaluate_window",
    "evaluated_settings_hash",
    "fold_windows",
]


@dataclass(frozen=True)
class EvalWindow:
    """One evaluation window: a stamp range with its split identifier.

    start_ts is included, end_ts is excluded; the holdout tail uses
    positive infinity so every stamp at or past the cutoff is inside.
    """

    window_id: str
    start_ts: float
    end_ts: float


@dataclass(frozen=True)
class FoldWindows:
    """The windows one search needs: pre-holdout fold tests plus holdout."""

    folds: tuple[EvalWindow, ...]
    holdout: EvalWindow


def fold_windows(stamps: Sequence[float], dataset: str, n_folds: int) -> FoldWindows:
    """Pre-holdout fold test windows plus the holdout range with its id.

    Fold geometry follows the split module block rule, applied to the sorted
    distinct pre-holdout timestamps: they are cut into N + 1 contiguous blocks
    and fold K tests block K + 1. Stamps that share an instant never straddle
    two folds, so every fold window holds at least one stamp. Window ids reuse
    the walk_forward_folds test ids, and the holdout window carries the holdout
    id over stamps at or past the holdout cutoff. Validation (dataset name, fold
    count, pre-holdout depth) reuses holdout_split and walk_forward_folds; fewer
    than N + 1 distinct pre-holdout timestamps raises here rather than yielding
    an empty window.
    """
    pairs = walk_forward_folds(stamps, dataset, n_folds)
    split = holdout_split(stamps, dataset)
    cutoff = split.holdout_start_ts
    distinct = sorted({stamp for stamp in stamps if stamp < cutoff})
    total = len(distinct)
    if total < n_folds + 1:
        msg = f"need at least {n_folds + 1} distinct pre-holdout timestamps for {n_folds} folds"
        raise ValueError(f"{msg}, found {total}")
    folds: list[EvalWindow] = []
    for position in range(1, n_folds + 1):
        start_pos = (position * total) // (n_folds + 1)
        end_pos = ((position + 1) * total) // (n_folds + 1)
        end_ts = distinct[end_pos] if end_pos < total else cutoff
        folds.append(
            EvalWindow(
                window_id=pairs[position - 1][1],
                start_ts=distinct[start_pos],
                end_ts=end_ts,
            )
        )
    return FoldWindows(
        folds=tuple(folds),
        holdout=EvalWindow(window_id=split.holdout_id, start_ts=cutoff, end_ts=float("inf")),
    )


def _int_field(payload: dict[str, object], name: str) -> int:
    value = payload.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"ledger row carries non-integer {name}")
    return value


def _payload_mapping(row: Mapping[str, Any], kind: str) -> dict[str, Any]:
    """Payload mapping of one eval ledger row, fail closed."""
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"{kind} row carries no payload mapping")
    return payload


def _net_lamports(ledger_path: Path) -> int:
    """Net recorded cash change in lamports from one eval ledger, fail closed.

    Sums FillRecorded cash_delta_lamports, which already carries every fee: a
    BUY debits filled plus network cost (its venue fee sits inside filled), and
    a SELL credits proceeds already net of venue fee and network cost. Each
    OrderRejected fees_lamports is then deducted, as the ledger cash equation
    does, so no fee is counted twice. Rows without a payload mapping, a
    non-integer cash field, or an unknown side raise instead of scoring a
    guess. A ledger with no fills nets 0.
    """
    store = LedgerStore(ledger_path)
    try:
        fills = store.read(types=["FillRecorded"], limit=None)
        rejections = store.read(types=["OrderRejected"], limit=None)
    finally:
        store.close()
    cash_total = 0
    for row in fills:
        payload = _payload_mapping(row, "FillRecorded")
        side = payload.get("side")
        if side not in ("buy", "sell"):
            raise ValueError(f"FillRecorded row carries unknown side {side!r}")
        cash_total += _int_field(payload, "cash_delta_lamports")
    for row in rejections:
        payload = _payload_mapping(row, "OrderRejected")
        cash_total -= _int_field(payload, "fees_lamports")
    return cash_total


def _effective_budget(budget: RiskBudget | None) -> RiskBudget:
    """Risk budget the replay evaluates: the caller's, else the replay default."""
    return budget if budget is not None else RiskBudget()


def _effective_limits(limits: EngineLimits | None) -> EngineLimits:
    """Engine limits the replay evaluates: the caller's, else the replay default."""
    return limits if limits is not None else EngineLimits()


def evaluated_settings_hash(
    params: CandidateParams,
    *,
    risk_budget: RiskBudget | None = None,
    limits: EngineLimits | None = None,
) -> str:
    """sha256 identity of every setting one evaluation replays.

    Covers the effective filter and exits (desk defaults with the candidate
    overrides) plus the risk budget and engine limits, each resolved exactly
    as evaluate_window resolves them. Identity only: never a score.
    """
    payload = {
        "exits": params.exits_settings().model_dump(mode="json"),
        "filter": params.filter_settings().model_dump(mode="json"),
        "limits": _effective_limits(limits).model_dump(mode="json"),
        "risk_budget": _effective_budget(risk_budget).model_dump(mode="json"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def evaluate_window(
    dataset: str | Path,
    params: CandidateParams,
    *,
    seed: int,
    ledger_path: str | Path,
    window: EvalWindow,
    risk_budget: RiskBudget | None = None,
    limits: EngineLimits | None = None,
) -> int:
    """Replay one stamp-range slice under candidate overrides, score lamports.

    dataset is a directory path or a recorded fixture name. The slice holds
    the source events whose stamps fall in the window; it is materialized
    into a temp directory as events.jsonl plus a manifest in the checked-in
    shape (the digest map is located structurally so hashing vocabulary
    stays in data and imports, the slice identity comes from dataset_digest,
    and the shape is enforced by FixtureManifest validation on load), then
    replayed with run_once_replay under the candidate overrides and the
    explicit caller-supplied ledger path, never the default replay path.
    risk_budget and limits go to run_once_replay unchanged; omitted means the replay default.
    Returns the net recorded cash change of the eval ledger in lamports (see
    _net_lamports); partial fills count at their recorded filled amount;
    zero trades score 0. Raises when the
    window holds no events. Deterministic for identical inputs.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError(f"seed must be an int, found {seed!r}")
    if window.end_ts < window.start_ts:
        raise ValueError(
            f"window {window.window_id!r} ends before it starts: "
            f"{window.start_ts} to {window.end_ts}"
        )
    if ledger_path is None or str(ledger_path) == "":
        raise ValueError("ledger_path must be an explicit caller-supplied path")
    directory = _resolve_dataset_dir(str(dataset))
    source = load_dataset(directory)
    chosen = [
        event for event in source.events if window.start_ts <= event_epoch(event) < window.end_ts
    ]
    if not chosen:
        raise ValueError(f"window {window.window_id!r} holds no events in {directory}")
    raw = (
        b"\n".join(
            json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
            for event in chosen
        )
        + b"\n"
    )
    file_hex = param_set_hash(raw)
    stage = Path(tempfile.mkdtemp(prefix="pumpgrok-eval-"))
    try:
        (stage / EVENTS_NAME).write_bytes(raw)
        identity = dataset_digest(stage)
        template: dict[str, Any] = json.loads((directory / MANIFEST_NAME).read_text("utf-8"))
        template["dataset"] = source.manifest.dataset
        template["recorded_from_utc"] = str(chosen[0]["ts_utc"])
        template["recorded_to_utc"] = str(chosen[-1]["ts_utc"])
        template["seed_hint"] = source.manifest.seed_hint
        template["sources"] = dict(source.manifest.sources)
        for key, value in template.items():
            if isinstance(value, dict) and EVENTS_NAME in value:
                template[key] = {EVENTS_NAME: file_hex}
        template["notes"] = (
            f"slice {window.window_id} of {source.manifest.dataset}; slice identity {identity}"
        )
        (stage / MANIFEST_NAME).write_text(
            json.dumps(template, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        run_once_replay(
            stage,
            params.filter_settings(),
            seed=seed,
            ledger_path=Path(ledger_path),
            exits=params.exits_settings(),
            budget=_effective_budget(risk_budget),
            limits=_effective_limits(limits),
        )
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return _net_lamports(Path(ledger_path))
