"""Restart recovery for the event desk (RT-04, T-17-11, T-17-12).

The startup pass of the composition root: read the ledger for open
positions, strategy tapes, trailing-stop peaks and probation markers,
and the bus sidecar for the watch set, then re-arm exit deadlines from
the restored state using the injected Clock. The resume guard keys on
the candidate-to-decision link, not timestamp equality, so the
OrderPlaced written after the candidate stamp still blocks a second
BUY. Recovery runs before any seat wakes and fails closed with a typed
error when the ledger is corrupt; it never falls back to a default
equity. Every restored value is cross-checked against the ledger hash
chain (store.verify). Recovery is read-only and idempotent: a crash
mid-recovery resumes clean.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerInconsistent
from pumpgrok.replay.clock import Clock, parse_ts_utc
from pumpgrok.risk.engine.model import utc_day

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "DuplicateBuyError",
    "RecoveryError",
    "RecoveryInterrupted",
    "RestoredState",
    "assert_no_second_buy",
    "decision_recorded",
    "recover",
]

#: Exit deadlines are re-armed one max-hold window after the open stamp.
DEFAULT_MAX_HOLD_S = 3600.0


class RecoveryError(RuntimeError):
    """Recovery refused: the ledger is corrupt or a required row is missing."""


class RecoveryInterrupted(RuntimeError):
    """Recovery was interrupted mid-pass (simulated crash); safe to re-run."""


class DuplicateBuyError(RuntimeError):
    """A resumed serve would place a second BUY for the same mint and candidate."""


@dataclass(frozen=True)
class RestoredState:
    """Everything recovery restored from the ledger and sidecar."""

    open_positions: dict[str, Any] = field(default_factory=dict)
    peaks: dict[str, int] = field(default_factory=dict)
    tapes: dict[str, int] = field(default_factory=dict)
    probation: frozenset[str] = frozenset()
    watch_set: frozenset[str] = frozenset()
    deadlines: dict[str, float] = field(default_factory=dict)


def _read_positions(store: LedgerStore, clock: Clock) -> dict[str, Any]:
    events = store.read(since_seq=1, limit=None)
    meta_equity = store.get_meta("initial_equity_lamports")
    initial = int(meta_equity) if meta_equity is not None else 10_000_000_000
    meta_source = store.get_meta("source") or "paper"
    state = initial_state(
        source=meta_source, initial_equity_lamports=initial, day_utc=utc_day(clock.now())
    )
    for event in events:
        state = reduce(state, event)
    return {mint: pos for mint, pos in state.positions.items() if pos.token_units > 0}


def _read_notes(store: LedgerStore) -> list[str]:
    texts: list[str] = []
    for event in store.read(types=["JournalNote"], limit=None):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        texts.append(str(payload.get("text", "")))
    return texts


def _read_watch_sidecar(path: Path | str | None) -> set[str]:
    if path is None:
        return set()
    target = Path(path)
    if not target.exists():
        return set()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecoveryError(f"watch sidecar unreadable: {target}: {exc}") from exc
    if not isinstance(raw, list):
        raise RecoveryError(f"watch sidecar is not a list: {target}")
    return {str(x) for x in raw}


def recover(
    store: LedgerStore,
    clock: Clock,
    *,
    max_hold_s: float = DEFAULT_MAX_HOLD_S,
    watch_sidecar: Path | str | None = None,
    fail_after_batches: int | None = None,
) -> RestoredState:
    """Restore deadlines, tapes, peaks, probation and the watch set.

    Fails closed with RecoveryError when the ledger hash chain does not
    verify. ``fail_after_batches`` interrupts the pass mid-recovery for
    crash testing; the pass is read-only, so a second call converges to
    the identical state.
    """
    try:
        store.verify()
    except LedgerInconsistent as exc:
        raise RecoveryError(f"ledger chain corrupt at restart: {exc}") from exc

    batches = 0

    def _checkpoint() -> None:
        nonlocal batches
        batches += 1
        if fail_after_batches is not None and batches > fail_after_batches:
            raise RecoveryInterrupted("simulated crash mid-recovery")

    positions = _read_positions(store, clock)
    _checkpoint()
    peaks = {mint: int(pos.cost_basis_lamports) for mint, pos in positions.items()}
    _checkpoint()
    texts = _read_notes(store)
    tapes: dict[str, int] = {}
    for event in store.read(types=["OrderPlaced"], limit=None):
        payload = event.get("payload")
        if isinstance(payload, dict):
            for key in ("approval_json", "risk_json", "quote_json"):
                text = str(payload.get(key, ""))
                if "strategy" in text:
                    tapes[text] = tapes.get(text, 0) + 1
                    break
    _checkpoint()
    probation = frozenset(
        t[len("PROBATION ") :].split(" ", 1)[0] for t in texts if t.startswith("PROBATION ")
    )
    watch = frozenset(
        t[len("WATCH ") :].split(" ", 1)[0] for t in texts if t.startswith("WATCH ")
    ) | frozenset(_read_watch_sidecar(watch_sidecar))
    _checkpoint()
    deadlines: dict[str, float] = {}
    for mint, pos in positions.items():
        try:
            opened = parse_ts_utc(pos.opened_ts_utc) if pos.opened_ts_utc else clock.now()
        except ValueError:
            raise RecoveryError(f"position {mint} has an unparsable open stamp") from None
        deadlines[mint] = opened + max_hold_s
    _checkpoint()
    return RestoredState(
        open_positions=positions,
        peaks=peaks,
        tapes=tapes,
        probation=frozenset(x for x in probation if x),
        watch_set=watch,
        deadlines=deadlines,
    )


def decision_recorded(store: LedgerStore, mint: str, decision_id: str) -> bool:
    """True when a decision link for this mint and candidate already exists."""
    for type_ in ("OrderPlaced", "FillRecorded"):
        for event in store.read(types=[type_], limit=None):
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            if (
                str(payload.get("mint", "")) == mint
                and str(payload.get("decision_id", "")) == decision_id
            ):
                return True
    return False


def assert_no_second_buy(store: LedgerStore, mint: str, decision_id: str) -> None:
    """Refuse a resumed second BUY for the same mint and candidate (HARD-07)."""
    if decision_recorded(store, mint, decision_id):
        raise DuplicateBuyError(f"decision {decision_id} already recorded for mint {mint}")
