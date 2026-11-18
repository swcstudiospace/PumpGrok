"""Strategy-scoped kills over the StrategyKillSet and StrategyKillCleared rows (RSK-02).

A strategy kill refuses that strategy's buys at the kill_switch step and never refuses sells.
Only a human sets or clears it: the identity starts with ``human:`` and is not a seat id, the
same rule the desk-wide clear applies (D17-5). A clear needs a ``killswitch_clear`` approval,
consumed in the same batch as the clear row, so an approval clears one kill once.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.ledger.reducer import LedgerState
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.risk.killswitch import SEAT_RE

__all__ = [
    "StrategyKillRefused",
    "clear_strategy_kill",
    "is_strategy_killed",
    "set_strategy_kill",
]

_KILL_TYPES = ["StrategyKillSet", "StrategyKillCleared"]


class StrategyKillRefused(ValueError):
    """A strategy kill set or clear the rules refuse: not human, wrong kind, or not killed."""


def is_strategy_killed(state: LedgerState, strategy_id: str) -> bool:
    """True while the folded state holds an unreleased kill for this strategy."""
    return strategy_id in state.strategy_kills


def _human(by: str) -> None:
    if not by.startswith("human:") or SEAT_RE.match(by.removeprefix("human:")):
        raise StrategyKillRefused(f"strategy kill must come from a human, got {by!r}")


def _require_id(strategy_id: str) -> None:
    if not strategy_id:
        raise StrategyKillRefused("a strategy kill needs a strategy id")


def _kill_rows(store: LedgerStore, strategy_id: str) -> list[dict[str, Any]]:
    """Strategy kill rows for one strategy, oldest first."""
    return [
        event
        for event in store.read(types=_KILL_TYPES, limit=None)
        if event["payload"].get("strategy_id") == strategy_id
    ]


def _killed(store: LedgerStore, strategy_id: str) -> bool:
    rows = _kill_rows(store, strategy_id)
    return bool(rows) and rows[-1]["type"] == "StrategyKillSet"


def _cleared_count(store: LedgerStore, strategy_id: str) -> int:
    """Count of clears for one strategy: each clear starts a new set-key epoch."""
    return sum(1 for row in _kill_rows(store, strategy_id) if row["type"] == "StrategyKillCleared")


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def set_strategy_kill(
    store: LedgerStore,
    strategy_id: str,
    reason: str,
    set_by: str,
    *,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "desk",
) -> dict[str, Any] | None:
    """Append ``StrategyKillSet`` for a strategy; None when that strategy is already killed."""
    _require_id(strategy_id)
    _human(set_by)
    if _killed(store, strategy_id):
        return None
    epoch = _cleared_count(store, strategy_id)
    row: dict[str, Any] = {
        "ts_utc": ts_utc,
        "source": source,
        "correlation_id": correlation_id,
        "idempotency_key": _key("StrategyKillSet", strategy_id, str(epoch)),
        "type": "StrategyKillSet",
        "payload": {
            "source": source,
            "strategy_id": strategy_id,
            "reason": reason,
            "set_by": set_by,
        },
    }
    store.append(**row)
    return row


def clear_strategy_kill(
    store: LedgerStore,
    approval: ApprovalRecord,
    strategy_id: str,
    reason: str,
    *,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "desk",
) -> dict[str, Any]:
    """Append ``StrategyKillCleared`` and consume the ``killswitch_clear`` approval in one batch."""
    _require_id(strategy_id)
    by = approval.approved_by
    _human(by)
    if approval.kind != "killswitch_clear":
        raise StrategyKillRefused(f"clear needs a killswitch_clear approval, got {approval.kind!r}")
    if not _killed(store, strategy_id):
        raise StrategyKillRefused(f"strategy {strategy_id} is not killed")
    epoch = _cleared_count(store, strategy_id)
    cleared: dict[str, Any] = {
        "ts_utc": ts_utc,
        "source": source,
        "correlation_id": correlation_id,
        "idempotency_key": _key("StrategyKillCleared", strategy_id, str(epoch)),
        "type": "StrategyKillCleared",
        "payload": {
            "source": source,
            "strategy_id": strategy_id,
            "cleared_by": by,
            "approval_id": approval.id,
        },
    }
    consumed: dict[str, Any] = {
        "ts_utc": ts_utc,
        "source": source,
        "correlation_id": correlation_id,
        "idempotency_key": f"consumed|{approval.id}",
        "type": "ApprovalRecorded",
        "payload": {
            "source": source,
            "id": approval.id,
            "kind": approval.kind,
            "approved_by": by,
            "at": approval.at.isoformat(),
            "ticket_id": approval.ticket_id or "",
            "mint": approval.mint or "",
            "size_lamports": approval.size_lamports or 0,
            "token_units": approval.token_units or 0,
            "max_slippage_bps": approval.max_slippage_bps or 0,
            "exit_rule_id": approval.exit_rule_id or "",
            "raw_message": reason,
            "consumed": True,
        },
    }
    if store.by_key(str(consumed["idempotency_key"])) is not None:
        raise StrategyKillRefused(f"killswitch_clear approval {approval.id} is already consumed")
    store.append_batch([cleared, consumed])
    return cleared
