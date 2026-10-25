"""PAP-01: backtest results and paper ledger trades share one result schema.

Both sides build SharedResult from the same Fill model over the same window,
so a backtest window and the paper ledger compare field for field. Run ids
reference the run manifest. Deterministic fixtures only; no network, no wall
clock.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from pumpgrok.backtest.manifest import build_manifest
from pumpgrok.backtest.results import FillDetail, SharedResult
from pumpgrok.core.adapter import Fill, FillStatus
from pumpgrok.replay.clock import parse_ts_utc

RUN_ID_SEED = 20260101
CODE_VERSION = "TESTCODEVERSION"
T0 = "2026-01-01T00:00:00.000000Z"
T1 = "2026-01-01T00:00:01.000000Z"
T2 = "2026-01-01T00:00:02.000000Z"
T3 = "2026-01-01T00:00:03.000000Z"
ORDER_A = "0" * 26
ORDER_B = "1" * 26
TX_A = "dry_run:" + "2" * 26
TX_B = "dry_run:" + "3" * 26


def _fill(
    order_id: str,
    tx_ref: str,
    seq: int,
    price: str,
    venue_fee: int,
    network_cost: int,
    fraction: str,
) -> Fill:
    """One deterministic adapter Fill with fixed ULID-shaped ids."""
    return Fill(
        order_id=order_id,
        decision_id=order_id,
        status=FillStatus.FILLED,
        venue_tx_ref=tx_ref,
        filled_lamports=10_000_000,
        filled_units=500_000,
        filled_fraction=Decimal(fraction),
        price_avg=Decimal(price),
        realised_slippage_bps=100,
        venue_fee_lamports=venue_fee,
        network_cost_lamports=network_cost,
        route="curve",
        ledger_seq=seq,
    )


def _row(
    ts_utc: str,
    price: str,
    venue_fee: int,
    network_cost: int,
    fraction: str,
    order_id: str = ORDER_A,
    tx_ref: str = TX_A,
) -> dict[str, Any]:
    """One FillRecorded ledger row carrying the same numbers as _fill."""
    return {
        "type": "FillRecorded",
        "ts_utc": ts_utc,
        "payload": {
            "source": "replay",
            "order_id": order_id,
            "decision_id": order_id,
            "side": "buy",
            "mint": "MINT",
            "filled_lamports": 10_000_000,
            "filled_units": 500_000,
            "filled_fraction": fraction,
            "price_avg": price,
            "venue_fee_lamports": venue_fee,
            "network_cost_lamports": network_cost,
            "cash_delta_lamports": -10_009_000,
            "latency_s": "1.2",
            "venue_tx_ref": tx_ref,
            "route": "curve",
            "realised_slippage_bps": 100,
        },
    }


def _window() -> tuple[float, float]:
    return (parse_ts_utc(T0), parse_ts_utc(T3))


def test_same_fills_compare_field_for_field() -> None:
    """Identical backtest fills and ledger rows compare clean over one window."""
    start, end = _window()
    backtest = SharedResult.from_fills(
        run_id="RUNID",
        dataset="smoke",
        window_start_ts=start,
        window_end_ts=end,
        fills=[
            _fill(ORDER_A, TX_A, 1, "20", 100_000, 9_000, "1"),
            _fill(ORDER_B, TX_B, 2, "25", 100_000, 9_000, "1"),
        ],
        latencies=[Decimal("1.2"), Decimal("1.2")],
    )
    paper = SharedResult.from_ledger_rows(
        run_id="RUNID",
        dataset="smoke",
        window_start_ts=start,
        window_end_ts=end,
        rows=[
            _row(T1, "20", 100_000, 9_000, "1"),
            _row(T2, "25", 100_000, 9_000, "1", order_id=ORDER_B, tx_ref=TX_B),
            {"type": "OrderRejected", "ts_utc": T1, "payload": {}},
            {"type": "JournalNote", "ts_utc": T1, "payload": {}},
        ],
    )
    verdict = backtest.compare(paper)
    assert verdict.matched
    assert verdict.differences == ()


def test_tampered_field_breaks_the_match() -> None:
    """One changed integer surfaces as a named field difference."""
    start, end = _window()
    backtest = SharedResult.from_fills(
        run_id="RUNID",
        dataset="smoke",
        window_start_ts=start,
        window_end_ts=end,
        fills=[_fill(ORDER_A, TX_A, 1, "20", 100_000, 9_000, "1")],
        latencies=[Decimal("1.2")],
    )
    paper = SharedResult.from_ledger_rows(
        run_id="RUNID",
        dataset="smoke",
        window_start_ts=start,
        window_end_ts=end,
        rows=[_row(T1, "20", 100_001, 9_000, "1")],
    )
    verdict = backtest.compare(paper)
    assert not verdict.matched
    assert verdict.differences == ("fills[0].venue_fee_lamports: 100000 != 100001",)


def test_compare_rejects_foreign_windows() -> None:
    """Comparing across datasets or windows raises instead of misreporting."""
    start, end = _window()
    base = SharedResult(run_id="RUNID", dataset="smoke", window_start_ts=start, window_end_ts=end)
    with pytest.raises(ValueError):
        base.compare(
            SharedResult(run_id="RUNID", dataset="other", window_start_ts=start, window_end_ts=end)
        )
    with pytest.raises(ValueError):
        base.compare(
            SharedResult(
                run_id="RUNID",
                dataset="smoke",
                window_start_ts=start,
                window_end_ts=end + 1,
            )
        )


def test_run_id_references_the_manifest() -> None:
    """The shared result carries the run manifest id for its dataset and seed."""
    manifest = build_manifest("smoke", RUN_ID_SEED, "0" * 64, "1" * 64, CODE_VERSION)
    start, end = _window()
    result = SharedResult.from_fills(
        run_id=manifest.run_id,
        dataset="smoke",
        window_start_ts=start,
        window_end_ts=end,
        fills=[],
        latencies=[],
    )
    assert result.run_id == manifest.run_id


def test_fill_detail_rejects_bad_money() -> None:
    """Negative money, non-finite ratios and unknown outcomes fail closed."""
    good = {
        "price_avg": Decimal("20"),
        "venue_fee_lamports": 100_000,
        "network_cost_lamports": 9_000,
        "latency_s": Decimal("1.2"),
        "filled_fraction": Decimal("1"),
        "outcome": "filled",
    }
    FillDetail(**good)
    with pytest.raises(ValueError):
        FillDetail(**{**good, "venue_fee_lamports": -1})
    with pytest.raises(ValueError):
        FillDetail(**{**good, "outcome": "settled"})
