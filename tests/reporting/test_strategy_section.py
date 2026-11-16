"""OBS-07: the per-strategy section sums to the desk view, and is absent otherwise."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pumpgrok.backtest.metrics_v2 import MetricsV2
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.ticket_refs import append_with_ticket_ref
from pumpgrok.reporting.daily import DailyReport
from pumpgrok.reporting.render import render_daily, render_weekly
from pumpgrok.reporting.strategy_section import (
    METRIC_COLUMNS,
    DeskView,
    StrategySectionRow,
    existing_render_daily,
    existing_render_weekly,
    render_strategy_section,
    section_from_events,
)
from pumpgrok.reporting.weekly import WeeklyReport

DAY = "2026-10-20"
START = DAY + "T00:00:00.000000Z"
END = "2026-10-21T00:00:00.000000Z"
MINT = "MintAAAAAAAA"
CID = "01J0000000000000000000000"
TICKET = "SOL-20261020-001"


def _metrics(**overrides: object) -> MetricsV2:
    values: dict[str, object] = {
        "total_return": None,
        "max_drawdown": None,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "hit_rate": None,
        "profit_factor": None,
        "expectancy_lamports": None,
        "annualization_valid": False,
    }
    values.update(overrides)
    return MetricsV2(**values)  # type: ignore[arg-type]


def _desk(realized: int, **overrides: object) -> DeskView:
    return DeskView(realized_lamports=realized, metrics=_metrics(**overrides))


def _strategy_realized(body: str) -> list[int]:
    section = body.split("## Strategies\n", 1)[1]
    lines = section.splitlines()
    assert lines[0].startswith("strategy | ")
    values: list[int] = []
    for line in lines[1:]:
        if not line or line.startswith("desk view"):
            break
        values.append(int(line.rsplit(" | ", 1)[-1]))
    return values


def _desk_realized(body: str) -> int:
    prefix = "desk view realized_lamports: "
    for line in body.splitlines():
        if line.startswith(prefix):
            return int(line[len(prefix) :])
    raise AssertionError("desk view line missing")


def test_fixed_rows_sum_to_the_desk_view_and_print_none() -> None:
    rows = (
        StrategySectionRow(
            "alpha",
            30,
            _metrics(hit_rate=Decimal("1"), expectancy_lamports=Decimal("30")),
        ),
        StrategySectionRow(
            "unattributed",
            -40,
            _metrics(hit_rate=Decimal("0"), expectancy_lamports=Decimal("-40")),
        ),
    )
    body = render_strategy_section(rows, _desk(-10))
    body.encode("ascii")
    assert body.startswith("## Strategies\n")
    header = body.splitlines()[1]
    for name in METRIC_COLUMNS:
        assert name in header
    assert "annualization_valid" in header
    assert "None" in body
    assert "false" in body
    assert _strategy_realized(body) == [30, -40]
    assert sum(_strategy_realized(body)) == _desk_realized(body) == -10


def test_mismatch_raises() -> None:
    rows = (StrategySectionRow("alpha", 1, _metrics()),)
    with pytest.raises(ValueError, match="does not sum to desk view"):
        render_strategy_section(rows, _desk(0))


def test_empty_rows_render_an_empty_string() -> None:
    assert render_strategy_section((), _desk(5)) == ""


def _event(seq: int, row_type: str, payload: dict[str, object], ts: str) -> dict[str, object]:
    return {"seq": seq, "ts_utc": ts, "type": row_type, "payload": payload}


def _fill(seq: int, side: str, units: int, cash: int, ts: str) -> dict[str, object]:
    return _event(
        seq,
        "FillRecorded",
        {
            "side": side,
            "mint": MINT,
            "filled_units": units,
            "cash_delta_lamports": cash,
            "venue_fee_lamports": 0,
            "network_cost_lamports": 0,
        },
        ts,
    )


def _opened(seq: int, ticket: str, ts: str) -> dict[str, object]:
    return _event(
        seq,
        "PositionOpened",
        {
            "mint": MINT,
            "ticket_id": ticket,
            "price_entry": "1",
            "token_units": 10,
            "cost_basis_lamports": 100,
            "opened_ts_utc": ts,
        },
        ts,
    )


def test_breakdown_rows_sum_to_the_desk_view() -> None:
    ts = DAY + "T12:00:00.000000Z"
    events = [
        _fill(1, "buy", 10, -100, ts),
        _opened(2, "T1", ts),
        _fill(3, "sell", 10, 130, ts),
        _fill(4, "buy", 10, -200, ts),
        _opened(5, "", ts),
        _fill(6, "sell", 10, 150, ts),
    ]
    # The second lifecycle has an empty ticket, so the breakdown keys it unattributed.
    # Two mints would be required for overlapping lifecycles; these are sequential.
    body = section_from_events(
        events,
        {"T1": "alpha"},
        start=START,
        end=END,
        elapsed_days=Decimal(1),
        initial_equity_lamports=1_000,
        deposits={},
    )
    assert "alpha" in body
    assert "unattributed" in body
    assert sum(_strategy_realized(body)) == _desk_realized(body)


def test_unattributed_only_window_renders_nothing() -> None:
    ts = DAY + "T12:00:00.000000Z"
    events = [
        _fill(1, "buy", 10, -100, ts),
        _opened(2, "T9", ts),
        _fill(3, "sell", 10, 110, ts),
    ]
    assert (
        section_from_events(
            events,
            {"OTHER": "alpha"},
            start=START,
            end=END,
            elapsed_days=Decimal(1),
            initial_equity_lamports=0,
        )
        == ""
    )


def test_daily_and_weekly_without_strategy_rows_match_the_existing_renderer(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "var" / "ledger.sqlite"
    daily = DailyReport.build(missing, DAY)
    assert render_daily(daily) == existing_render_daily(daily)
    assert "## Strategies" not in render_daily(daily)
    assert not missing.exists()
    weekly = WeeklyReport.build(missing, DAY, root=tmp_path)
    assert render_weekly(weekly) == existing_render_weekly(weekly)
    assert "## Strategies" not in render_weekly(weekly)


def _store_append(
    store: LedgerStore,
    key: str,
    row_type: str,
    payload: dict[str, object],
    ts: str,
) -> None:
    store.append(
        ts_utc=ts,
        source="paper",
        correlation_id=CID,
        idempotency_key=key,
        type=row_type,
        payload=payload,
    )


def _ledger(path: Path, *, strategy: str | None) -> Path:
    ledger = path / "ledger.sqlite"
    store = LedgerStore(ledger)
    try:
        _store_append(
            store,
            "buy-1",
            "FillRecorded",
            {
                "source": "paper",
                "order_id": "ord-1",
                "decision_id": "dec-1",
                "side": "buy",
                "mint": MINT,
                "filled_lamports": 100,
                "filled_units": 10,
                "filled_fraction": "1",
                "price_avg": "1",
                "cash_delta_lamports": -100,
                "venue_tx_ref": "dry_run:buy-1",
            },
            DAY + "T10:00:00Z",
        )
        opened = {
            "ts_utc": DAY + "T10:00:01Z",
            "source": "paper",
            "correlation_id": CID,
            "idempotency_key": "open-1",
            "type": "PositionOpened",
            "payload": {
                "source": "paper",
                "mint": MINT,
                "price_entry": "1",
                "token_units": 10,
                "cost_basis_lamports": 100,
                "opened_ts_utc": DAY + "T10:00:00Z",
                "ticket_id": TICKET,
            },
        }
        if strategy is None:
            store.append(**opened)
        else:
            append_with_ticket_ref(store, opened, ticket_id=TICKET, strategy_id=strategy)
        _store_append(
            store,
            "sell-1",
            "FillRecorded",
            {
                "source": "paper",
                "order_id": "ord-2",
                "decision_id": "dec-2",
                "side": "sell",
                "mint": MINT,
                "filled_lamports": 130,
                "filled_units": 10,
                "filled_fraction": "1",
                "price_avg": "1",
                "cash_delta_lamports": 130,
                "venue_tx_ref": "dry_run:sell-1",
            },
            DAY + "T15:00:00Z",
        )
    finally:
        store.close()
    return ledger


def test_ledger_without_refs_matches_the_existing_renderer(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, strategy=None)
    daily = DailyReport.build(ledger, DAY)
    assert render_daily(daily) == existing_render_daily(daily)
    weekly = WeeklyReport.build(ledger, DAY, root=tmp_path)
    assert render_weekly(weekly) == existing_render_weekly(weekly)


def test_attributed_period_appends_a_section_that_sums(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, strategy="alpha")
    daily_model = DailyReport.build(ledger, DAY)
    plain = existing_render_daily(daily_model)
    body = render_daily(daily_model)
    assert body.startswith(plain)
    assert body[len(plain) :].startswith("\n## Strategies\n")
    assert sum(_strategy_realized(body)) == _desk_realized(body)
    assert "None" in body
    assert "desk view annualization_valid: false" in body

    weekly_model = WeeklyReport.build(ledger, DAY, root=tmp_path)
    plain_week = existing_render_weekly(weekly_model)
    week = render_weekly(weekly_model)
    assert week.startswith(plain_week)
    assert week[len(plain_week) :].startswith("\n## Strategies\n")
    assert sum(_strategy_realized(week)) == _desk_realized(week)
    assert "desk view annualization_valid: true" in week
