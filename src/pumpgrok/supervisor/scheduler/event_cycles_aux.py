"""Event-driven seat cycles for the whale, signal and journal roles (EVT-10, 14-04 slice B).

Each body runs on the bus event that woke its seat (``TRIGGER_EVENT``). A journal timer start has
no event and runs the rollup, as the 300 s ``EVENT_TIMERS`` entry promises.

Each body calls the role's existing service and never invents an observation:

- whale: ``onchain.large_transfers`` over the injected RPC client. With no RPC client, or with
  every RPC endpoint down, it reports BLIND; a failed read reports UNREAD.
- signal: stands down on a kill switch or halt. For a candidate it scores from the dataset's
  recorded model outcome. Model latency is charged to a scratch clock, so the shared desk clock
  never moves for a model call. With no recorded outcomes it reports skipped.
- journal: notes each trade or position event through ``journal.append`` bound to the journal
  seat, and renders the daily report from the ledger on the timer or on a position close.

Only the injected clock is read. Nothing here imports the Grok gateway: a model answer comes only
from a recorded outcome, never from a live call.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import bind_calling_seat
from pumpgrok.events.models import Event, EventKind
from pumpgrok.ledger.events import NoteKind
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.runner import llm_request_for
from pumpgrok.supervisor.scheduler.supervisor import TRIGGER_EVENT
from pumpgrok.supervisor.seat_task import CycleFn, SeatContext
from pumpgrok.tools.journal.append import JournalAppendIn, run_journal_append
from pumpgrok.tools.journal.render_report import RenderReportIn, run_render_report
from pumpgrok.tools.onchain.large_transfers import LargeTransfersIn, run_large_transfers
from pumpgrok.tools.onchain.rpc import RpcError

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.replay.recorder import ReplayLlm
    from pumpgrok.supervisor.scheduler.degraded import DegradedState
    from pumpgrok.supervisor.scheduler.replay_runtime import _ReplayTrading
    from pumpgrok.tools.onchain.rpc import RpcClient

__all__ = ["build_aux_event_cycles"]

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


async def _signal(
    ctx: SeatContext,
    *,
    replay_llm: ReplayLlm | None,
    dataset_name: str,
    dataset_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Signal: stand down on a kill switch or halt; score a candidate from its recorded outcome."""
    event = TRIGGER_EVENT.get()
    trigger = _trigger_name(event)
    if event is not None and event.kind in _WITHHOLD_KINDS:
        return {"scoring": "withheld", "withheld": event.kind.value, "trigger": trigger}
    if event is None or event.kind not in _CANDIDATE_KINDS:
        return {"scoring": "skipped", "reason": "not_a_candidate", "trigger": trigger}
    if replay_llm is None:
        return {"scoring": "skipped", "reason": "no_model_records", "trigger": trigger}
    # Model latency is virtual: charge it to a scratch clock. A FixtureClock cannot move backwards
    # and the desk clock is shared with every other seat, so a model call never moves it.
    latency_clock = FixtureClock(start=ctx.clock.now())
    outcome = replay_llm.complete(llm_request_for(dataset_name, list(dataset_events)), latency_clock)
    return {"scoring": "llm", "outcome": outcome.outcome, "mint": event.entity_id, "trigger": trigger}


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


def build_aux_event_cycles(
    *,
    store: LedgerStore,
    degraded: DegradedState,
    rpc: RpcClient | None,
    replay_llm: ReplayLlm | None,
    dataset_name: str,
    dataset_events: Sequence[Mapping[str, Any]],
    trading: _ReplayTrading | None,
    journal_dir: Path,
    reports_dir: Path,
) -> Mapping[str, CycleFn]:
    """Event-driven bodies for the whale, signal and journal seats, keyed by seat id.

    ``rpc`` is the whale's read path; ``None`` reports BLIND. ``replay_llm`` holds the dataset's
    recorded model outcomes; ``None`` reports skipped. ``trading`` is the runtime's granted wiring
    (its marks are refreshed before the journal folds); ``None`` skips the refresh. Merge the
    result over the replay map with ``merge_event_cycles``.
    """
    return {
        WHALE: functools.partial(_whale, degraded=degraded, rpc=rpc),
        SIGNAL: functools.partial(
            _signal,
            replay_llm=replay_llm,
            dataset_name=dataset_name,
            dataset_events=dataset_events,
        ),
        JOURNAL: functools.partial(
            _journal,
            store=store,
            trading=trading,
            journal_dir=journal_dir,
            reports_dir=reports_dir,
        ),
    }
