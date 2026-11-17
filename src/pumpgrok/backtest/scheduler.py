"""Autonomous backtest edges (BT-13).

``run_edge`` runs one dataset or strategy edge when the ledger autonomy level
is autonomous-paper, skips with no write otherwise, and does no work when the
edge key is already stored. Publication is a JournalNote of NoteKind verdict
through the existing journal note writer (owner decision 6, option A). The
ledger source is ``paper``, an existing ``SOURCES`` value. There is no timer.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pumpgrok.backtest.gaps import segment
from pumpgrok.backtest.grading import APPROVED_THRESHOLDS, CanaryResult, grade
from pumpgrok.backtest.metrics import MetricsContext
from pumpgrok.backtest.metrics_v2 import summarize_v2
from pumpgrok.backtest.roundtrip import RoundTrips, round_trips
from pumpgrok.backtest.store import ResultStore, edge_key
from pumpgrok.backtest.strategy_run import run_strategy
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.ledger.events import NoteKind
from pumpgrok.ledger.store import SOURCES
from pumpgrok.tools.journal.append import JournalAppendIn, run_journal_append

__all__ = ["GRADER_VERSION", "Edge", "run_edge", "strategy_run"]

#: Grader identity stamped on every edge this module writes.
GRADER_VERSION = "1"

#: The journal writer records this source. It is an existing SOURCES member.
_LEDGER_SOURCE = "paper"

EdgeKind = Literal["dataset", "strategy"]
EdgeStatus = Literal["done", "skipped", "cached"]


@dataclass(frozen=True)
class Edge:
    """One dataset digest or strategy version the caller wants evaluated."""

    dataset_digest: str
    strategy_version_id: str
    params_hash: str
    dataset_dir: str
    strategy_id: str
    kind: EdgeKind
    grader_version: str = GRADER_VERSION
    params: tuple[tuple[str, str], ...] = ()
    canary_passed: bool = False

    def key(self) -> tuple[str, str, str, str]:
        return edge_key(
            self.dataset_digest,
            self.strategy_version_id,
            self.params_hash,
            self.grader_version,
        )


def strategy_run(edge: Edge) -> Any:
    """16-02 entry. Tests replace this; a second edge must not reach it."""
    return run_strategy(edge.strategy_id, dict(edge.params), edge.dataset_dir)


def run_edge(edge: Edge, store: ResultStore, ledger_store: Any, clock: Any) -> EdgeStatus:
    """Evaluate one edge, or return skipped or cached without doing the work.

    Autonomy is checked before any sidecar or ledger write. A stored key
    returns cached and does not call ``strategy_run``.
    """
    if _LEDGER_SOURCE not in SOURCES:
        raise RuntimeError("journal source is not an existing SOURCES value")
    if read_autonomy(ledger_store) != "autonomous-paper":
        return "skipped"
    key = edge.key()
    if store.row_bytes(key) is not None:
        return "cached"
    run = strategy_run(edge)
    body = _result_body(edge, run)
    store.insert_or_get(key, body)
    _publish(ledger_store, clock, str(body["result_id"]), str(body["grade"]))
    return "done"


def _result_body(edge: Edge, run: Any) -> dict[str, Any]:
    """Grade the dataset and fold 16-01 metrics into one canonical mapping."""
    book = run.round_trips if isinstance(getattr(run, "round_trips", None), RoundTrips) else None
    counted = round_trips(())
    if book is None:
        book = counted
    metrics = summarize_v2(
        book,
        MetricsContext(
            initial_equity_lamports=0,
            equity_curve_lamports=(),
            elapsed_days=Decimal(0),
        ),
    )
    segmentation = segment(
        edge.dataset_dir,
        None,
        APPROVED_THRESHOLDS.cooldown_s,
        APPROVED_THRESHOLDS.haircut_bps,
    )
    graded = grade(
        edge.dataset_dir,
        CanaryResult(passed=edge.canary_passed),
        APPROVED_THRESHOLDS,
    )
    result_id = _result_id(edge)
    return {
        "dataset_digest": edge.dataset_digest,
        "gap_flags": len(segmentation.flags),
        "grade": graded.verdict,
        "grader_version": edge.grader_version,
        "kind": edge.kind,
        "metrics_annualization_valid": metrics.annualization_valid,
        "params_hash": edge.params_hash,
        "reasons": list(graded.reasons),
        "result_id": result_id,
        "strategy_version_id": edge.strategy_version_id,
    }


def _result_id(edge: Edge) -> str:
    identity = canonical_json(
        {
            "dataset_digest": edge.dataset_digest,
            "grader_version": edge.grader_version,
            "params_hash": edge.params_hash,
            "strategy_version_id": edge.strategy_version_id,
        }
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _publish(ledger_store: Any, clock: Any, result_id: str, grade_name: str) -> None:
    """JournalNote verdict through journal.append. Source stays ``paper``."""
    journal_dir = Path(ledger_store.path).parent / "journal"
    note = JournalAppendIn(
        kind="journal_note",
        note_kind=NoteKind.verdict.value,
        body={
            "text": f"backtest result {result_id} grade {grade_name}",
            "refs": [result_id],
        },
        bot="desk",
        correlation_id=result_id,
    )
    asyncio.run(run_journal_append(note, ledger_store, clock, journal_dir))
