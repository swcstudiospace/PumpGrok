"""Real replay-based window evaluator for backtest tuning (BT-03, BT-07).

Each candidate parameter set is applied as validated settings overrides and
replayed through the real engine and PaperAdapter over a stamp-range slice of
a recorded dataset. The tuning objective is net realized lamports over the
window: SELL filled lamports minus BUY filled lamports minus all venue fees
and network costs from the FillRecorded rows. Partial fills count at their
recorded filled amount. A window with no fills scores 0, which is an honest
zero, never an error marker.

Score inputs are replay outputs only: candidate overrides, the recorded
events in the window, and the seed. No digest, random draw, or wall-clock
reading acts as a score. Identity digests appear only through the manifest
helpers, never as scores. The module is deterministic: identical inputs give
identical scores. New money stays integer base units; Decimal appears only
inside the ledger rows this module reads, never in its arithmetic.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from pumpgrok.backtest.manifest import _resolve_dataset_dir, dataset_digest, param_set_hash
from pumpgrok.backtest.split import holdout_split, walk_forward_folds
from pumpgrok.config.settings import ExitsSettings, FilterSettings
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, event_epoch, load_dataset
from pumpgrok.supervisor.scheduler import run_once_replay

__all__ = [
    "CandidateParams",
    "EvalWindow",
    "FoldWindows",
    "ScoringKnobError",
    "evaluate_window",
    "fold_windows",
]

#: Tunable names the replay never consults, so accepting them would be a
#: hollow knob. ScoringWeights fields (audit, narrative, timing, metrics),
#: the ScoringSettings container names (weights, timing_cache_seconds), and
#: min_total_score, which lives on FilterSettings but decide_token never
#: reads: it consults only passes_filter, so the knob is inert in replay.
_SCORING_KNOBS = frozenset(
    {
        "audit",
        "narrative",
        "timing",
        "metrics",
        "weights",
        "timing_cache_seconds",
        "min_total_score",
    }
)


class ScoringKnobError(ValueError):
    """A candidate tunable names a scoring knob the replay never consults."""


def _reject_scoring_knobs(section: str, mapping: Mapping[str, Any]) -> None:
    """Refuse scoring knobs inside one override mapping, fail closed."""
    for key in mapping:
        if key in _SCORING_KNOBS:
            raise ScoringKnobError(
                f"scoring knob {key!r} in {section!r} is not tunable: "
                "the replay consults only passes_filter, so the knob is inert"
            )


class CandidateParams(BaseModel):
    """One candidate parameter set: filter and exits overrides only.

    Both mappings are optional; absent means desk defaults. Each provided
    mapping is validated by constructing the real FilterSettings or
    ExitsSettings model, so unknown fields fail. Any other top-level key,
    including scoring weights, fails through extra forbidden. Scoring knobs
    wherever they appear, including min_total_score inside filter, fail
    through the explicit blocklist with a typed validation error. Pydantic
    surfaces validator ValueError subclasses as ValidationError.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    filter: dict[str, Any] | None = None
    exits: dict[str, Any] | None = None

    @field_validator("filter")
    @classmethod
    def _check_filter(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Blocklist scoring knobs, then validate against FilterSettings."""
        if value is None:
            return None
        _reject_scoring_knobs("filter", value)
        FilterSettings(**value)
        return value

    @field_validator("exits")
    @classmethod
    def _check_exits(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Blocklist scoring knobs, then validate against ExitsSettings."""
        if value is None:
            return None
        _reject_scoring_knobs("exits", value)
        ExitsSettings(**value)
        return value

    def filter_settings(self) -> FilterSettings:
        """Desk defaults with the candidate filter overrides applied."""
        if self.filter is None:
            return FilterSettings()
        return FilterSettings(**dict(self.filter))

    def exits_settings(self) -> ExitsSettings:
        """Desk defaults with the candidate exits overrides applied."""
        if self.exits is None:
            return ExitsSettings()
        return ExitsSettings(**dict(self.exits))


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

    Fold geometry follows the split module block rule: the pre-holdout
    stamps keep their input order and are cut into N + 1 contiguous blocks;
    fold K tests block K + 1. Window ids reuse the walk_forward_folds test
    ids, and the holdout window carries the holdout id over stamps at or
    past the holdout cutoff. Validation (dataset name, fold count,
    pre-holdout depth) reuses holdout_split and walk_forward_folds, so bad
    inputs raise there instead of yielding an empty or holdout-reading
    window. Every returned window holds at least one stamp.
    """
    pairs = walk_forward_folds(stamps, dataset, n_folds)
    split = holdout_split(stamps, dataset)
    cutoff = split.holdout_start_ts
    pre = [stamp for stamp in stamps if stamp < cutoff]
    total = len(pre)
    folds: list[EvalWindow] = []
    for position in range(1, n_folds + 1):
        start_pos = (position * total) // (n_folds + 1)
        end_pos = ((position + 1) * total) // (n_folds + 1)
        end_ts = pre[end_pos] if end_pos < total else cutoff
        folds.append(
            EvalWindow(window_id=pairs[position - 1][1], start_ts=pre[start_pos], end_ts=end_ts)
        )
    return FoldWindows(
        folds=tuple(folds),
        holdout=EvalWindow(window_id=split.holdout_id, start_ts=cutoff, end_ts=float("inf")),
    )


def _int_field(payload: dict[str, object], name: str) -> int:
    value = payload.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"FillRecorded row carries non-integer {name}")
    return value


def _net_lamports(ledger_path: Path) -> int:
    """Net realized lamports from one eval ledger, fail closed.

    SELL filled lamports minus BUY filled lamports minus every venue fee and
    network cost on the FillRecorded rows, in ledger order. Rows without a
    payload mapping, non-integer money fields, or an unknown side raise
    instead of scoring a guess. A ledger with no fills nets 0.
    """
    store = LedgerStore(ledger_path)
    try:
        rows = store.read(types=["FillRecorded"], limit=None)
    finally:
        store.close()
    buy_total = 0
    sell_total = 0
    fee_total = 0
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("FillRecorded row carries no payload mapping")
        side = payload.get("side")
        filled = _int_field(payload, "filled_lamports")
        venue_fee = _int_field(payload, "venue_fee_lamports")
        network_cost = _int_field(payload, "network_cost_lamports")
        if side == "buy":
            buy_total += filled
        elif side == "sell":
            sell_total += filled
        else:
            raise ValueError(f"FillRecorded row carries unknown side {side!r}")
        fee_total += venue_fee + network_cost
    return sell_total - buy_total - fee_total


def evaluate_window(
    dataset: str | Path,
    params: CandidateParams,
    *,
    seed: int,
    ledger_path: str | Path,
    window: EvalWindow,
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
    Returns net realized lamports from the eval ledger; partial fills count
    at their recorded filled amount; zero trades score 0. Raises when the
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
        )
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return _net_lamports(Path(ledger_path))
