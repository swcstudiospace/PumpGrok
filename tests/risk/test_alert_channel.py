"""RISK-004 / R22: the alert channel is a live kill source polled every risk cycle.

Telegram is replaced by a fake ``httpx`` transport that honours ``offset`` the way the Bot API
does (updates below the offset are confirmed and never returned again). No test touches the
network, and the bot token used here is a placeholder that must never appear in a log.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.alert_channel import EmptyAlertChannel, build_alert_channel
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import KillSwitch, killswitch_file
from pumpgrok.tools.risk.kill_switch import flatten_hook_for

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 764_000_000_000_000
SIZE = 200_000_000
TOKEN = (
    "123456789:PLACEHOLDER_NOT_A_REAL_TOKEN_0000AB"  # pragma: allowlist secret: test placeholder
)
LOG = "pumpgrok.risk.alert_channel"


class FakeTelegram:
    """Scripted getUpdates: returns updates at or above ``offset``; records every offset asked."""

    def __init__(
        self,
        updates: Sequence[dict[str, Any]] = (),
        *,
        fail: Exception | None = None,
        status: int | None = None,
    ) -> None:
        self.updates = list(updates)
        self.fail = fail
        self.status = status
        self.offsets: list[int] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.telegram.org"
        offset = int(request.url.params.get("offset", "0"))
        self.offsets.append(offset)
        if self.fail is not None:
            raise self.fail
        if self.status is not None:
            return httpx.Response(self.status, json={"ok": False})
        result = [u for u in self.updates if int(u["update_id"]) >= offset]
        return httpx.Response(200, json={"ok": True, "result": result})


def _update(update_id: int, chat_id: int, text: str) -> dict[str, Any]:
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


def _channel(fake: FakeTelegram, state_dir: Path, allowlist: Sequence[str] = ("111",)) -> Any:
    client = httpx.Client(transport=httpx.MockTransport(fake.handler), timeout=2.0)
    return build_alert_channel(
        token=TOKEN, allowlist=list(allowlist), state_dir=state_dir, client=client
    )


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, **kwargs: Any) -> RiskEngine:
    kwargs.setdefault("get_reserves", lambda _mint: (S0, T0))
    kwargs.setdefault("env", {})
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",
        **kwargs,
    )


def _buy(clock: FixtureClock, ids: IdFactory) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT_A,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


class _ScriptedCurves:
    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _adapter(store: LedgerStore, clock: FixtureClock, engine: RiskEngine, ids: IdFactory) -> Any:
    snap = CurveSnapshot(mint=MINT_A, s_lamports=S0, t_units=T0)
    return PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(7),
        budget=RiskBudget(),
        price_source=_ScriptedCurves([snap, snap]),
        p_drop=0.0,
    )


def _position(store: LedgerStore, clock: FixtureClock, units: int) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key="pos-open-a",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": MINT_A,
            "price_entry": "0.00001",
            "token_units": units,
            "cost_basis_lamports": units,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )


def _human_clear(clock: FixtureClock, ids: IdFactory) -> ApprovalRecord:
    return ApprovalRecord(
        id=f"apr-{ids.ulid()}",
        kind="killswitch_clear",
        approved_by="human:alice",
        raw_message="all clear",
        at=datetime.fromtimestamp(clock.now(), UTC),
    )


def test_allowlisted_kill_line_halts_engine_within_one_check(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    desk = tmp_path / "desk"
    latch = killswitch_file(desk)
    fake = FakeTelegram([_update(7, 111, "KILL operator stop")])
    try:
        engine = _engine(store, clock, killswitch_path=latch, alert_channel=_channel(fake, desk))
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is False
        assert decision.reason == "kill_switch"
        sets = store.read(types=["KillSwitchSet"], limit=None)
        assert len(sets) == 1
        assert sets[0]["payload"]["origin"] == "alert_command"
        assert sets[0]["payload"]["reason"] == "operator stop"
        assert latch.read_text(encoding="utf-8") == "operator stop"
        engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert fake.offsets == [0, 8]
    finally:
        store.close()


def test_non_allowlisted_chat_is_ignored_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOG)
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    desk = tmp_path / "desk"
    fake = FakeTelegram([_update(7, 999, "KILL nope")])
    try:
        engine = _engine(
            store, clock, killswitch_path=killswitch_file(desk), alert_channel=_channel(fake, desk)
        )
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is True
        assert store.read(types=["KillSwitchSet"], limit=None) == []
        assert not killswitch_file(desk).exists()
        assert "non-allowlisted" in caplog.text
    finally:
        store.close()


@pytest.mark.parametrize("failure", ["transport", "http_500"])
def test_get_updates_failure_does_not_stop_check_or_log_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, failure: str
) -> None:
    caplog.set_level(logging.DEBUG)
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    desk = tmp_path / "desk"
    if failure == "transport":
        # The exception text carries the token on purpose: it must never reach a log.
        fake = FakeTelegram(fail=httpx.ConnectError(f"refused: /bot{TOKEN}/getUpdates"))
    else:
        fake = FakeTelegram(status=500)
    try:
        engine = _engine(
            store, clock, killswitch_path=killswitch_file(desk), alert_channel=_channel(fake, desk)
        )
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is True
        assert "getUpdates failed" in caplog.text
        assert TOKEN not in caplog.text
        assert TOKEN not in repr([record.getMessage() for record in caplog.records])
    finally:
        store.close()


def test_unconfigured_channel_polls_nothing_and_changes_nothing(tmp_path: Path) -> None:
    assert isinstance(
        build_alert_channel(token="", allowlist=["111"], state_dir=tmp_path), EmptyAlertChannel
    )
    assert isinstance(
        build_alert_channel(token=TOKEN, allowlist=["https://hooks.example/x"], state_dir=tmp_path),
        EmptyAlertChannel,
    )
    assert EmptyAlertChannel().poll() == []
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    latch = killswitch_file(tmp_path)
    try:
        engine = _engine(store, clock, killswitch_path=latch)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is True
        assert store.read(types=["KillSwitchSet"], limit=None) == []
        assert not latch.exists()
    finally:
        store.close()


def test_file_source_still_halts_engine_when_telegram_is_down(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    desk = tmp_path / "desk"
    latch = killswitch_file(desk)
    latch.parent.mkdir(parents=True)
    latch.write_text("operator stop", encoding="utf-8")
    fake = FakeTelegram(fail=httpx.ConnectError("no route to api.telegram.org"))
    try:
        engine = _engine(store, clock, killswitch_path=latch, alert_channel=_channel(fake, desk))
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is False
        assert decision.reason == "kill_switch"
        sets = store.read(types=["KillSwitchSet"], limit=None)
        assert len(sets) == 1
        assert sets[0]["payload"]["origin"] == "file"
    finally:
        store.close()


def test_restart_does_not_reengage_a_consumed_kill(tmp_path: Path) -> None:
    """(a): a restart resumes from the persisted offset; a consumed KILL is never re-read."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    desk = tmp_path / "desk"
    latch = killswitch_file(desk)
    fake = FakeTelegram([_update(7, 111, "KILL operator stop")])
    try:
        first = _engine(store, clock, killswitch_path=latch, alert_channel=_channel(fake, desk))
        assert first.check(_buy(clock, ids), seat="bot-04-sniper").reason == "kill_switch"
        # A human clears the switch: the latch file is removed and the ledger is cleared.
        latch.unlink()
        KillSwitch(clock, store=store, killswitch_path=latch, env={}).request_clear(
            _human_clear(clock, ids), "all clear", ts_utc=format_ts_utc(clock.now())
        )
        # The process restarts: a new channel instance on the same desk dir.
        restarted = _engine(store, clock, killswitch_path=latch, alert_channel=_channel(fake, desk))
        decision = restarted.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is True, decision.reason
        assert fake.offsets[-1] == 8
        assert len(store.read(types=["KillSwitchSet"], limit=None)) == 1
    finally:
        store.close()


