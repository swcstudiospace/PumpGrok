"""Seeded deterministic replay runner (paper-engine.md 4.4-4.5, PAPER-004).

One path drives every replay: verify the manifest, advance a
:class:`FixtureClock` through each fixture timestamp, fold the events into one
engine decision, append one ``JournalNote`` (``source=replay``) through
``LedgerStore.append_batch``, then verify the chain. Same dataset plus same
seed yields identical ULIDs, timestamps and hashes; any silent gap longer than
:data:`STALE_GAP_S` fails the run with :class:`DataStale` instead of replaying
stale prices as fresh.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.errors import DataStale
from pumpgrok.core.idempotency import derive_idempotency_key
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.engine.pipeline import decide_replay, format_decision
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore, recreate_ledger_db
from pumpgrok.logging.json import bind_seat
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import EVENTS_NAME, CorruptFixture, load_dataset
from pumpgrok.replay.recorder import load_llm_records
from pumpgrok.replay.rng import DEFAULT_SEED, make_rng
from pumpgrok.replay.sources import FixtureEventSource

__all__ = [
    "CYCLE_SEAT",
    "STALE_GAP_S",
    "ReplayResult",
    "ledger_events_hash",
    "llm_request_for",
    "run_replay",
]

CYCLE_SEAT = "desk"
STALE_GAP_S = 120.0
REPLAY_ROOT = Path("var") / "replay"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of one replay run; every field derives from fixture plus seed."""

    dataset: str
    events_read: int
    decision: str
    reason: str
    events_hash: str
    ledger_path: Path
    seq: int


def llm_request_for(dataset_name: str, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the model-resolution request a replay answers from the fixture.

    Only fixture-stable inputs: the dataset name, the event count and the
    first and last stamps. The generator authors the same dict, so the
    recorded ``canonical_request_hash`` matches without running the engine.
    """
    first = events[0]
    last = events[-1]
    return {
        "dataset": dataset_name,
        "events": len(events),
        "first_ts_utc": first["ts_utc"],
        "last_ts_utc": last["ts_utc"],
    }


def ledger_events_hash(ledger_path: str | Path) -> str:
    """sha256 over the concatenated ``events.hash`` column in seq order."""
    conn = sqlite3.connect(str(ledger_path))
    try:
        rows = conn.execute("SELECT hash FROM events ORDER BY seq ASC;").fetchall()
    finally:
        conn.close()
    digest = hashlib.sha256()
    for (value,) in rows:
        digest.update(str(value).encode("utf-8"))
    return digest.hexdigest()


def run_replay(
    dataset_dir: str | Path,
    filter_cfg: FilterSettings,
    *,
    seed: int = DEFAULT_SEED,
    ledger_path: str | Path | None = None,
) -> ReplayResult:
    """Replay one fixture dataset into a fresh hash-chained ledger."""
    source_dir = Path(dataset_dir)
    dataset = load_dataset(source_dir)  # verifies every listed digest first
    if not dataset.events:
        raise CorruptFixture("dataset has no events", file=EVENTS_NAME)
    source = FixtureEventSource(dataset)

    stamps = source.timestamps()
    for previous, current in pairwise(stamps):
        if current - previous > STALE_GAP_S:
            gap = current - previous
            raise DataStale(
                f"replay gap of {gap:.1f}s exceeds {STALE_GAP_S:.0f}s silence budget",
                dataset=source.name,
                gap_s=gap,
            )

    clock = FixtureClock(start=stamps[0])
    ids = IdFactory(clock, make_rng(seed))
    cycle = CorrelationId.new(ids)
    if ledger_path is None:
        target = REPLAY_ROOT / source.name / "ledger.sqlite"
    else:
        target = Path(ledger_path)
    # Pre-append checks (manifest, gap, LLM record) run before any file is
    # created, and an append/verify failure removes the just-created ledger,
    # so a failed run leaves no file behind.

    with bind_correlation(cycle), bind_seat(CYCLE_SEAT):
        for stamp in stamps:
            clock.advance_to(stamp)
        # Pure engine stage only: fixture ticks become evidence-less
        # candidates, so the fail-closed filter decides. No monitor stream,
        # no analyzer fetch. Model resolution answers from the fixture: a
        # recorded outcome sleeps its virtual latency on the clock, and a
        # request with no record fails the run (ReplayMissingRecord).
        decision = decide_replay(list(source), filter_cfg, clock.now())
        replay_llm = load_llm_records(source_dir)
        llm_clause = ""
        if replay_llm is not None:
            llm_outcome = replay_llm.complete(llm_request_for(source.name, list(source)), clock)
            llm_clause = f"; llm outcome={llm_outcome.outcome} latency_s={llm_outcome.latency_s}"
        recreate_ledger_db(target)
        store = LedgerStore(target)
        try:
            stored = store.append_batch(
                [
                    {
                        "ts_utc": clock.utc_iso(),
                        "source": "replay",
                        "correlation_id": str(cycle),
                        "idempotency_key": derive_idempotency_key(
                            "skip_cycle",
                            CYCLE_SEAT,
                            {"dataset": source.name, "events": len(source)},
                            scope=str(cycle),
                        ),
                        "type": "JournalNote",
                        "payload": {
                            "source": "replay",
                            "seat": CYCLE_SEAT,
                            "note_kind": "verdict",
                            "text": (
                                f"replay engine cycle: {format_decision(decision)}; "
                                "model resolution skipped (replay); "
                                f"read {len(source)} fixture events from {source.name}; "
                                "metadata and age gates satisfied by construction, "
                                "buyer evidence absent by construction"
                                f"{llm_clause}"
                            ),
                            "refs": [],
                        },
                    }
                ]
            )
            if not store.verify():
                raise LedgerInconsistent("replay ledger failed verification")
        except Exception:
            # A failed append/verify must not leave a file that file-existence
            # checks mistake for a successful replay output: drop the
            # just-created ledger (sqlite plus -wal/-shm) and re-raise.
            with contextlib.suppress(OSError):
                recreate_ledger_db(target)
            raise
        finally:
            store.close()
        events_hash = ledger_events_hash(target)
        log.info(
            "replay engine cycle complete",
            extra={
                "event": "cycle_end",
                "events_read": len(source),
                "engine_decision": decision.decision,
                "engine_reason": decision.reason,
                "ledger_seq": stored[0]["seq"],
            },
        )
    return ReplayResult(
        dataset=source.name,
        events_read=len(source),
        decision=decision.decision,
        reason=decision.reason,
        events_hash=events_hash,
        ledger_path=target,
        seq=stored[0]["seq"],
    )
