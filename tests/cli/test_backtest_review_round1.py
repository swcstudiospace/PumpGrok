"""Review round 1 regressions for the backtest verb (findings 4-7, 9, 11, 12, 20, 21).

Money paths are checked on synthetic ledger rows folded by the real reducer. The
verb-level checks run the bundled smoke fixture under tmp_path, offline.
"""

from __future__ import annotations

import fcntl
import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import pumpgrok.backtest.evaluate as evaluate_module
import pumpgrok.backtest.harness as harness_module
from pumpgrok.backtest.evaluate import CandidateParams, evaluated_settings_hash
from pumpgrok.backtest.manifest import dataset_digest
from pumpgrok.cli import main
from pumpgrok.cli.backtest import (
    _backtest_dataset,
    _fills_from_rows,
    _paper_window,
    _rejection_fees,
    _window_curve,
)
from pumpgrok.ledger.reducer import LedgerState, initial_state
from pumpgrok.replay.clock import format_ts_utc

REPO = Path(__file__).resolve().parents[2]
_GENESIS_EQUITY = 1_000_000
_T0 = 1_800_000_000.0
_MINT = "So11111111111111111111111111111111111111112"
_ULID_BUY = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
_ULID_SELL = "01BX5ZZKBKACTAV9WEVGEMMVRY"
_ULID_DECISION = "01CP4Y3KW7W6CNMS3Z0AF8V0SA"


def _genesis() -> LedgerState:
    return initial_state(source="backtest", initial_equity_lamports=_GENESIS_EQUITY, day_utc="")


def _row(seq: int, kind: str, payload: dict[str, Any], stamp: float = _T0) -> dict[str, Any]:
    return {
        "seq": seq,
        "ts_utc": format_ts_utc(stamp),
        "type": kind,
        "payload": payload,
        "correlation_id": "t",
    }


def _fill_payload(
    order_id: str, side: str, lamports: int, units: int, cash_delta: int
) -> dict[str, Any]:
    return {
        "side": side,
        "mint": _MINT,
        "order_id": order_id,
        "decision_id": _ULID_DECISION,
        "filled_lamports": lamports,
        "filled_units": units,
        "filled_fraction": "1",
        "price_avg": "20000",
        "venue_fee_lamports": 0,
        "network_cost_lamports": 0,
        "cash_delta_lamports": cash_delta,
        "venue_tx_ref": f"dry_run:{order_id}",
        "route": "curve",
        "realised_slippage_bps": 0,
    }


def _opened_payload() -> dict[str, Any]:
    return {
        "mint": _MINT,
        "symbol": "",
        "creator": "",
        "ticket_id": "",
        "price_entry": "20000",
        "token_units": 10,
        "cost_basis_lamports": 200_000,
        "opened_ts_utc": format_ts_utc(_T0),
    }


def _closed_payload() -> dict[str, Any]:
    return {"mint": _MINT, "realized_pnl_lamports": -50_000, "reason": "manual"}


def _rejected_payload(fees: int) -> dict[str, Any]:
    return {
        "reason": "slippage",
        "fees_lamports": fees,
        "order_id": _ULID_SELL,
        "decision_id": _ULID_DECISION,
        "stage": "confirm",
    }


def test_refused_attempt_fee_reduces_the_curve_and_the_report_total() -> None:
    """F4: a paid refusal is cash out, so the curve and the fee total must carry it."""
    rows = [
        _row(1, "FillRecorded", _fill_payload(_ULID_BUY, "buy", 200_000, 10, -200_000)),
        _row(2, "PositionOpened", _opened_payload()),
        _row(3, "OrderRejected", _rejected_payload(300)),
    ]

    assert _rejection_fees(rows) == 300
    assert _window_curve(_genesis(), rows) == (_GENESIS_EQUITY - 300,)


def test_purchase_is_not_a_loss_and_a_losing_sale_is_one() -> None:
    """F5: the buy cash outflow stays at cost; only the sale's shortfall is a loss."""
    rows = [
        _row(1, "FillRecorded", _fill_payload(_ULID_BUY, "buy", 200_000, 10, -200_000)),
        _row(2, "PositionOpened", _opened_payload()),
        _row(3, "FillRecorded", _fill_payload(_ULID_SELL, "sell", 150_000, 10, 150_000)),
        _row(4, "PositionClosed", _closed_payload()),
    ]

    assert _window_curve(_genesis(), rows) == (_GENESIS_EQUITY, _GENESIS_EQUITY - 50_000)


def test_paper_window_opens_at_cutoff_and_stops_at_the_recording_end() -> None:
    """F6: pre-cutoff rows set the opening equity; rows at or past the end are excluded."""
    cutoff = _T0
    recording_end = _T0 + 500.0
    rows = [
        _row(1, "OrderRejected", _rejected_payload(500), stamp=cutoff - 100.0),
        _row(
            2,
            "FillRecorded",
            _fill_payload(_ULID_BUY, "buy", 200_000, 10, -200_000),
            stamp=cutoff + 10,
        ),
        _row(3, "PositionOpened", _opened_payload(), stamp=cutoff + 10),
        _row(
            4,
            "FillRecorded",
            _fill_payload(_ULID_SELL, "sell", 150_000, 10, 150_000),
            stamp=recording_end + 1.0,
        ),
    ]

    opening, window_rows = _paper_window(
        rows, cutoff=cutoff, recording_end=recording_end, initial=_GENESIS_EQUITY
    )

    assert opening.cash_lamports == _GENESIS_EQUITY - 500
    assert [row["seq"] for row in window_rows] == [2, 3]
    fills, _ = _fills_from_rows(window_rows)
    assert len(fills) == 1
    assert _window_curve(opening, window_rows) == (_GENESIS_EQUITY - 500,)


