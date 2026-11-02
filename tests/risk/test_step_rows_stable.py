"""Risk step rows stay stable: 19 STEP_IDS and an unchanged risk_json shape (QLT-05, RSK-08).

The 11-04 split of RiskEngine._evaluate must not change the vocabulary, the order, the row
shape of RiskDecision.evaluated or the risk_json the paper adapter persists on OrderPlaced.
Each pinned value was recorded on the unsplit code at this branch's HEAD.
"""

from __future__ import annotations

import contextlib
import io
import json
import random
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.cli import main as cli_main
from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.engine import STEP_IDS, RiskDecision, RiskEngine, order_hash_for
from pumpgrok.tools.risk.check_limits import R34_RULE_IDS

PINNED_STEP_IDS: tuple[str, ...] = (
    "ledger_inconsistent",
    "kill_switch",
    "halted",
    "breaker_open",
    "live_gate",
    "approval_missing",
    "approval_mismatch",
    "seat_may_trade",
    "max_trades_per_day",
    "max_open_positions",
    "already_open",
    "creator_already_open",
    "max_trade_fraction",
    "max_token_fraction",
    "daily_loss_halt",
    "drawdown_halt",
    "data_stale",
    "size_too_small",
    "below_liquidity_floor",
)
PINNED_DECISION_FIELDS = frozenset(
    {
        "passed",
        "reason",
        "order_hash",
        "decision_id",
        "approval_id",
        "approval",
        "size_lamports",
        "token_units",
        "capped",
        "caps",
        "probe",
        "evaluated",
    }
)
PINNED_RISK_JSON_KEYS = frozenset({"capped", "caps", "order_hash", "reason"})
PASS_ROW_STATUSES = frozenset({"pass", "fail", "skip"})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_START = 1_792_540_800.0  # 2026-10-21T00:00:00Z, the day used by tests/risk/test_engine.py


def test_step_ids_are_the_pinned_nineteen_in_order() -> None:
    assert STEP_IDS == PINNED_STEP_IDS
    assert len(STEP_IDS) == 19


def test_step_ids_match_the_r34_rule_vocabulary() -> None:
    assert list(STEP_IDS) == list(R34_RULE_IDS)


def test_decision_field_names_are_pinned() -> None:
    assert set(RiskDecision.model_fields) == PINNED_DECISION_FIELDS


def test_a_walked_buy_carries_nineteen_id_and_status_rows(tmp_path: Path) -> None:
    clock = FixtureClock(start=_START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    ids = IdFactory(clock, random.Random(11))
    try:
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=ids,
            clock=clock,
            autonomy="autonomous-paper",
            get_reserves=lambda _mint: (42_000_000_000, 764_000_000_000_000),
        )
        order = OrderRequest(
            ticket_id="SOL-20260201-001",
            mint="So11111111111111111111111111111111111111112",
            side="buy",
            decision_id=ids.ulid(),
            size_lamports=200_000_000,
            max_slippage_bps=50,
            approval_id=f"apr-{ids.ulid()}",
            correlation_id="test",
        )
        decision = engine.check(order, seat="bot-04-sniper")
    finally:
        store.close()
    assert decision.passed is True
    assert len(decision.evaluated) == 19
    for row in decision.evaluated:
        assert set(row) == {"id", "status"}
        assert row["status"] in PASS_ROW_STATUSES
    assert [row["id"] for row in decision.evaluated] == list(PINNED_STEP_IDS)
    assert {row["status"] for row in decision.evaluated} == {"pass"}
    assert decision.order_hash == order_hash_for(order)


def _smoke_ledger(monkeypatch: pytest.MonkeyPatch, cwd: Path) -> Path:
    monkeypatch.chdir(cwd)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        code = cli_main(["verify", "--fixture", "smoke"])
    assert code == 0
    return cwd / "var" / "replay" / "smoke" / "ledger.sqlite"


def _placed_risk_json(ledger: Path) -> list[str]:
    conn = sqlite3.connect(str(ledger))
    try:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE type = 'OrderPlaced' ORDER BY seq"
        ).fetchall()
    finally:
        conn.close()
    texts: list[str] = []
    for (payload_json,) in rows:
        payload: dict[str, Any] = json.loads(payload_json)
        texts.append(str(payload["risk_json"]))
    return texts


def test_risk_json_on_placed_orders_keeps_its_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    texts = _placed_risk_json(_smoke_ledger(monkeypatch, tmp_path))
    assert len(texts) == 2
    for text in texts:
        parsed = json.loads(text)
        assert set(parsed) == PINNED_RISK_JSON_KEYS
        assert parsed["reason"] == "pass"
        assert parsed["capped"] is False
        assert parsed["caps"] == {}
        assert _HEX64.match(str(parsed["order_hash"])) is not None
        assert text == canonical_json(parsed)


def test_nineteen_rows_are_not_persisted_in_risk_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The 19 evaluated rows live on RiskDecision.evaluated; risk_json carries the summary only.
    for text in _placed_risk_json(_smoke_ledger(monkeypatch, tmp_path)):
        assert "evaluated" not in json.loads(text)
