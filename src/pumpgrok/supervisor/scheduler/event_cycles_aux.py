<<<<<<< HEAD
"""Deterministic bus and journal rollup (EVT-08, RT-01).

`DeterministicBus` is the Phase 12 drain under `fixture_compat`: identical
bytes for identical inputs, exact hash equality, no tolerance band.
=======
"""Event-driven seat cycles for the whale, signal and journal roles (EVT-10, 14-04 slice B).

Each body runs on the bus event that woke its seat (``TRIGGER_EVENT``). A journal timer start has
no event and runs the rollup, as the 300 s ``EVENT_TIMERS`` entry promises.

Each body calls the role's existing service and never invents an observation:

- whale: ``onchain.large_transfers`` over the injected RPC client. With no RPC client, or with
  every RPC endpoint down, it reports BLIND; a failed read reports UNREAD.
- signal: stands down on a kill switch or halt. For a candidate it reports a SYNTHETIC per-token
  score from that candidate's own fixture row (``synthetic_signal_score``). It is not a model
  result and not a Grok outcome: the fixtures record no per-token model outcomes, so the score is
  a deterministic stand-in chosen by the owner. A candidate with no fixture row reports skipped.
- journal: notes each trade or position event through ``journal.append`` bound to the journal
  seat, and renders the daily report from the ledger on the timer or on a position close.

Only the injected clock is read. Nothing here imports the Grok gateway or calls a model.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
import random
from collections.abc import Sequence

from pumpgrok.events.drain import DrainBytes, drain
from pumpgrok.events.models import Event
from pumpgrok.replay.clock import FixtureClock

#: Seed pinned by the smoke datasets (manifest seed_hint).
FIXTURE_SEED = 20260101


class DeterministicBus:
    """The Phase 12 drain as a bus. Only this drain is used; no second copy."""

    def __init__(self, *, clock: FixtureClock, rng: random.Random) -> None:
        self._clock = clock
        self._rng = rng

    def deliver(self, events: Sequence[Event], *, fixture_compat: bool = True) -> DrainBytes:
        if not fixture_compat:
            raise ValueError("deterministic bus requires fixture_compat")
        return drain(events, self._clock, self._rng)
=======
import functools
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import bind_calling_seat
from pumpgrok.engine.monitor import CURVE_COMPLETION_LAMPORTS
from pumpgrok.events.models import Event, EventKind
from pumpgrok.ledger.events import NoteKind
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.supervisor.scheduler.supervisor import TRIGGER_EVENT
from pumpgrok.supervisor.seat_task import CycleFn, SeatContext
from pumpgrok.tools.journal.append import JournalAppendIn, run_journal_append
from pumpgrok.tools.journal.render_report import RenderReportIn, run_render_report
from pumpgrok.tools.onchain.large_transfers import LargeTransfersIn, run_large_transfers
from pumpgrok.tools.onchain.rpc import RpcError

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.supervisor.scheduler.degraded import DegradedState
    from pumpgrok.supervisor.scheduler.replay_runtime import _ReplayTrading
    from pumpgrok.tools.onchain.rpc import RpcClient

__all__ = ["build_aux_event_cycles", "synthetic_signal_score"]

WHALE = "bot-03-whale"
SIGNAL = "bot-08-signal"
JOURNAL = "bot-09-journal"

#: Events that wake the whale and the signal as a candidate (owner-confirmed wake matrix).
_CANDIDATE_KINDS = frozenset({EventKind.token_created, EventKind.migration})
#: Events on which the signal stands down: it scores nothing while the desk is halted.
_WITHHOLD_KINDS = frozenset({EventKind.kill_switch, EventKind.halt})
#: Events the journal records as a note.
_NOTE_KINDS = frozenset({EventKind.trade, EventKind.position_opened, EventKind.position_closed})
#: Events that also render the daily rollup. The timer is the other rollup trigger.
_ROLLUP_KINDS = frozenset({EventKind.position_closed})
#: Journal note vocabulary for trade and position facts.
_NOTE_KIND = NoteKind.note.value


def _trigger_name(event: Event | None) -> str:
    return "timer" if event is None else event.kind.value


async def _refresh_marks(trading: _ReplayTrading | None) -> None:
    """Mark every open position from the curve source at this instant (never from a payload)."""
    if trading is not None and trading.refresh_marks is not None:
        await trading.refresh_marks()


async def _whale(
    ctx: SeatContext, *, degraded: DegradedState, rpc: RpcClient | None
) -> dict[str, Any]:
    """Whale: watch the new mint's large transfers over RPC; BLIND when no endpoint answers."""
    event = TRIGGER_EVENT.get()
    if event is None or event.kind not in _CANDIDATE_KINDS:
        trigger = _trigger_name(event)
        return {"verdict": "SKIP", "reason": "not_a_candidate", "mint": None, "trigger": trigger}
    mint = event.entity_id
    trigger = event.kind.value
    if degraded.rpc_blind:
        return {"verdict": "BLIND", "reason": "rpc_down", "mint": mint, "trigger": trigger}
    if rpc is None:
        return {"verdict": "BLIND", "reason": "no_rpc", "mint": mint, "trigger": trigger}
    try:
        found = await run_large_transfers(LargeTransfersIn(mint=mint), rpc)
    except (DataStale, RpcError) as exc:
        return {"verdict": "UNREAD", "reason": type(exc).__name__, "mint": mint, "trigger": trigger}
    return {
        "verdict": "OBSERVED",
        "transfers": len(found["transfers"]),
        "mint": mint,
        "trigger": trigger,
    }


