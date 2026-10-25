"""RiskEngine walk orchestration: check, approvals, kill, probes and flatten."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.risk_budget import RiskBudget, budget_equity_lamports
from pumpgrok.engine.reputation import ReputationBook
from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.risk.alert_channel import AlertChannel
from pumpgrok.risk.breakers import BREAKER_NAMES, BreakerSet
from pumpgrok.risk.killswitch import SEAT_RE, FlattenOrder, KillState, KillSwitch
from pumpgrok.risk.limits import EngineLimits

from pumpgrok.risk.engine.constants import (
    EXIT_SELL_REASONS,
    EXIT_SKIP_STEPS,
    KILL_VERDICT_RE,
    RULE_EXIT_REASONS,
    STEP_IDS,
    _DECISION_CACHE_MAX,
    _RECHECK_STEPS,
)
from pumpgrok.risk.engine.model import (
    RiskDecision,
    _Fail,
    _StepCtx,
    order_hash_for,
    utc_day,
)
from pumpgrok.risk.engine.steps import _EngineSteps


class RiskEngine(_EngineSteps):
    """Evaluates the 19 R34 steps for one order (paper-engine.md 5.2).

    The kill-switch env is snapshotted at construction (read once at start,
    R22); the file and alert sources are polled on every check. Repeat checks
    with the same ``order_hash`` (and stage) return the identical decision
    while the ledger head and gate state are unchanged.
    """

    def __init__(
        self,
        *,
        store: LedgerStore,
        budget: RiskBudget,
        ids: IdFactory,
        clock: Clock,
        limits: EngineLimits | None = None,
        mode: Literal["paper", "live"] = "paper",
        autonomy: Literal["manual-ticket", "autonomous-paper"] = "manual-ticket",
        killswitch_path: Path | str | None = None,
        alert_channel: AlertChannel | None = None,
        env: Mapping[str, str] | None = None,
        get_reserves: Callable[[str], tuple[int, int] | None] | None = None,
        live_check: Callable[[], list[str]] | None = None,
        observe_only: frozenset[str] = frozenset(),
        scan_kill_verdicts: bool = True,
        reputation: ReputationBook | None = None,
    ) -> None:
        self._store = store
        self._budget = budget
        self._ids = ids
        self._clock = clock
        self._limits = limits if limits is not None else EngineLimits()
        self._mode = mode
        self._autonomy = autonomy
        self._reputation = reputation
        self._flatten_hook: Callable[[], Awaitable[None]] | None = None
        self._killswitch = KillSwitch(
            clock,
            store=store,
            killswitch_path=killswitch_path,
            env=env,
            alert_channel=alert_channel,
        )
        self._breakers = BreakerSet(store, clock)
        self._get_reserves = get_reserves
        self._live_check = live_check
        self._observe_only = observe_only
        self._scan_kill_verdicts = scan_kill_verdicts
        self._decisions: dict[str, RiskDecision] = {}
        # Breaker name -> order_hash of the order holding its admitted probe.
        self._probe_owners: dict[str, str] = {}

    @property
    def reputation(self) -> ReputationBook | None:
        """Attached reputation book, if the desk wired one (R62)."""
        return self._reputation

    def set_reputation(self, book: ReputationBook | None) -> None:
        """Attach (or detach) the book; a rebuilt book takes effect at once."""
        self._reputation = book

    def set_observe_only(self, seats: frozenset[str]) -> None:
        """Mirror the supervisor latch set (paper-engine.md 6.4, plan 04-08).

        Latched seats refuse paper writes at ``seat_may_trade``; a latched
        risk seat refuses buys desk-wide while exits continue.
        """
        self._observe_only = frozenset(seats)

    def _now_ts(self) -> str:
        return format_ts_utc(self._clock.now())

    def _fold(self) -> LedgerState:
        events = self._store.read(since_seq=1, limit=None)
        meta_equity = self._store.get_meta("initial_equity_lamports")
        initial = (
            int(meta_equity) if meta_equity is not None else budget_equity_lamports(self._budget)
        )
        meta_source = self._store.get_meta("source")
        if meta_source:
            source = meta_source
        elif events:
            source = str(events[0]["source"])
        else:
            source = "paper"
        state = initial_state(
            source=source,
            initial_equity_lamports=initial,
            day_utc=utc_day(self._clock.now()),
        )
        for event in events:
            state = reduce(state, event)
        return state

    def attach_flatten_hook(self, hook: Callable[[], Awaitable[None]]) -> None:
        """Bind the flatten executor that ``poll_kill_sources`` runs on a requested flatten.

        The composition root binds it once the adapter exists (``flatten_hook_for``), since the
        adapter is built from this engine.
        """
        self._flatten_hook = hook

    async def poll_kill_sources(self) -> KillState:
        """Absorb the env, file and alert kill sources once, then honour a requested flatten.

        RISK-004: call this once per supervised cycle, independent of any order check, so an
        alert ``KILL FLATTEN`` acts even when no order is being checked. Safe to call repeatedly:
        the channel consumes each update once, the ledger rows are idempotent, and a flatten
        closes only positions still open. A requested flatten with no hook attached is an error,
        never a silent no-op.
        """
        self._killswitch.absorb_alerts()
        state = self._killswitch.poll()
        self._killswitch.observe(ts_utc=self._now_ts(), source="paper", correlation_id="desk")
        if state.active and state.flatten_requested:
            if self._flatten_hook is None:
                raise RuntimeError("kill flatten requested but no flatten hook is attached")
            await self._flatten_hook()
        return state

    def _poll_kill(self, source: str, correlation_id: str) -> tuple[str, str, bool] | None:
        """Active kill switch, if any: (source, reason, flatten_requested)."""
        self._killswitch.observe(
            ts_utc=self._now_ts(), source=source, correlation_id=correlation_id
        )
        state = self._killswitch.poll()
        if not state.active:
            return None
        return (state.source, state.reason, state.flatten_requested)

    def _killed_mints(self) -> set[str]:
        """Mints under a session RISK KILL verdict (upgrade-plan RISK-005)."""
        if not self._scan_kill_verdicts:
            return set()
        killed: set[str] = set()
        for event in self._store.read(limit=None):
            if event["type"] != "JournalNote":
                continue
            payload = event["payload"]
            if not isinstance(payload, dict):
                continue
            if str(payload.get("note_kind", "")) != "verdict":
                continue
            match = KILL_VERDICT_RE.match(str(payload.get("text", "")))
            if match is not None:
                killed.add(match.group("mint"))
        return killed

    def _approvals(self) -> dict[str, ApprovalRecord]:
        """Latest unconsumed approvals by id, rebuilt from ``ApprovalRecorded`` rows."""
        latest: dict[str, dict[str, Any]] = {}
        for event in self._store.read(limit=None):
            if event["type"] != "ApprovalRecorded":
                continue
            payload = event["payload"]
            if not isinstance(payload, dict):
                continue
            approval_id = str(payload.get("id", ""))
            if approval_id:
                latest[approval_id] = payload
        records: dict[str, ApprovalRecord] = {}
        for approval_id, payload in latest.items():
            if bool(payload.get("consumed", False)):
                continue
            try:
                records[approval_id] = ApprovalRecord(
                    id=approval_id,
                    kind=payload.get("kind", ""),
                    ticket_id=payload.get("ticket_id") or None,
                    mint=payload.get("mint") or None,
                    size_lamports=payload.get("size_lamports") or None,
                    token_units=payload.get("token_units") or None,
                    max_slippage_bps=payload.get("max_slippage_bps") or None,
                    exit_rule_id=payload.get("exit_rule_id") or None,
                    approved_by=str(payload.get("approved_by", "")),
                    raw_message=str(payload.get("raw_message", "")),
                    at=datetime.fromisoformat(str(payload.get("at", ""))),
                    consumed=False,
                )
            except ValueError:
                continue
        return records

    def _mint_autonomous(self, order: OrderRequest, exit_reason: str | None) -> ApprovalRecord:
        now = datetime.fromtimestamp(self._clock.now(), UTC)
        if order.side.value == "buy":
            message = f"autonomous-paper buy {order.ticket_id} {order.mint}"
            return ApprovalRecord(
                id=f"apr-{self._ids.ulid()}",
                kind="autonomous_paper",
                ticket_id=order.ticket_id,
                mint=order.mint,
                size_lamports=order.size_lamports,
                max_slippage_bps=order.max_slippage_bps,
                approved_by="risk_engine",
                raw_message=message,
                at=now,
            )
        message = f"autonomous-paper sell {exit_reason or 'exit'} {order.mint}"
        return ApprovalRecord(
            id=f"apr-{self._ids.ulid()}",
            kind="autonomous_paper",
            ticket_id=order.ticket_id,
            mint=order.mint,
            size_lamports=order.size_lamports if order.token_units is None else None,
            token_units=order.token_units,
            max_slippage_bps=order.max_slippage_bps,
            exit_rule_id=exit_reason if exit_reason in RULE_EXIT_REASONS else None,
            approved_by="risk_engine",
            raw_message=message,
            at=now,
        )

    def check(
        self,
        order: OrderRequest,
        *,
        seat: str | None = None,
        exit_reason: str | None = None,
        creator: str | None = None,
        source: str = "paper",
        correlation_id: str = "desk",
        stage: Literal["ACCEPTED", "CONFIRMING"] = "ACCEPTED",
    ) -> RiskDecision:
        """Run the R34 steps for one order; first failure wins.

        ``exit_reason`` names an exit-rule, ``rug_alert``, ``kill_flatten``,
        ``blind_flatten`` or ``graduated`` sell; those sells skip steps 2-4
        and 9-19. ``creator`` is the candidate mint's creator for the
        ``creator_already_open`` step (the sniper knows it off-ledger; the
        ledger scan is the fallback). ``stage="CONFIRMING"`` re-runs the stop
        steps and the position-limit steps (``max_open_positions``,
        ``already_open``, ``creator_already_open``) so a buy that raced another
        fill is refused at the fill, and a sell refuses with ``no_position`` when
        its holding has closed.
        """
        # RISK-004: the alert channel is polled on every check, after env and file are read.
        self._killswitch.absorb_alerts()
        order_hash = order_hash_for(order)
        cache_key = self._cache_key(order, order_hash=order_hash, stage=stage)
        cached = self._decisions.get(cache_key)
        if cached is not None:
            return cached
        decision = self._evaluate(
            order,
            order_hash=order_hash,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            source=source,
            correlation_id=correlation_id,
            stage=stage,
        )
        self._decisions[cache_key] = decision
        while len(self._decisions) > _DECISION_CACHE_MAX:
            self._decisions.pop(next(iter(self._decisions)))
        return decision

    def _cache_key(
        self,
        order: OrderRequest,
        *,
        order_hash: str,
        stage: Literal["ACCEPTED", "CONFIRMING"],
    ) -> str:
        """Cache key with a gate generation: ledger head plus live gate state.

        Any halt/kill/breaker change (a ledger append, a kill env/file/alert
        flip, or a breaker cooldown transition) changes the key, so a cached
        PASS never replays past an engaged gate and a cached REJECT never
        survives a human clear.
        """
        kill = self._killswitch.poll()
        return (
            f"{stage}|{order_hash}|{order.approval_id or ''}"
            f"|{self._store.count()}"
            f"|{int(kill.active)}|{kill.source}|{kill.reason}"
            f"|{','.join(sorted(self._breakers.open_breakers()))}"
            f"|{','.join(sorted(self._breakers.half_open_breakers()))}"
        )

    def _skip(self, step: str, ctx: _StepCtx) -> bool:
        if ctx.stage == "CONFIRMING" and step not in _RECHECK_STEPS:
            return True
        return ctx.is_exit_sell and step in EXIT_SKIP_STEPS

    def _evaluate(
        self,
        order: OrderRequest,
        *,
        order_hash: str,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
        source: str,
        correlation_id: str,
        stage: Literal["ACCEPTED", "CONFIRMING"],
    ) -> RiskDecision:
        is_buy = order.side.value == "buy"
        state = self._fold()
        self._breakers.sync_from_ledger()
        ts_utc = self._now_ts()
        equity = self._equity_for_halts(state)
        self._breakers.refresh(
            ts_utc=ts_utc, source=source, correlation_id=correlation_id, equity_now=equity
        )
        for name in list(self._probe_owners):
            if not self._breakers.by_name(name).probe_inflight:
                del self._probe_owners[name]
        half_all = [name for name in BREAKER_NAMES if self._breakers.by_name(name).half_open]
        # Probes this order already holds are its own: its repeat checks reuse them.
        owned = [name for name in half_all if self._probe_owners.get(name) == order_hash]
        half_avail = self._breakers.half_open_breakers()
        ctx = _StepCtx(
            order=order,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            source=source,
            correlation_id=correlation_id,
            stage=stage,
            is_buy=is_buy,
            is_exit_sell=(
                not is_buy and exit_reason is not None and exit_reason in EXIT_SELL_REASONS
            ),
            wanted={"human_buy"} if is_buy else {"human_sell", "exit_rule"},
            state=state,
            kill=self._poll_kill(source, correlation_id),
            open_breakers=set(self._breakers.open_breakers()),
            half_blocked=is_buy and bool(half_all) and not half_avail and not owned,
            killed=self._killed_mints() if is_buy else set(),
            equity=equity,
            approvals=self._approvals(),
            final_size=order.size_lamports if is_buy else None,
        )
        ctx.approval_id = order.approval_id or None
        try:
            for step in STEP_IDS:
                if self._skip(step, ctx):
                    continue
                getattr(self, f"_step_{step}")(ctx)
            if stage == "CONFIRMING" and not is_buy:
                # A sell sized at ACCEPTED must still find its holding at the fill: a
                # flatten or another exit may have closed it while this order slept.
                held = state.positions.get(order.mint)
                if held is None or held.token_units <= 0:
                    raise _Fail("no_position", f"mint={order.mint} holding closed before fill")
            if ctx.is_buy and not ctx.is_exit_sell and half_all:
                if owned:
                    ctx.probe = True
                elif half_avail and self._breakers.admit_probe(half_avail[0]):
                    self._probe_owners[half_avail[0]] = order_hash
                    ctx.probe = True
                else:
                    raise _Fail("breaker_open", "probe inflight")
        except _Fail as fail:
            return self._reject(order_hash, ctx, fail.reason)
        return self._accept(order_hash, ctx)

    def _accept(self, order_hash: str, ctx: _StepCtx) -> RiskDecision:
        order = ctx.order
        return RiskDecision(
            passed=True,
            reason="pass",
            order_hash=order_hash,
            decision_id=order.decision_id,
            approval_id=ctx.approval_id,
            approval=ctx.approval,
            size_lamports=ctx.final_size if ctx.is_buy else None,
            token_units=None if ctx.is_buy else order.token_units,
            capped=ctx.capped,
            caps=dict(ctx.caps),
            probe=ctx.probe,
            evaluated=self._evaluated(ctx, None),
        )

    def _reject(self, order_hash: str, ctx: _StepCtx, reason: str) -> RiskDecision:
        order = ctx.order
        return RiskDecision(
            passed=False,
            reason=reason,
            order_hash=order_hash,
            decision_id=order.decision_id,
            approval_id=ctx.approval_id,
            approval=ctx.approval,
            size_lamports=ctx.final_size if ctx.is_buy else None,
            token_units=None if ctx.is_buy else order.token_units,
            capped=ctx.capped,
            caps=dict(ctx.caps),
            probe=ctx.probe,
            evaluated=self._evaluated(ctx, reason),
        )

    def _evaluated(self, ctx: _StepCtx, failed: str | None) -> list[dict[str, str]]:
        # reputation_degraded is a breaker-scope reason (R62), not a 20th step:
        # it fails the breaker_open row so the 19 R34 rows never change shape.
        fail_key = "breaker_open" if failed == "reputation_degraded" else failed
        rows: list[dict[str, str]] = []
        for step in STEP_IDS:
            status = "fail" if step == fail_key else ctx.evaluated.get(step, "skip")
            rows.append({"id": step, "status": status})
        return rows

    def note_tick(self, ts: float, *, ts_utc: str, source: str, correlation_id: str) -> None:
        """Record a fresh price for the DataStale breaker (feed hook for 04-08)."""
        self._breakers.note_tick(ts, ts_utc=ts_utc, source=source, correlation_id=correlation_id)

    def note_miss(self, ts: float, *, ts_utc: str, source: str, correlation_id: str) -> None:
        """Record a missed price read for the DataStale breaker (feed hook for 04-08)."""
        self._breakers.note_miss(ts, ts_utc=ts_utc, source=source, correlation_id=correlation_id)

    def resolve_probe(
        self, name: str, ok: bool, *, source: str = "paper", correlation_id: str = "desk"
    ) -> None:
        """Resolve an admitted half-open probe; the adapter calls this per outcome."""
        self._breakers.resolve_probe(
            name, ok, ts_utc=self._now_ts(), source=source, correlation_id=correlation_id
        )
        self._probe_owners.pop(name, None)

    def release_order_probes(
        self, order_hash: str, ok: bool, *, source: str, correlation_id: str
    ) -> None:
        """Resolve every inflight probe owned by ``order_hash``; others are untouched.

        Breakers whose probe is not inflight are skipped, so repeat or
        out-of-order calls never raise. Each resolved probe goes through
        :meth:`resolve_probe`, which also clears its owner entry.
        """
        for name, owner in list(self._probe_owners.items()):
            if owner != order_hash:
                continue
            if not self._breakers.by_name(name).probe_inflight:
                del self._probe_owners[name]
                continue
            self.resolve_probe(name, ok, source=source, correlation_id=correlation_id)

    def record_kill_verdict(
        self, mint: str, reason: str, *, source: str = "paper", correlation_id: str = "desk"
    ) -> None:
        """Record a RISK KILL verdict on a mint; later buys for all seats refuse (RISK-005)."""
        self._store.append(
            ts_utc=self._now_ts(),
            source=source,
            correlation_id=correlation_id,
            idempotency_key=f"kill-verdict|{mint}|{self._now_ts()[:10]}",
            type="JournalNote",
            payload={
                "source": source,
                "seat": "bot-02-risk",
                "note_kind": "verdict",
                "text": f"RISK verdict=KILL mint={mint} reason={reason}",
                "refs": [],
            },
        )

    def request_halt_clear(
        self,
        approval: ApprovalRecord,
        reason: str,
        *,
        source: str = "paper",
        correlation_id: str = "desk",
    ) -> None:
        """Append ``HaltCleared`` plus the ``halt_clear`` approval (CLI calls this in 04-07).

        Human-only and refused unless a halt is latched; UTC rollover never
        clears on its own (R5).
        """
        by = approval.approved_by
        if not by.startswith("human:") or SEAT_RE.match(by.removeprefix("human:")):
            raise ValueError(f"halt clear must come from a human, got {by!r}")
        if approval.kind != "halt_clear":
            raise ValueError(f"halt clear needs a halt_clear approval, got {approval.kind!r}")
        if not self._fold().halt.active:
            raise ValueError("no active halt to clear")
        if self._store.by_key(f"consumed|{approval.id}") is not None:
            raise ValueError(f"halt_clear approval {approval.id} is already consumed")
        ts_utc = self._now_ts()
        self._store.append_batch(
            [
                {
                    "ts_utc": ts_utc,
                    "source": source,
                    "correlation_id": correlation_id,
                    "idempotency_key": f"halt-clear|{approval.id}",
                    "type": "HaltCleared",
                    "payload": {
                        "source": source,
                        "reason": reason,
                        "cleared_by": by,
                        "approval_id": approval.id,
                        "note": reason,
                    },
                },
                {
                    "ts_utc": ts_utc,
                    "source": source,
                    "correlation_id": correlation_id,
                    "idempotency_key": f"consumed|{approval.id}",
                    "type": "ApprovalRecorded",
                    "payload": {
                        "source": source,
                        "id": approval.id,
                        "kind": approval.kind,
                        "approved_by": by,
                        "at": approval.at.isoformat(),
                        "ticket_id": approval.ticket_id or "",
                        "mint": approval.mint or "",
                        "size_lamports": approval.size_lamports or 0,
                        "token_units": approval.token_units or 0,
                        "max_slippage_bps": approval.max_slippage_bps or 0,
                        "exit_rule_id": approval.exit_rule_id or "",
                        "raw_message": reason,
                        "consumed": True,
                    },
                },
            ]
        )

    def plan_flatten(self, *, correlation_id: str = "desk") -> list[FlattenOrder]:
        """Build one ``kill_flatten`` sell per open position with a minted approval.

        The supervisor waits on the in-flight barrier, then places these via
        ``PaperAdapter.place``; the EXIT seat is not in the path (design 5.4).
        """
        now = datetime.fromtimestamp(self._clock.now(), UTC)
        orders: list[FlattenOrder] = []
        for mint, pos in self._fold().positions.items():
            if pos.token_units <= 0:
                continue
            approval = ApprovalRecord(
                id=f"apr-{self._ids.ulid()}",
                kind="autonomous_paper",
                ticket_id=pos.ticket_id,
                mint=mint,
                token_units=pos.token_units,
                max_slippage_bps=self._limits.max_slippage_bps,
                approved_by="risk_engine",
                raw_message=f"autonomous-paper kill_flatten {mint}",
                at=now,
            )
            orders.append(
                FlattenOrder(
                    order=OrderRequest(
                        ticket_id=pos.ticket_id,
                        mint=mint,
                        side=Side.SELL,
                        decision_id=self._ids.ulid(),
                        token_units=pos.token_units,
                        max_slippage_bps=self._limits.max_slippage_bps,
                        approval_id=approval.id,
                        correlation_id=correlation_id,
                    ),
                    approval=approval,
                )
            )
        return orders

    def _creator_of(self, mint: str, state: LedgerState) -> str:
        pos = state.positions.get(mint)
        if pos is not None and pos.creator:
            return str(pos.creator)
        for event in self._store.read(limit=None):
            if event["type"] != "PositionOpened":
                continue
            payload = event["payload"]
            if isinstance(payload, dict) and str(payload.get("mint", "")) == mint:
                return str(payload.get("creator", ""))
        return ""

    def _creator_open(self, creator: str, state: LedgerState) -> bool:
        return any(p.token_units > 0 and p.creator == creator for p in state.positions.values())