def test_forced_close_row_becomes_a_fill_without_an_order_decision() -> None:
    """F7: a graduation or blind close records decision_id "" and must still build a fill."""
    proceeds = 180_000
    row = _row(
        7,
        "FillRecorded",
        {
            "source": "paper",
            "order_id": _ULID_SELL,
            "decision_id": "",
            "side": "sell",
            "mint": _MINT,
            "filled_lamports": proceeds,
            "filled_units": 10,
            "filled_fraction": "1",
            "price_avg": "18000",
            "venue_fee_lamports": 0,
            "network_cost_lamports": 0,
            "cash_delta_lamports": proceeds,
            "venue_tx_ref": f"dry_run:{_ULID_SELL}",
            "route": "curve",
        },
    )

    fills, latencies = _fills_from_rows([row])

    assert len(fills) == 1
    assert fills[0].decision_id == ""
    assert fills[0].filled_lamports == proceeds
    assert fills[0].ledger_seq == 7
    assert latencies == [Decimal("0")]


def test_report_identifies_the_filter_set_the_replay_evaluates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """F9: the identity covers the effective filter, exits, risk budget and limits."""
    monkeypatch.chdir(tmp_path)
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"filter": {"min_unique_buyers": 7}}), encoding="utf-8")

    code = main(["backtest", "--fixture", "smoke", "--params", str(params)])
    out = capsys.readouterr().out

    assert code == 0
    expected = evaluated_settings_hash(CandidateParams(filter={"min_unique_buyers": 7}))
    assert f"filter_settings_hash: {expected}\n" in out


def test_identical_run_is_refused_while_the_run_directory_is_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """F11: an identical live run is refused and leaves the first run's files alone."""
    monkeypatch.chdir(tmp_path)
    assert main(["backtest", "--fixture", "smoke"]) == 0
    first_out = capsys.readouterr().out
    (run_dir,) = (tmp_path / "var" / "backtest").iterdir()
    trials_before = (run_dir / "trials.jsonl").read_bytes()

    with (run_dir / ".lock").open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        code = main(["backtest", "--fixture", "smoke"])
        err = capsys.readouterr().err

    assert code == 1
    assert "already running" in err
    assert (run_dir / "trials.jsonl").read_bytes() == trials_before

    assert main(["backtest", "--fixture", "smoke"]) == 0
    assert capsys.readouterr().out == first_out


def test_float_parameter_is_a_usage_error_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """F12: a float leaf in --params exits 1 with the usage message, never a traceback."""
    monkeypatch.chdir(tmp_path)
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"filter": {"max_curve_progress": 0.25}}), encoding="utf-8")

    code = main(["backtest", "--fixture", "smoke", "--params", str(params)])
    err = capsys.readouterr().err

    assert code == 1
    assert "usage error: bad --params" in err


def test_recording_path_replays_its_own_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """F21: a nested recording is read from its own directory, not a same-named fixture."""
    recording = tmp_path / "tests" / "fixtures" / "replay" / "session" / "recording-copy"
    shutil.copytree(REPO / "tests" / "fixtures" / "replay" / "smoke", recording)
    monkeypatch.setattr("pumpgrok.cli.backtest._repo_root", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)

    spec = _backtest_dataset(str(recording))

    assert spec.ref == str(recording.resolve())
    assert spec.directory == recording.resolve()
    assert spec.name == "recording-copy"
    code = main(["backtest", "--fixture", str(recording)])
    out = capsys.readouterr().out
    assert code == 0
    assert f"dataset_digest: {dataset_digest(recording)}\n" in out


def test_holdout_is_replayed_once_per_backtest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """F20: one backtest replays the holdout window exactly once."""
    monkeypatch.chdir(tmp_path)
    real_evaluate = harness_module.evaluate_window
    real_replay = evaluate_module.run_once_replay
    holdout_replays: list[Path] = []
    replays: list[Path] = []

    def counting_window(dataset: Any, params: Any, **kwargs: Any) -> int:
        if kwargs["window"].end_ts == float("inf"):
            holdout_replays.append(Path(kwargs["ledger_path"]))
        return real_evaluate(dataset, params, **kwargs)

    def counting_replay(dataset_dir: Any, filter_cfg: Any, **kwargs: Any) -> Any:
        replays.append(Path(kwargs["ledger_path"]))
        return real_replay(dataset_dir, filter_cfg, **kwargs)

    monkeypatch.setattr(harness_module, "evaluate_window", counting_window)
    monkeypatch.setattr(evaluate_module, "run_once_replay", counting_replay)

    assert main(["backtest", "--fixture", "smoke"]) == 0
    capsys.readouterr()
    assert len(holdout_replays) == 1
    assert holdout_replays[0].name == "holdout.sqlite"
    # Three tuning folds plus the one holdout replay; the CLI adds no replay of its own.
    assert len(replays) == 4
