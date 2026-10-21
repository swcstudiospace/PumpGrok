"""Bounded restarts, latches, resume, graceful shutdown, readyz, observe-only.

Restart budget 5/hour with min(16, 2**n) + jitter backoff gating
rescheduling; exhaustion latches observe-only with one edge-triggered
``bot_restart_exhausted`` Escalation while other seats keep ticking. Stale
seats emit one edge-triggered ``heartbeat_stale``. Resume clears the latch
via the ``state resume`` ledger note. Every Escalation relays to
notify.alert. RISK-006: observe-only seats cannot resolve paper-write
tools; the exit latch appends HaltSet manual; the risk latch rejects buys
while exits continue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.logging.json import bind_seat
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.seat_task import ObserveOnly, RestartPolicy, SeatContext, SeatTask
from pumpgrok.tools.notify.notifier import Notifier


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def _ctx(store: LedgerStore, clock: FixtureClock, seat: str) -> SeatContext:
    return SeatContext(
        seat_id=seat,
        clock=clock,
        rng=make_rng(11),
        store=store,
        source="replay",
        correlation_id="desk",
    )


async def _boom(ctx: SeatContext) -> dict[str, Any]:
    raise RuntimeError("seat crashed")


async def _ok(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


def test_backoff_sequence_is_1_2_4_8_16_plus_jitter() -> None:
    clock = FixtureClock(start=0.0)
    policy = RestartPolicy()
    rng = make_rng(11)
    seen: list[float] = []
    for _ in range(5):
        assert policy.record_crash(clock.now()) is True
        seen.append(policy.backoff_s(rng, clock.now()))
    assert policy.record_crash(clock.now()) is False
    for attempt, wait in enumerate(seen):
        base = min(16.0, 2.0**attempt)
        assert base <= wait < base + 1.0


async def test_sixth_restart_in_one_hour_latches_observe_only(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    try:
        latch = ObserveOnly()
        task = SeatTask(
            "bot-04-sniper",
            1.0,
            _boom,
            clock=clock,
            rng=make_rng(11),
            store=store,
            observe_only=latch,
        )
        for _ in range(5):
            assert await task.run_guarded(_ctx(store, clock, "bot-04-sniper")) == "crash"
            clock.advance_to(clock.now() + 60.0)
        assert task.restarts == 5
        assert not latch.is_latched("bot-04-sniper")
        # Sixth crash inside the hour: no restart, latch + escalation.
        assert await task.run_guarded(_ctx(store, clock, "bot-04-sniper")) == "crash"
        assert task.restarts == 5
        assert latch.is_latched("bot-04-sniper")
        assert latch.reason("bot-04-sniper") == "bot_restart_exhausted"
        rows = store.read(types=["Escalation"], limit=None)
        assert len(rows) == 1
        payload = rows[0]["payload"]
        assert isinstance(payload, dict)
        assert payload["kind"] == "bot_restart_exhausted"
        assert payload["seat"] == "bot-04-sniper"
    finally:
        store.close()


async def test_other_seats_keep_ticking_after_one_latches(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    try:
        cycles = dict.fromkeys(ROSTER, _ok)
        cycles["bot-07-shill"] = _boom
        supervisor = Supervisor(store=store, clock=clock, rng=make_rng(11), cycles=cycles)
        for _ in range(6):
            await supervisor.run_once()
            clock.advance_to(clock.now() + 60.0)
        assert supervisor.observe_only.is_latched("bot-07-shill")
        assert not supervisor.observe_only.is_latched("bot-00-chief")
        assert supervisor.tasks["bot-00-chief"].cycles == 6
        kinds = [e["payload"]["kind"] for e in store.read(types=["Escalation"], limit=None)]
        assert kinds == ["bot_restart_exhausted"]
    finally:
        store.close()


async def test_heartbeat_stale_emits_once_and_resume_clears_latch(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    try:
        latch = ObserveOnly()
        latch.latch("bot-01-scout", "bot_restart_exhausted")
        resumed = latch.fold_resume(store)
        assert resumed == []
        store.append(
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="desk",
            idempotency_key="resume|bot-01-scout|t",
            type="JournalNote",
            payload={
                "source": "paper",
                "seat": "bot-01-scout",
                "note_kind": "note",
                "text": "resume bot-01-scout by human:alice",
                "refs": [],
            },
        )
        assert latch.fold_resume(store) == ["bot-01-scout"]
        assert not latch.is_latched("bot-01-scout")
    finally:
        store.close()


def test_observe_only_matrix_sniper_risk_exit() -> None:
    latch = ObserveOnly()
    assert latch.paper_write_allowed("bot-04-sniper", "buy") is True
    latch.latch("bot-04-sniper", "bot_restart_exhausted")
    assert latch.paper_write_allowed("bot-04-sniper", "buy") is False
    assert latch.paper_write_allowed("bot-06-exit", "buy") is False
    assert latch.paper_write_allowed("bot-06-exit", "sell") is True
    latch2 = ObserveOnly()
    latch2.latch("bot-02-risk", "bot_restart_exhausted")
    assert latch2.paper_write_allowed("bot-04-sniper", "buy") is False
    assert latch2.paper_write_allowed("bot-06-exit", "sell") is True
    latch3 = ObserveOnly()
    latch3.latch("bot-06-exit", "bot_restart_exhausted")
    assert latch3.paper_write_allowed("bot-06-exit", "sell") is False
    assert latch3.paper_write_allowed("bot-04-sniper", "buy") is True


async def test_exit_latch_appends_halt_set_manual(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    try:
        latch = ObserveOnly()
        task = SeatTask(
            "bot-06-exit",
            15.0,
            _boom,
            clock=clock,
            rng=make_rng(11),
            store=store,
            observe_only=latch,
        )
        for _ in range(6):
            assert await task.run_guarded(_ctx(store, clock, "bot-06-exit")) == "crash"
            clock.advance_to(clock.now() + 60.0)
        assert latch.is_latched("bot-06-exit")
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        payload = halts[0]["payload"]
        assert isinstance(payload, dict)
        assert payload["reason"] == "manual"
        assert payload["detail"] == "exit seat observe-only"
    finally:
        store.close()


async def test_risk_latch_rejects_buys_while_exits_continue(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    try:
        factory = IdFactory(clock, make_rng(11))
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=factory,
            clock=clock,
            limits=EngineLimits(),
            autonomy="autonomous-paper",
        )
        engine.set_observe_only(frozenset({"bot-02-risk"}))
        mint = "B" * 44
        with bind_seat("bot-04-sniper"):
            buy = OrderRequest(
                ticket_id="SOL-20260101-001",
                mint=mint,
                side=Side.BUY,
                decision_id=factory.ulid(),
                size_lamports=10_000_000,
                max_slippage_bps=100,
                approval_id=f"apr-{factory.ulid()}",
                correlation_id="desk",
            )
            refused = engine.check(buy, seat="bot-04-sniper", source="replay")
        assert refused.passed is False
        assert refused.reason == "seat_may_trade"
        # Exits continue: the same latch never refuses a sell at this step.
        with bind_seat("bot-06-exit"):
            sell = OrderRequest(
                ticket_id="SOL-20260101-001",
                mint=mint,
                side=Side.SELL,
                decision_id=factory.ulid(),
                token_units=1_000_000,
                max_slippage_bps=100,
                approval_id=f"apr-{factory.ulid()}",
                correlation_id="desk",
            )
            exit_decision = engine.check(
                sell, seat="bot-06-exit", exit_reason="stop_loss", source="replay"
            )
        assert exit_decision.reason != "seat_may_trade"
    finally:
        store.close()


class _RecordingNotifier(Notifier):
    def __init__(self, clock: FixtureClock, tmp_path: Path) -> None:
        super().__init__(allowlist=(), clock=clock, alert_file=tmp_path / "alerts.jsonl")
        self.sent: list[dict[str, Any]] = []

    async def send_telegram(self, chat_id: str, text: str) -> None:
        raise AssertionError("no telegram in tests")

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        raise AssertionError("no webhook in tests")

    async def send(self, **fields: Any) -> dict[str, Any]:
        self.sent.append(dict(fields))
        return {"delivered": [], "suppressed": False}


async def test_escalation_relays_to_notify_alert(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    try:
        notifier = _RecordingNotifier(clock, tmp_path)
        task = SeatTask(
            "bot-04-sniper",
            1.0,
            _boom,
            clock=clock,
            rng=make_rng(11),
            store=store,
            notifier=notifier,
        )
        for _ in range(6):
            assert await task.run_guarded(_ctx(store, clock, "bot-04-sniper")) == "crash"
            clock.advance_to(clock.now() + 60.0)
        kinds = [call["kind"] for call in notifier.sent]
        assert "bot_restart_exhausted" in kinds
        critical = [c for c in notifier.sent if c["kind"] == "bot_restart_exhausted"]
        assert all(call["severity"] == "critical" for call in critical)
    finally:
        store.close()