#: Synthetic signal weights (sum 1.0). Fixed constants chosen by the owner, not fitted to outcomes.
_W_BUYERS = 0.4
_W_CURVE = 0.3
_W_TIMING = 0.3
#: Unique buyers at which the buyer term saturates at 1.0.
_BUYER_SATURATION = 20
#: First-trade age in seconds after creation at which the timing term reaches 0.0.
_TIMING_WINDOW_S = 3600.0
#: Decimal places of a synthetic score: enough to separate candidates, short in the trace.
_SCORE_DP = 9


def _buyer_term(row: Mapping[str, Any]) -> float:
    buyers = row.get("unique_buyers")
    if isinstance(buyers, bool) or not isinstance(buyers, int) or buyers < 0:
        return 0.0
    return min(buyers, _BUYER_SATURATION) / _BUYER_SATURATION


def _curve_term(row: Mapping[str, Any]) -> float:
    reserves = row.get("S")
    if isinstance(reserves, bool) or not isinstance(reserves, int) or reserves < 0:
        return 0.0
    return min(reserves, CURVE_COMPLETION_LAMPORTS) / CURVE_COMPLETION_LAMPORTS


def _timing_term(row: Mapping[str, Any]) -> float:
    created, first = row.get("created_ts_utc"), row.get("ts_utc")
    if not isinstance(created, str) or not isinstance(first, str):
        return 0.0
    try:
        age = parse_ts_utc(first) - parse_ts_utc(created)
    except ValueError:
        return 0.0
    return max(0.0, 1.0 - age / _TIMING_WINDOW_S) if age >= 0 else 0.0


def synthetic_signal_score(row: Mapping[str, Any]) -> float:
    """SYNTHETIC per-token signal score in [0, 1]. NOT a model result and NOT a Grok outcome.

    A pure function of one candidate's fixture row: the buyer count (``unique_buyers``), the curve
    reserves (``S``, lamports) and the first-trade timing (``ts_utc`` against ``created_ts_utc``).
    A field the row does not record adds nothing and never raises, so a sparse row scores low
    rather than failing. The same row always gives the same score. The owner chose synthetic
    per-token scores because the fixtures carry no per-token recorded Grok outcomes, and this
    sandbox cannot record any.
    """
    score = (
        _W_BUYERS * _buyer_term(row) + _W_CURVE * _curve_term(row) + _W_TIMING * _timing_term(row)
    )
    return round(score, _SCORE_DP)


async def _signal(
    ctx: SeatContext, *, first_rows: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Signal: stand down on a kill switch or halt; score a candidate from its own fixture row."""
    event = TRIGGER_EVENT.get()
    trigger = _trigger_name(event)
    if event is not None and event.kind in _WITHHOLD_KINDS:
        return {"scoring": "withheld", "withheld": event.kind.value, "trigger": trigger}
    if event is None or event.kind not in _CANDIDATE_KINDS:
        return {"scoring": "skipped", "reason": "not_a_candidate", "trigger": trigger}
    row = first_rows.get(event.entity_id)
    if row is None:
        return {
            "scoring": "skipped",
            "reason": "no_fixture_row",
            "mint": event.entity_id,
            "trigger": trigger,
        }
    return {
        "scoring": "synthetic",
        "score": synthetic_signal_score(row),
        "mint": event.entity_id,
        "trigger": trigger,
    }


async def _journal(
    ctx: SeatContext,
    *,
    store: LedgerStore,
    trading: _ReplayTrading | None,
    journal_dir: Path,
    reports_dir: Path,
) -> dict[str, Any]:
    """Journal: note trade and position events; render the daily rollup on the timer or a close."""
    event = TRIGGER_EVENT.get()
    trigger = _trigger_name(event)
    await _refresh_marks(trading)
    noted = False
    if event is not None and event.kind in _NOTE_KINDS:
        with bind_calling_seat(JOURNAL):
            await run_journal_append(
                JournalAppendIn(
                    kind="journal_note",
                    note_kind=_NOTE_KIND,
                    body={
                        "text": f"{event.kind.value} {event.entity_id}",
                        "refs": [event.entity_id],
                    },
                    bot=JOURNAL,
                ),
                store,
                ctx.clock,
                journal_dir,
            )
        noted = True
    rollup: str | None = None
    if event is None or event.kind in _ROLLUP_KINDS:
        report = await run_render_report(
            RenderReportIn(period="daily", deliver=False), store, ctx.clock, reports_dir
        )
        rollup = str(report["report_path"])
    return {"noted": noted, "rollup": rollup, "trigger": trigger}


def _first_rows_by_mint(events: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Each mint's first fixture row: the row its token_created candidate is scored from."""
    rows: dict[str, Mapping[str, Any]] = {}
    for row in events:
        rows.setdefault(str(row["mint"]), row)
    return rows


def build_aux_event_cycles(
    *,
    store: LedgerStore,
    degraded: DegradedState,
    rpc: RpcClient | None,
    dataset_events: Sequence[Mapping[str, Any]],
    trading: _ReplayTrading | None,
    journal_dir: Path,
    reports_dir: Path,
) -> Mapping[str, CycleFn]:
    """Event-driven bodies for the whale, signal and journal seats, keyed by seat id.

    ``rpc`` is the whale's read path; ``None`` reports BLIND. ``dataset_events`` are the fixture
    rows the signal scores each candidate from; a mint with no row reports skipped. ``trading`` is
    the runtime's granted wiring (its marks are refreshed before the journal folds); ``None`` skips
    the refresh. Merge the result over the replay map with ``merge_event_cycles``.
    """
    return {
        WHALE: functools.partial(_whale, degraded=degraded, rpc=rpc),
        SIGNAL: functools.partial(_signal, first_rows=_first_rows_by_mint(dataset_events)),
        JOURNAL: functools.partial(
            _journal,
            store=store,
            trading=trading,
            journal_dir=journal_dir,
            reports_dir=reports_dir,
        ),
    }
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
