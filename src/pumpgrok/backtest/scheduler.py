"""Autonomous backtest scheduler (BT-13; CONTEXT D-07).

The scheduler is event-subscribed only: a run triggers on a dataset
edge or a strategy edge, never on a timer. A run requires
``read_autonomy`` at ``autonomous-paper``; otherwise the run is refused
and the refusal is journaled into the store as a record. A repeated
edge does zero work: the idempotence key (dataset digest + strategy id
+ param hash) short-circuits before the runner is invoked. No LLM
client is constructible in this module -- the import list is part of
the contract asserted by the tests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pumpgrok.backtest.grading import DataKind, DatasetMeta, grade
from pumpgrok.backtest.store import RunStore, idempotence_key

REQUIRED_AUTONOMY = "autonomous-paper"
REFUSAL_KIND = "refused:autonomy"
RUN_KIND = "run"


@dataclass(frozen=True)
class ScheduledRun:
    """Outcome of one edge: ran, reused, or refused (with the journal record)."""

    ran: bool
    refused: bool
    record: dict[str, Any]


class Scheduler:
    """Idempotent autonomous runs over a deterministic store."""

    def __init__(
        self,
        store: RunStore,
        *,
        autonomy_level: str,
        journal: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._store = store
        self._autonomy_level = autonomy_level
        self._journal = journal or (lambda _entry: None)

    def on_edge(
        self,
        edge_kind: str,
        dataset_digest: str,
        strategy_id: str,
        param_hash: str,
        runner: Callable[[], dict[str, Any]],
    ) -> ScheduledRun:
        """Handle one dataset/strategy edge under autonomy gating and idempotence."""
        if edge_kind not in ("dataset", "strategy"):
            raise ValueError(f"unknown edge kind: {edge_kind!r}")
        key = idempotence_key(dataset_digest, strategy_id, param_hash)
        if self._autonomy_level != REQUIRED_AUTONOMY:
            record = {
                "idempotence_key": key,
                "kind": REFUSAL_KIND,
                "edge": edge_kind,
                "autonomy": self._autonomy_level,
            }
            self._journal(record)
            return ScheduledRun(ran=False, refused=True, record=record)
        cached = self._store.get(key)
        if cached is not None and cached.get("kind") == RUN_KIND:
            return ScheduledRun(ran=False, refused=False, record=cached)
        result = runner()
        run_record: dict[str, Any] = {
            "idempotence_key": key,
            "kind": RUN_KIND,
            "edge": edge_kind,
            "dataset_digest": dataset_digest,
            "strategy_id": strategy_id,
            "param_hash": param_hash,
            "result": result,
        }
        self._store.save(run_record)
        return ScheduledRun(ran=True, refused=False, record=run_record)

    def store_bytes(self) -> bytes:
        """Current store bytes (byte-stable across identical runs)."""
        if not self._store.path.is_file():
            return b""
        return self._store.path.read_bytes()


def grade_result(meta_dict: dict[str, Any]) -> dict[str, Any]:
    """Grade a persisted meta mapping through grading.py (Phase 17 consumes this)."""

    meta = DatasetMeta(
        kind=DataKind(str(meta_dict["kind"])),
        complete=bool(meta_dict["complete"]),
        duration_days=float(meta_dict["duration_days"]),
        gap_count=int(meta_dict["gap_count"]),
    )
    verdict = grade(meta)
    return {"eligible": verdict.eligible, "reasons": list(verdict.reasons)}