def _flatten_engine(
    store: LedgerStore, clock: FixtureClock, ids: IdFactory, fake: FakeTelegram, desk: Path
) -> tuple[RiskEngine, Any]:
    engine = _engine(
        store, clock, killswitch_path=killswitch_file(desk), alert_channel=_channel(fake, desk)
    )
    adapter = _adapter(store, clock, engine, ids)
    engine.attach_flatten_hook(
        flatten_hook_for(store, adapter.inflight_barrier, adapter.close_position)
    )
    return engine, adapter


def test_plain_kill_then_flatten_escalates_and_closes(tmp_path: Path) -> None:
    """(b): a KILL FLATTEN while a plain KILL is engaged escalates and is honoured."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    desk = tmp_path / "desk"
    fake = FakeTelegram([_update(7, 111, "KILL operator stop")])
    try:
        _position(store, clock, 3_000_000)
        engine, _adapter_unused = _flatten_engine(store, clock, ids, fake, desk)
        asyncio.run(engine.poll_kill_sources())
        assert store.read(types=["PositionClosed"], limit=None) == []
        fake.updates.append(_update(8, 111, "KILL FLATTEN close all"))
        asyncio.run(engine.poll_kill_sources())
        closed = store.read(types=["PositionClosed"], limit=None)
        assert [row["payload"]["reason"] for row in closed] == ["kill_flatten"]
        sets = store.read(types=["KillSwitchSet"], limit=None)
        assert sets[-1]["payload"]["origin"] == "alert_command"
        assert sets[-1]["payload"]["flatten_requested"] is True
        assert killswitch_file(desk).read_text(encoding="utf-8") == "FLATTEN close all"
    finally:
        store.close()


def test_flatten_on_alert_channel_closes_position_without_orders(tmp_path: Path) -> None:
    """(c): with no order checks at all, one poll_kill_sources() closes the position."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    desk = tmp_path / "desk"
    fake = FakeTelegram([_update(7, 111, "KILL FLATTEN close all")])
    try:
        _position(store, clock, 3_000_000)
        engine, _adapter_unused = _flatten_engine(store, clock, ids, fake, desk)
        asyncio.run(engine.poll_kill_sources())
        closed = store.read(types=["PositionClosed"], limit=None)
        assert [row["payload"]["reason"] for row in closed] == ["kill_flatten"]
        # Repeated polls are safe: nothing is closed twice and no duplicate ledger rows appear.
        asyncio.run(engine.poll_kill_sources())
        asyncio.run(engine.poll_kill_sources())
        assert len(store.read(types=["PositionClosed"], limit=None)) == 1
        assert len(store.read(types=["KillSwitchSet"], limit=None)) == 1
    finally:
        store.close()


