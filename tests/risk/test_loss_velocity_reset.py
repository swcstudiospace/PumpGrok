"""S-B1: the loss-velocity breaker reads half-open from ``half_open`` and its reset persists."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.breakers import BreakerSet, LossVelocityBreaker

START = 1_790_000_000.0
EQUITY = 10_000_000_000
DROP = int(EQUITY * 0.97)


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def _mtm(store: LedgerStore, ts: float, equity: int, key: str) -> None:
    store.append(
        ts_utc=format_ts_utc(ts),
        source="paper",
        correlation_id="test",
        idempotency_key=key,
        type="MarkToMarket",
        payload={
            "source": "paper",
            "ts_source": "curve",
            "cash_lamports": equity,
            "equity_lamports": equity,
            "unrealized_lamports": 0,
            "prices_json": "{}",
        },
    )


def test_loss_velocity_reads_half_open_after_cooldown() -> None:
    now = [900.0]
    breaker = LossVelocityBreaker(lambda: now[0])
    breaker.note_equity(0.0, EQUITY)
    breaker.note_equity(900.0, DROP)
    assert breaker.evaluate(900.0) == "open"
    now[0] = 900.0 + breaker.cooldown_s
    assert breaker.state == "half-open"
    assert breaker.half_open is True


def test_loss_velocity_reset_persists_as_breaker_reset_row(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        breakers = BreakerSet(store, clock)
        _mtm(store, START, EQUITY, "mtm-0")
        clock.advance_to(START + 900.0)
        _mtm(store, START + 900.0, DROP, "mtm-1")
        breakers.refresh(
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
            equity_now=DROP,
        )
        assert breakers.open_breakers() == ["loss_velocity"]
        assert len(store.read(types=["BreakerTripped"], limit=None)) == 1

        clock.advance_to(START + 900.0 + breakers.loss_velocity.cooldown_s + 1.0)
        _mtm(store, START + 2500.0, DROP, "mtm-2")
        breakers.refresh(
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
            equity_now=DROP,
        )
        assert breakers.loss_velocity.state == "closed"
        resets = store.read(types=["BreakerReset"], limit=None)
        assert [row["payload"]["breaker"] for row in resets] == ["loss_velocity"]
    finally:
        store.close()
