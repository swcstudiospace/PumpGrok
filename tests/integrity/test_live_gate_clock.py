"""Live gate clock injection (INT-06, D-07).

The gate never reads wall time: ``evaluate``/``check`` take ``now`` from the
caller, so two evaluations under one fixture ``now`` are byte-identical and a
different ``now`` moves only the day count. Deterministic, no network.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.execution.live.live_gate import LiveGate
from pumpgrok.ledger.store import LedgerStore

MINT = "So11111111111111111111111111111111111111112"
CID = "01J0000000000000000000000000"
FIRST_TS = "2026-08-01T10:00:00Z"


def _append(store: LedgerStore, seq: int, type: str, payload: dict, ts: str) -> None:
    store.append(
        ts_utc=ts,
        source="paper",
        correlation_id=CID,
        idempotency_key=f"gate-{type}-{seq}",
        type=type,
        payload=payload,
    )


def _paper_root(tmp_path: Path) -> Path:
    var = tmp_path / "var"
    var.mkdir()
    store = LedgerStore(var / "ledger.sqlite")
    try:
        for seq in range(3):
            _append(
                store,
                seq,
                "PositionClosed",
                {
                    "mint": MINT,
                    "source": "paper",
                    "price_exit": "0.00005800",
                    "proceeds_lamports": 203000000,
                    "realized_pnl_lamports": 3000000,
                    "reason": "take_profit",
                },
                FIRST_TS,
            )
        _append(
            store,
            3,
            "MarkToMarket",
            {
                "ts_source": "curve",
                "source": "paper",
                "cash_lamports": 9000000000,
                "equity_lamports": 11500000000,
                "unrealized_lamports": 0,
            },
            "2026-08-01T12:00:00Z",
        )
    finally:
        store.close()
    return tmp_path


def _gate(root: Path) -> LiveGate:
    return LiveGate(mode="live", environ={"PUMPGROK_LIVE_ENABLE": "1"}, root=root)


def test_gate_output_identical_across_evaluations(tmp_path: Path) -> None:
    """Two evaluations under one fixture now are byte-identical."""
    root = _paper_root(tmp_path)
    first = _gate(root).evaluate(now="2026-08-20T00:00:00Z")
    second = _gate(root).evaluate(now="2026-08-20T00:00:00Z")
    assert first == second
    assert _gate(root).check(now="2026-08-20T00:00:00Z") == _gate(root).check(
        now="2026-08-20T00:00:00Z"
    )


def test_now_threads_through_days_precondition(tmp_path: Path) -> None:
    """The day count follows the injected now, not the wall clock."""
    root = _paper_root(tmp_path)
    early = {item.id: item for item in _gate(root).evaluate(now="2026-08-10")}
    assert early["min_paper_days"].met is False
    assert early["min_paper_days"].reason == "9 of 14 days on source=paper events"
    late = {item.id: item for item in _gate(root).evaluate(now="2026-08-20")}
    assert late["min_paper_days"].met is True
    assert late["min_paper_days"].reason == "19 of 14 days on source=paper events"


def test_timestamp_form_matches_date_form(tmp_path: Path) -> None:
    """A full timestamp and its date evaluate identically (date part only)."""
    root = _paper_root(tmp_path)
    by_date = _gate(root).evaluate(now="2026-08-20")
    by_ts = _gate(root).evaluate(now="2026-08-20T23:59:59Z")
    assert by_date == by_ts