def test_flatten_consumed_under_env_survives_restart(tmp_path: Path) -> None:
    """Finding 10: a KILL FLATTEN consumed while PUMPGROK_KILLSWITCH is set survives a restart."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    desk = tmp_path / "desk"
    latch = killswitch_file(desk)
    env = {"PUMPGROK_KILLSWITCH": "1"}
    fake = FakeTelegram([_update(7, 111, "KILL FLATTEN close all")])
    try:
        _position(store, clock, 3_000_000)
        assert not latch.exists()
        first = _engine(
            store, clock, killswitch_path=latch, alert_channel=_channel(fake, desk), env=env
        )
        # The process dies after the offset is committed and before the flatten executes.
        with pytest.raises(RuntimeError):
            asyncio.run(first.poll_kill_sources())
        assert (desk / "alert_offset").read_text(encoding="utf-8") == "8"
        restarted = _engine(
            store,
            clock,
            killswitch_path=latch,
            alert_channel=_channel(FakeTelegram([]), desk),
            env=env,
        )
        adapter = _adapter(store, clock, restarted, ids)
        restarted.attach_flatten_hook(
            flatten_hook_for(store, adapter.inflight_barrier, adapter.close_position)
        )
        state = asyncio.run(restarted.poll_kill_sources())
        assert state.flatten_requested is True
        closed = store.read(types=["PositionClosed"], limit=None)
        assert [row["payload"]["reason"] for row in closed] == ["kill_flatten"]
    finally:
        store.close()


def test_env_engaged_switch_keeps_flatten_from_file_latch(tmp_path: Path) -> None:
    """Finding 10: env and file sources combine; a FLATTEN latch keeps flatten_requested."""
    latch = killswitch_file(tmp_path / "desk")
    latch.parent.mkdir(parents=True)
    latch.write_text("FLATTEN close all", encoding="utf-8")
    state = KillSwitch(
        FixtureClock(start=START), killswitch_path=latch, env={"PUMPGROK_KILLSWITCH": "1"}
    ).poll()
    assert state.active is True
    assert state.source == "env"
    assert state.flatten_requested is True


def test_failed_latch_write_does_not_commit_offset(tmp_path: Path) -> None:
    """Finding 10: the offset is committed only after the flatten request is persisted."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    desk = tmp_path / "desk"
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    fake = FakeTelegram([_update(7, 111, "KILL FLATTEN close all")])
    try:
        engine = _engine(
            store,
            clock,
            killswitch_path=blocker / "KILLSWITCH",
            alert_channel=_channel(fake, desk),
            env={"PUMPGROK_KILLSWITCH": "1"},
        )
        engine._killswitch.absorb_alerts()
        assert not (desk / "alert_offset").exists()
    finally:
        store.close()


