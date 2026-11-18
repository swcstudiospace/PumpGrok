"""RSK-02: a strategy kill refuses that strategy's buys, never its sells, and only a human sets or
clears it, through the ledger and the ``killswitch set|clear --strategy`` verbs."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.strategy_kill import (
    StrategyKillRefused,
    clear_strategy_kill,
    set_strategy_kill,
)

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
MINT_A = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
BUY_SEAT = "bot-04-sniper"
SELL_SEAT = "bot-06-exit"
BIG_RESERVES = (42_000_000_000, 764_000_000_000_000)


def _open(path: Path) -> LedgerStore:
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock) -> RiskEngine:
    return RiskEngine(
        store=store,
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="autonomous-paper",
        budget=RiskBudget(),
        get_reserves=lambda _mint: BIG_RESERVES,
    )


def _buy(ids: IdFactory, ticket: str = TICKET) -> OrderRequest:
    return OrderRequest(
        ticket_id=ticket,
        mint=MINT_A,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=200_000_000,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _sell(ids: IdFactory) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT_A,
        side="sell",
        decision_id=ids.ulid(),
        token_units=3_000_000,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _clear_approval(clock: FixtureClock, ids: IdFactory, kind: str = "killswitch_clear"):
    return ApprovalRecord(
        id=f"apr-{ids.ulid()}",
        kind=kind,  # type: ignore[arg-type]
        approved_by="human:alice",
        raw_message="clear",
        at=datetime.fromtimestamp(clock.now(), UTC),
    )


def test_a_strategy_kill_refuses_only_that_strategys_buys(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _open(tmp_path / "ledger.sqlite")
    ids = IdFactory(clock, random.Random(7))
    try:
        set_strategy_kill(store, "alpha", "halt alpha", "human:alice", ts_utc=format_ts_utc(START))
        engine = _engine(store, clock)
        alpha = engine.check(_buy(ids), seat=BUY_SEAT, strategy_id="alpha")
        assert alpha.passed is False
        assert alpha.reason == "kill_switch"
        beta = engine.check(_buy(ids, "SOL-20260201-002"), seat=BUY_SEAT, strategy_id="beta")
        assert beta.reason != "kill_switch"
    finally:
        store.close()


def test_a_strategy_kill_never_refuses_a_sell(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _open(tmp_path / "ledger.sqlite")
    ids = IdFactory(clock, random.Random(7))
    try:
        set_strategy_kill(store, "alpha", "halt alpha", "human:alice", ts_utc=format_ts_utc(START))
        engine = _engine(store, clock)
        exit_sell = engine.check(
            _sell(ids), seat=SELL_SEAT, exit_reason="exit_rule", strategy_id="alpha"
        )
        assert exit_sell.reason != "kill_switch"
        human_sell = engine.check(_sell(ids), seat=SELL_SEAT, strategy_id="alpha")
        assert human_sell.reason != "kill_switch"
    finally:
        store.close()


def test_a_strategy_kill_survives_a_restart(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    path = tmp_path / "ledger.sqlite"
    ids = IdFactory(clock, random.Random(7))
    store = _open(path)
    set_strategy_kill(store, "alpha", "halt alpha", "human:alice", ts_utc=format_ts_utc(START))
    store.close()
    reopened = LedgerStore(str(path))
    try:
        decision = _engine(reopened, clock).check(_buy(ids), seat=BUY_SEAT, strategy_id="alpha")
        assert decision.reason == "kill_switch"
    finally:
        reopened.close()


def test_a_strategy_kill_clears_only_through_a_human_killswitch_clear(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _open(tmp_path / "ledger.sqlite")
    ids = IdFactory(clock, random.Random(7))
    try:
        set_strategy_kill(store, "alpha", "halt alpha", "human:alice", ts_utc=format_ts_utc(START))
        with pytest.raises(StrategyKillRefused):
            clear_strategy_kill(
                store,
                _clear_approval(clock, ids, kind="halt_clear"),
                "alpha",
                "wrong kind",
                ts_utc=format_ts_utc(START),
            )
        assert _engine(store, clock).check(
            _buy(ids), seat=BUY_SEAT, strategy_id="alpha"
        ).reason == ("kill_switch")
        cleared = clear_strategy_kill(
            store, _clear_approval(clock, ids), "alpha", "all clear", ts_utc=format_ts_utc(START)
        )
        assert cleared["type"] == "StrategyKillCleared"
        assert len(store.read(types=["StrategyKillCleared"], limit=None)) == 1
        assert _engine(store, clock).check(
            _buy(ids), seat=BUY_SEAT, strategy_id="alpha"
        ).reason != ("kill_switch")
        with pytest.raises(StrategyKillRefused):
            clear_strategy_kill(
                store, _clear_approval(clock, ids), "alpha", "again", ts_utc=format_ts_utc(START)
            )
    finally:
        store.close()


def test_cli_strategy_kill_is_human_only_and_records_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            ["killswitch", "set", "--strategy", "alpha", "--reason", "halt", "--by", "bot-02-risk"]
        )
        != 0
    )
    assert (
        main(["killswitch", "set", "--strategy", "alpha", "--reason", "halt", "--by", "human:op"])
        == 0
    )
    store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
    try:
        assert len(store.read(types=["StrategyKillSet"], limit=None)) == 1
    finally:
        store.close()
    assert (
        main(["killswitch", "clear", "--strategy", "alpha", "--by", "bot-02-risk", "--reason", "x"])
        != 0
    )
    assert (
        main(["killswitch", "clear", "--strategy", "alpha", "--by", "human:op", "--reason", "x"])
        == 0
    )
    store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
    try:
        cleared = store.read(types=["StrategyKillCleared"], limit=None)
        assert [row["payload"]["strategy_id"] for row in cleared] == ["alpha"]
    finally:
        store.close()


@pytest.mark.parametrize("verb", ["set", "clear"])
def test_killswitch_strategy_verbs_have_help(verb: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["killswitch", verb, "--help"])
    assert exc.value.code == 0
