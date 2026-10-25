"""Characterization: vendor-shape trade log export (STRUCT-004).

Pins ``ledger/export.py`` against ``vendor/grokbot-pumpfun/src/log.py:98-183``
(``TradeLog.buy/skip/close`` record shapes) and
``vendor/grokbot-pumpfun/tests/test_log.py`` (vendor oracle, kept
byte-identical per R53).

Adaptations from the oracle (deliberate):

- The vendor appends records directly; the desk derives the same three
  shapes from the hash-chained ledger through one ``export_seq`` cursor, so
  ``pumpgrok scout pipeline --candidates`` and the vendor dashboard keep
  reading them (paper-engine 3.6, MIGRATION_MAP 3.1). Rotation
  not ported: the cursor resume replaces it, and the journal is sharded by
  UTC day instead.
- ``mode`` stamps the R21 source vocabulary (``paper``) rather than the
  vendor ``dry-run``. ``tx_hash`` stays the bare ``dry_run`` string so the
  ``--candidates`` filter (``tx_hash == dry_run``) keeps matching; the
  unique paper ref rides in ``venue_tx_ref`` as ``dry_run:<ULID>``
  (paper-engine 964).
- Component scores (audit/narrative/timing/metrics) and the token snapshot
  live in the canonical journal rows, not in this compatibility file: the
  ledger payloads never carried agent internals.
- Broken-line tolerance (vendor ``read_log`` skipping corrupt lines) has no
  analog: the ledger refuses torn writes at the cursor layer instead.
- All prose is English; the vendor text is Russian.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from pumpgrok.ledger.export import DRY_RUN_TX, export_ledger
from pumpgrok.ledger.store import LedgerStore

MINT = "Mint1111CATS1111111111111111111111111111111"
REF = "dry_run:01J0000000000000000000004"


def _envelope(entry_type: str, payload: dict[str, Any], key: str, ts: str) -> dict[str, Any]:
    return {
        "ts_utc": ts,
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "idempotency_key": key,
        "type": entry_type,
        "payload": payload,
    }


def _fill_payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source": "paper",
        "order_id": "01J0000000000000000000002",
        "decision_id": "01J0000000000000000000003",
        "side": "buy",
        "mint": MINT,
        "filled_lamports": 200_000_000,
        "filled_units": 3579186000000,
        "filled_fraction": "1",
        "price_avg": "5.532e-5",
        "venue_fee_lamports": 2000000,
        "network_cost_lamports": 9000,
        "cash_delta_lamports": -200009000,
        "latency_s": "1.4",
        "venue_tx_ref": REF,
    }
    base.update(overrides)
    return base


def _rejected_payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source": "paper",
        "order_id": "01J0000000000000000000006",
        "decision_id": "01J0000000000000000000007",
        "reason": "slippage_exceeded",
        "detail": "confirm-out below threshold",
        "stage": "CONFIRMING",
        "fees_lamports": 9000,
    }
    base.update(overrides)
    return base


def _closed_payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source": "paper",
        "mint": MINT,
        "price_exit": "6.2e-5",
        "proceeds_lamports": 225000000,
        "realized_pnl_lamports": 25000000,
        "reason": "take_profit",
        "pnl_pct": "12.5",
        "hold_seconds": 300,
        "venue_tx_ref": "dry_run:01J0000000000000000000005",
    }
    base.update(overrides)
    return base


def _export(tmp_path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.set_meta("source", "paper")
    store.set_meta("initial_equity_lamports", "10000000000")
    store.append_batch(rows)
    trades_path = tmp_path / "trades.jsonl"
    result = export_ledger(store, journal_dir=tmp_path / "journal", trades_path=trades_path)
    assert result["trade_lines"] == len(rows)
    return [json.loads(line) for line in trades_path.read_text(encoding="utf-8").splitlines()]


def _buy_row(ts: str = "2026-01-01T00:00:01.000001Z") -> dict[str, Any]:
    return _envelope("FillRecorded", _fill_payload(), "fill-key-0001", ts)


# --- buy --------------------------------------------------------------------


def test_buy_line_carries_vendor_keys(tmp_path: Path) -> None:
    (line,) = _export(tmp_path, [_buy_row()])
    assert line["type"] == "buy"
    assert line["mint"] == MINT
    assert line["symbol"] == ""
    assert Decimal(line["size_sol"]) * 1_000_000_000 == 200_000_000
    assert Decimal(line["entry_price"]) * 1000 == Decimal("5.532e-5")
    assert isinstance(line["ts"], float) and line["ts"] > 0
    assert line["seq"] == 1


def test_buy_tx_hash_is_bare_dry_run_with_venue_ref(tmp_path: Path) -> None:
    """The evidence filter matches ``tx_hash == dry_run``; uniqueness rides along."""
    (line,) = _export(tmp_path, [_buy_row()])
    assert line["tx_hash"] == "dry_run"
    assert line["venue_tx_ref"] == REF
    assert line["venue_tx_ref"].startswith(DRY_RUN_TX + ":")


def test_buy_without_venue_ref_still_matches_filter(tmp_path: Path) -> None:
    payload = _fill_payload()
    del payload["venue_tx_ref"]
    (line,) = _export(
        tmp_path,
        [_envelope("FillRecorded", payload, "fill-key-0002", "2026-01-01T00:00:01.000001Z")],
    )
    assert line["tx_hash"] == "dry_run"
    assert line["venue_tx_ref"] == ""


def test_buy_mode_uses_source_vocabulary(tmp_path: Path) -> None:
    """R21 source vocabulary (``paper``), not the vendor ``dry-run`` mode string."""
    (line,) = _export(tmp_path, [_buy_row()])
    assert line["mode"] == "paper"


# --- skip -------------------------------------------------------------------


def test_skip_line_carries_stage_and_r34_reason(tmp_path: Path) -> None:
    row = _envelope(
        "OrderRejected", _rejected_payload(), "rej-key-0001", "2026-01-01T00:00:02.000001Z"
    )
    (line,) = _export(tmp_path, [row])
    assert line["type"] == "skip"
    assert line["mint"] == ""
    assert line["stage"] == "CONFIRMING"
    assert line["reason"] == "slippage_exceeded"
    assert line["detail"] == "confirm-out below threshold"
    assert "tx_hash" not in line


def test_skip_reason_is_a_code_never_free_text(tmp_path: Path) -> None:
    row = _envelope(
        "OrderRejected",
        _rejected_payload(reason="size_too_small"),
        "rej-key-0002",
        "2026-01-01T00:00:02.000001Z",
    )
    (line,) = _export(tmp_path, [row])
    assert line["reason"] == "size_too_small"
    assert " " not in line["reason"]


# --- close ------------------------------------------------------------------


def test_close_line_computes_vendor_fields(tmp_path: Path) -> None:
    row = _envelope(
        "PositionClosed", _closed_payload(), "close-key-0001", "2026-01-01T00:00:03.000001Z"
    )
    (line,) = _export(tmp_path, [row])
    assert line["type"] == "close"
    assert line["mint"] == MINT
    assert Decimal(line["exit_price"]) * 1000 == Decimal("6.2e-5")
    assert Decimal(line["pnl_sol"]) * 1_000_000_000 == 25_000_000
    assert line["pnl_pct"] == float("12.5")
    assert line["hold_seconds"] == 300
    assert line["reason"] == "take_profit"
    assert line["tx_hash"] == "dry_run"
    assert line["venue_tx_ref"] == "dry_run:01J0000000000000000000005"


def test_close_loss_carries_negative_pnl(tmp_path: Path) -> None:
    payload = _closed_payload(
        realized_pnl_lamports=-120_000_000, pnl_pct="-30.0", reason="stop_loss"
    )
    row = _envelope("PositionClosed", payload, "close-key-0002", "2026-01-01T00:00:03.000001Z")
    (line,) = _export(tmp_path, [row])
    assert Decimal(line["pnl_sol"]) * 1_000_000_000 == -120_000_000
    assert line["pnl_pct"] == float("-30.0")
    assert line["reason"] == "stop_loss"


# --- cursor -----------------------------------------------------------------


def test_export_writes_no_duplicates_on_rerun(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.set_meta("source", "paper")
    store.set_meta("initial_equity_lamports", "10000000000")
    store.append_batch([_buy_row()])
    trades_path = tmp_path / "trades.jsonl"
    first = export_ledger(store, journal_dir=tmp_path / "journal", trades_path=trades_path)
    assert first == {"journal_lines": 1, "trade_lines": 1, "export_seq": 1}
    second = export_ledger(store, journal_dir=tmp_path / "journal", trades_path=trades_path)
    assert second == {"journal_lines": 0, "trade_lines": 0, "export_seq": 1}
    assert len(trades_path.read_text(encoding="utf-8").splitlines()) == 1


def test_journal_row_keeps_full_payload(tmp_path: Path) -> None:
    """The compatibility file is reduced; the journal row keeps every lamport."""
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.set_meta("source", "paper")
    store.set_meta("initial_equity_lamports", "10000000000")
    store.append_batch([_buy_row()])
    journal_dir = tmp_path / "journal"
    export_ledger(store, journal_dir=journal_dir, trades_path=tmp_path / "trades.jsonl")
    (line,) = (journal_dir / "2026-01-01.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(line)
    assert row["payload"]["filled_lamports"] == 200_000_000
    assert row["payload"]["venue_tx_ref"] == REF
    assert row["correlation_id"] == "01J0000000000000000000001"
