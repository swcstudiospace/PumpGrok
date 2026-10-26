"""Seeded deterministic replay runner (paper-engine.md 4.4-4.5, PAPER-004).

One path drives every replay: verify the manifest, advance a
:class:`FixtureClock` through each fixture timestamp, judge each event as a
candidate, summarise the verdicts as one engine decision, append one
``JournalNote`` (``source=replay``) through
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
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.errors import DataStale
from pumpgrok.core.idempotency import derive_idempotency_key
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.engine.pipeline import decide_replay, format_decision
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore, recreate_ledger_db
from pumpgrok.logging.json import bind_seat
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, CorruptFixture, load_dataset
from pumpgrok.replay.recorder import load_llm_records
from pumpgrok.replay.rng import DEFAULT_SEED, make_rng
from pumpgrok.replay.sources import FixtureEventSource

if TYPE_CHECKING:
    from pumpgrok.upgrade.params import ParamSet

__all__ = [
    "CYCLE_SEAT",
    "STALE_GAP_S",
    "ReplayResult",
    "ReplayTrade",
    "ledger_events_hash",
    "llm_request_for",
    "run_replay",
]

CYCLE_SEAT = "desk"
STALE_GAP_S = 120.0
REPLAY_ROOT = Path("var") / "replay"


def _contained_ledger_path(dataset_name: str) -> Path:
    """Default ledger path for a dataset; refuses any path that resolves outside REPLAY_ROOT."""
    root = REPLAY_ROOT.resolve()
    target = (root / dataset_name / "ledger.sqlite").resolve()
    if target.parent.parent != root:
        raise CorruptFixture("dataset name escapes the replay directory", file=MANIFEST_NAME)
    return target


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayTrade:
    """One order attempt a replay cycle made through the registry (G1).

    ``outcome`` is the place tool's status (``filled``, ``partial``,
    ``rejected`` or ``unknown``) and ``reason`` its catalog reason: ``ok`` on
    a fill, the risk or adapter refusal otherwise.

    Per-fill detail (BT-02) mirrors the FillRecorded row the same call wrote:
    price, venue fee, network cost, latency and filled fraction. Money stays
    integer base units; price and latency are Decimals. An attempt that never
    filled keeps zeroed detail and names its outcome.
    """

    side: str
    mint: str
    outcome: str
    reason: str
    rule: str = ""
    price_avg: Decimal = Decimal("0")
    venue_fee_lamports: int = 0
    network_cost_lamports: int = 0
    latency_s: Decimal = Decimal("0")
    filled_fraction: Decimal = Decimal("0")


def format_trade(trade: ReplayTrade) -> str:
    """One stdout line for a replay order attempt; a rule sell names its rule."""
    rule = f" rule={trade.rule}" if trade.rule else ""
    return (
        f"trade side={trade.side} mint={trade.mint} outcome={trade.outcome} "
        f"reason={trade.reason}{rule}"
    )


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
    trades: tuple[ReplayTrade, ...] = ()


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
    active_set: ParamSet | None = None,
) -> ReplayResult:
    """Replay one fixture dataset into a fresh hash-chained ledger.

    When ``active_set`` is given, its candidate's filter settings replace ``filter_cfg``
    before the checkpoint verdict is judged, as ``open_replay_runtime`` does for the
    paper timeline. Exit settings never reach this verdict, so only the filter is applied.
    ``None`` leaves the replay unchanged.
    """
    if active_set is not None:
        filter_cfg = active_set.candidate().filter_settings()
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
    target = _contained_ledger_path(source.name) if ledger_path is None else Path(ledger_path)
    # Pre-append checks (manifest, gap, LLM record) run before any file is
    # created, and an append/verify failure removes the just-created ledger,
    # so a failed run leaves no file behind.

    with bind_correlation(cycle), bind_seat(CYCLE_SEAT):
        for stamp in stamps:
            clock.advance_to(stamp)
        # Pure engine stage only: each fixture tick is a candidate carrying its
        # recorded evidence, judged by the fail-closed filter at its own time.
        # No monitor stream, no analyzer fetch. Model resolution answers from
        # the fixture: a recorded outcome sleeps its virtual latency on the
        # clock, and a request with no record fails the run (ReplayMissingRecord).
        decision = decide_replay(list(source), filter_cfg)
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
                                "candidates judged on fixture evidence "
                                "(name, image, created time, buyers, reserves)"
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
