"""INV-R-19: ledger restart reconciles; tamper yields INCONSISTENT plus halt.

Owning test for SAFETY_INVARIANTS.md section 3.3 row INV-R-19. A restart
replays snapshot-plus-tail and equals a full replay field-for-field; the
hash chain covers canonical JSON. Tampering one payload row at rest
(UPDATE is refused by design, so the raw path drops the trigger) yields
INCONSISTENT and every order refused with reason=ledger_inconsistent. No
halt row is fabricated on the latched handle (the failed verify is the
persistent signal, dropped by design); nothing is auto-repaired: the
tampered bytes stay tampered.

Harness: FixtureClock plus seeded IdFactory; no wall clock, no network.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.reconcile import CONSISTENT, INCONSISTENT, reconcile
from pumpgrok.ledger.reducer import dump_state, initial_state, load_state, reduce
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore, recreate_ledger_db
from pumpgrok.logging.json import bind_seat
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

BASE = 1767225600.0  # 2026-01-01T00:00:00Z
EQUITY = 10_000_000_000
DAY = "2026-01-01"
MINT = "C" * 44
CID = "01JAAAAAAAAAAAAAAAAAAAAAAAAA"


def _note(
    store: LedgerStore, clock: FixtureClock, key: str, kind: str, text: str
) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id=CID,
        idempotency_key=key,
        type="JournalNote",
        payload={"source": "paper", "seat": "desk", "note_kind": kind, "text": text},
    )


def test_restart_reconcile_and_tamper_detect(tmp_path: Path) -> None:
    """INV-R-19: snapshot-plus-tail equals full replay; tamper halts the desk."""
    db_path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(db_path)
    clock = FixtureClock(start=BASE)
    ids = IdFactory(clock, make_rng(11))
    store = LedgerStore(str(db_path))
    store.set_meta("source", "paper")
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id=CID,
        idempotency_key=f"rollover-{DAY}",
        type="DailyRollover",
        payload={
            "source": "paper",
            "day_utc": DAY,
            "day_start_equity_lamports": EQUITY,
            "prior_day_json": "{}",
            "open_positions": [],
        },
    )
    clock.advance_to(BASE + 60.0)
    _note(store, clock, "note-signal", "signal", "signal for mint C")
    _note(store, clock, "note-safety", "safety_report", "safety ok for mint C")
    clock.advance_to(BASE + 120.0)
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id=CID,
        idempotency_key=f"fill-{ids.ulid()}",
        type="FillRecorded",
        payload={
            "source": "paper",
            "order_id": ids.ulid(),
            "decision_id": ids.ulid(),
            "side": "buy",
            "mint": MINT,
            "filled_lamports": 200_000_000,
            "filled_units": 1_000_000,
            "filled_fraction": "1",
            "price_avg": "200",
            "venue_fee_lamports": 0,
            "network_cost_lamports": 0,
            "cash_delta_lamports": -200_000_000,
            "latency_s": "0.1",
            "venue_tx_ref": "",
        },
    )
    snap_seq = store.count()
    folded = initial_state(source="paper", initial_equity_lamports=EQUITY, day_utc=DAY)
    for event in store.read(since_seq=1, limit=None):
        folded = reduce(folded, event)
    store.write_snapshot(
        seq=snap_seq, ts_utc=format_ts_utc(clock.now()), state=dump_state(folded)
    )
    clock.advance_to(BASE + 180.0)
    _note(store, clock, "note-review", "review", "post-fill review")
    head_seq = store.count()
    store.close()

    reopened = LedgerStore(str(db_path))
    try:
        assert reopened.verify() is True
        result = reconcile(reopened)
        assert result["status"] == CONSISTENT
        assert result["snapshot_seq"] == snap_seq
        assert result["tail_events"] == head_seq - snap_seq
        assert result["head_seq"] == head_seq
        # Snapshot-plus-tail equals a full fold over every event.
        genesis = initial_state(
            source="paper", initial_equity_lamports=EQUITY, day_utc=DAY
        )
        full = genesis
        for event in reopened.read(since_seq=1, limit=None):
            full = reduce(full, event)
        assert load_state(result["state"]) == load_state(dump_state(full))
    finally:
        reopened.close()

    # Tamper one payload row at rest: drop the append-only trigger on a raw
    # connection (UPDATE is refused by design), rewrite, reconnect.
    raw = sqlite3.connect(str(db_path))
    try:
        raw.execute("DROP TRIGGER IF EXISTS events_append_only_u;")
        row = raw.execute("SELECT payload_json FROM events WHERE seq = 2;").fetchone()
        assert row is not None
        tampered = row[0].replace("signal for mint C", "signal for mint X")
        assert tampered != row[0]
        raw.execute("UPDATE events SET payload_json = ? WHERE seq = 2;", (tampered,))
        raw.commit()
    finally:
        raw.close()

    tampered_store = LedgerStore(str(db_path))
    try:
        try:
            tampered_store.verify()
        except LedgerInconsistent:
            inconsistent = True
        else:
            inconsistent = False
        assert inconsistent is True
        result = reconcile(tampered_store)
        assert result["status"] == INCONSISTENT
        assert "chain" in str(result.get("detail", ""))
        # The desk halts and every order is refused; nothing self-heals.
        engine = RiskEngine(
            store=tampered_store,
            budget=RiskBudget(),
            ids=IdFactory(clock, make_rng(11)),
            clock=clock,
            autonomy="autonomous-paper",
            get_reserves=lambda _mint: (42_000_000_000, 764_000_000_000_000),
            env={},
        )
        factory = IdFactory(clock, make_rng(11))
        with bind_seat("bot-04-sniper"):
            buy = OrderRequest(
                ticket_id="SOL-20260101-001",
                mint=MINT,
                side=Side.BUY,
                decision_id=factory.ulid(),
                size_lamports=10_000_000,
                max_slippage_bps=100,
                approval_id=f"apr-{factory.ulid()}",
                correlation_id=CID,
            )
            refused = engine.check(buy, seat="bot-04-sniper", source="paper")
        assert refused.passed is False
        assert refused.reason == "ledger_inconsistent"
        with bind_seat("bot-06-exit"):
            sell = OrderRequest(
                ticket_id="SOL-20260101-001",
                mint=MINT,
                side=Side.SELL,
                decision_id=factory.ulid(),
                token_units=1_000_000,
                max_slippage_bps=100,
                approval_id=f"apr-{factory.ulid()}",
                correlation_id=CID,
            )
            refused_sell = engine.check(
                sell, seat="bot-06-exit", exit_reason="stop_loss", source="paper"
            )
        assert refused_sell.passed is False
        assert refused_sell.reason == "ledger_inconsistent"
        # No halt row is fabricated on the latched handle: the failed
        # verify itself is the persistent signal, so the append is dropped
        # by design (risk/engine.py _suppress_integrity). No row is added
        # at all: the tamper is preserved, never repaired or papered over.
        assert tampered_store.count() == head_seq
        assert tampered_store.read(types=["HaltSet"], limit=None) == []
        raw = sqlite3.connect(str(db_path))
        try:
            kept = raw.execute(
                "SELECT payload_json FROM events WHERE seq = 2;"
            ).fetchone()
            assert kept is not None and "mint X" in kept[0]
        finally:
            raw.close()
        assert reconcile(tampered_store)["status"] == INCONSISTENT
    finally:
        tampered_store.close()