def _blocked_desk(tmp_path: Path) -> Path:
    """A regular file where the desk directory should be, so every latch write fails."""
    desk = tmp_path / "desk"
    desk.write_text("not a directory", encoding="utf-8")
    return desk


def test_failed_latch_write_redelivers_kill_once_directory_writable(tmp_path: Path) -> None:
    """Index 1: a KILL whose latch write failed stays pending and engages on the next poll."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    desk = _blocked_desk(tmp_path)
    fake = FakeTelegram([_update(7, 111, "KILL operator stop")])
    try:
        engine = _engine(
            store,
            clock,
            killswitch_path=killswitch_file(desk),
            alert_channel=_channel(fake, desk),
        )
        asyncio.run(engine.poll_kill_sources())
        # The failed write must not advance the offset that the next poll asks Telegram for.
        assert fake.offsets == [0]
        desk.unlink()
        desk.mkdir()
        asyncio.run(engine.poll_kill_sources())
        assert killswitch_file(desk).read_text(encoding="utf-8") == "operator stop"
        sets = store.read(types=["KillSwitchSet"], limit=None)
        assert [row["payload"]["origin"] for row in sets] == ["alert_command"]
        assert fake.offsets[-1] == 0
    finally:
        store.close()


def test_order_refused_while_kill_latch_cannot_be_saved(tmp_path: Path) -> None:
    """Index 1: while a pending KILL cannot be saved, no order passes (fail closed)."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    desk = _blocked_desk(tmp_path)
    fake = FakeTelegram([_update(7, 111, "KILL operator stop")])
    try:
        engine = _engine(
            store,
            clock,
            killswitch_path=killswitch_file(desk),
            alert_channel=_channel(fake, desk),
        )
        first = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert first.passed is False
        assert first.reason == "kill_switch"
        second = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert second.passed is False
        assert second.reason == "kill_switch"
        # The engagement is in force, so the ledger records it once, even before the latch saves.
        pending_sets = store.read(types=["KillSwitchSet"], limit=None)
        assert [row["payload"]["origin"] for row in pending_sets] == ["alert_command"]
        assert desk.is_file()  # still the blocker: no latch was written
        desk.unlink()
        desk.mkdir()
        refused = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert refused.reason == "kill_switch"
        assert killswitch_file(desk).read_text(encoding="utf-8") == "operator stop"
        sets = store.read(types=["KillSwitchSet"], limit=None)
        assert [row["payload"]["origin"] for row in sets] == ["alert_command"]
    finally:
        store.close()
