"""TOOL-011 served-verb coverage (R64): every served verb runs its backend.

Registry level: the five exec tools resolve through ``build_registry`` find
and run against the paper adapter (scripted curves, ``p_drop=0.0`` for
deterministic fills). CLI level: paper buy/sell (simulate then place),
state halt --clear/autonomy/resume, killswitch clear, ticket next/create/list,
and verify run end to end with exit 0 and JSON. The remaining exit-5 list is
pinned to the 04-09 handoff exactly.
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pumpgrok.cli as cli_mod
from pumpgrok.cli import main
from pumpgrok.config.settings import load_settings
from pumpgrok.core.approvals import parse_human_phrase, record_human_approval
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.execution.paper_adapter import CurveSnapshot
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.tickets import allocate_ticket
from pumpgrok.replay.clock import WallClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.tools import build_operator_registry

ROOT = Path(__file__).resolve().parents[2]
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SNIPER = "bot-04-sniper"

EXIT_5_HANDOFF = [
    ["scout", "discover"],
    ["scout", "pipeline", "--candidates"],
    ["risk", "audit"],
    ["chief", "pickup"],
    ["rug", "watch"],
    ["journal", "rollup", "--daily"],
    ["report", "--daily"],
    ["audit"],
    ["live", "confirm"],
    ["replay", "trim"],
    ["replay", "rebuild-ticks"],
]

EXEC_BACKENDS = {
    "exec.quote": "pumpgrok.execution.paper_adapter.PaperAdapter.quote",
    "exec.simulate": "pumpgrok.execution.paper_adapter.PaperAdapter.simulate",
    "exec.place": "pumpgrok.execution.paper_adapter.PaperAdapter.place",
    "exec.cancel": "pumpgrok.execution.paper_adapter.PaperAdapter.cancel",
    "exec.positions": "pumpgrok.execution.paper_adapter.PaperAdapter.positions",
}


@pytest.fixture(autouse=True)
def _04_07_clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip PUMPGROK_* and secret-shaped names so tests set what they need."""
    for name in list(os.environ):
        if name.startswith("PUMPGROK_") or any(
            frag in name.lower()
            for frag in ("secret", "password", "token", "api_key", "auth", "credential")
        ):
            monkeypatch.delenv(name, raising=False)


class ScriptedCurves:
    """Pop one scripted snapshot per read; hold the last."""

    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _snap() -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0)


def _registry(tmp_path: Path, curves: ScriptedCurves):
    """Build the operator registry over a tmp ledger with scripted curves."""
    settings = load_settings()
    reg, manifests, client = build_operator_registry(
        data_dir=tmp_path / "desk",
        repo_root=ROOT,
        settings=settings,
        ledger_path=tmp_path / "ledger.sqlite",
        price_source=curves,  # type: ignore[arg-type]
        p_drop=0.0,
    )
    assert manifests["bot-04-sniper"].id == SNIPER
    return reg, manifests, client


def _resolve(reg, manifests, name: str):
    """Resolve one tool; each call runs under its own correlation id."""
    manifest = manifests[SNIPER]
    with bind_correlation(CorrelationId.new(IdFactory(WallClock(), make_rng()))):
        tool = reg.find(name, max_side_effect=SideEffect.PAPER_WRITE, bot=manifest)

    async def _call(payload):  # type: ignore[no-untyped-def]
        with bind_correlation(CorrelationId.new(IdFactory(WallClock(), make_rng()))):
            return await tool(payload)

    _call.spec = tool.spec  # type: ignore[attr-defined]
    return _call


def _ticket_and_approval(
    store: LedgerStore, *, side: str, size_sol: str, slippage: int = 100
) -> tuple[str, str]:
    """Allocate a ticket and record a matching human approval for one side."""
    clock = WallClock()
    ts_utc = format_ts_utc(clock.now())
    ticket_id = allocate_ticket(
        store, ts_utc=ts_utc, source="paper", correlation_id="t", seat=SNIPER, title="lead"
    )
    approval_id = f"apr-{IdFactory(clock, make_rng()).ulid()}"
    record = parse_human_phrase(
        f"approve {ticket_id} {MINT} {size_sol} {slippage}",
        kind="human_buy" if side == "buy" else "human_sell",  # type: ignore[arg-type]
        by="human:alice",
        approval_id=approval_id,
        at=datetime.fromtimestamp(clock.now(), UTC),
    )
    record_human_approval(store, record, ts_utc=ts_utc, source="paper", correlation_id="t")
    return ticket_id, approval_id


_real_registry = build_operator_registry


def _patch_curves(monkeypatch: pytest.MonkeyPatch, curves: ScriptedCurves) -> None:
    """Inject scripted curves plus p_drop=0.0 into the CLI registry build."""

    def _with_curves(**kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("price_source", curves)
        kwargs.setdefault("p_drop", 0.0)
        return _real_registry(**kwargs)

    monkeypatch.setattr(cli_mod, "build_operator_registry", _with_curves)


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _mark(store: LedgerStore, mint: str) -> None:
    """Seed one fresh MarkToMarket row (production: the journal-seat cadence)."""
    now = format_ts_utc(WallClock().now())
    store.append(
        ts_utc=now,
        source="paper",
        correlation_id="t",
        idempotency_key=f"mtm|{mint}|{now}",
        type="MarkToMarket",
        payload={
            "source": "paper",
            "ts_source": now,
            "cash_lamports": 9_800_000_000,
            "equity_lamports": 10_000_000_000,
            "unrealized_lamports": 0,
            "prices_json": json.dumps({mint: {"mtm_lamports": 200_000_000, "spot": "0"}}),
        },
    )


class TestExecBackendCoverage:
    """The five exec tools resolve and run against the paper adapter."""

    async def test_served_specs_bind_paper_adapter(self, tmp_path: Path) -> None:
        reg, manifests, client = _registry(tmp_path, ScriptedCurves([_snap()]))
        try:
            for name, backend in EXEC_BACKENDS.items():
                tool = _resolve(reg, manifests, name)
                assert tool.spec.backend == backend
            place = _resolve(reg, manifests, "exec.place")
            assert place.spec.requires_approval is True
        finally:
            await client.aclose()

    async def test_simulate_writes_no_ledger_row(self, tmp_path: Path) -> None:
        reg, manifests, client = _registry(tmp_path, ScriptedCurves([_snap(), _snap()]))
        try:
            store = LedgerStore(str(tmp_path / "ledger.sqlite"))
            try:
                before = len(store.read(limit=None))
                tool = _resolve(reg, manifests, "exec.simulate")
                out = await tool(
                    tool.spec.input_model(
                        ticket_id="SOL-20260101-001",
                        mint=MINT,
                        side="buy",
                        size_lamports=200_000_000,
                        slippage_bps=100,
                    )
                )
                after = len(store.read(limit=None))
            finally:
                store.close()
            assert before == after
            assert out.model_dump(mode="json")["would_fill"] is True
        finally:
            await client.aclose()

    async def test_place_buy_fills_and_consumes_approval(self, tmp_path: Path) -> None:
        reg, manifests, client = _registry(tmp_path, ScriptedCurves([_snap(), _snap()]))
        try:
            store = LedgerStore(str(tmp_path / "ledger.sqlite"))
            try:
                ticket_id, approval_id = _ticket_and_approval(store, side="buy", size_sol="0.2")
                simulate = _resolve(reg, manifests, "exec.simulate")
                await simulate(
                    simulate.spec.input_model(
                        ticket_id=ticket_id,
                        mint=MINT,
                        side="buy",
                        size_lamports=200_000_000,
                        slippage_bps=100,
                    )
                )
                tool = _resolve(reg, manifests, "exec.place")
                out = await tool(
                    tool.spec.input_model(
                        ticket_id=ticket_id,
                        mint=MINT,
                        side="buy",
                        decision_id=IdFactory(WallClock(), make_rng()).ulid(),
                        size_lamports=200_000_000,
                        max_slippage_bps=100,
                        approval_id=approval_id,
                    )
                )
                body = out.model_dump(mode="json")
                assert body["status"] == "filled"
                placed = [e for e in store.read(limit=None) if e["type"] == "OrderPlaced"]
                assert len(placed) == 1
                recorded = [e for e in store.read(limit=None) if e["type"] == "ApprovalRecorded"]
                consumed = [e for e in recorded if e["payload"]["consumed"] is True]
                assert {e["payload"]["id"] for e in consumed} == {approval_id}
            finally:
                store.close()
        finally:
            await client.aclose()

    async def test_place_rejects_unknown_approval_without_write(self, tmp_path: Path) -> None:
        reg, manifests, client = _registry(tmp_path, ScriptedCurves([_snap(), _snap()]))
        try:
            tool = _resolve(reg, manifests, "exec.place")
            out = await tool(
                tool.spec.input_model(
                    ticket_id="SOL-20260101-001",
                    mint=MINT,
                    side="buy",
                    decision_id=IdFactory(WallClock(), make_rng()).ulid(),
                    size_lamports=200_000_000,
                    max_slippage_bps=100,
                    approval_id=f"apr-{IdFactory(WallClock(), make_rng()).ulid()}",
                )
            )
            assert out.model_dump(mode="json")["status"] == "rejected"
            store = LedgerStore(str(tmp_path / "ledger.sqlite"))
            try:
                assert [e for e in store.read(limit=None) if e["type"] == "OrderPlaced"] == []
            finally:
                store.close()
        finally:
            await client.aclose()

    async def test_cancel_unknown_and_positions_after_buy(self, tmp_path: Path) -> None:
        reg, manifests, client = _registry(tmp_path, ScriptedCurves([_snap(), _snap()]))
        try:
            store = LedgerStore(str(tmp_path / "ledger.sqlite"))
            try:
                ticket_id, approval_id = _ticket_and_approval(store, side="buy", size_sol="0.2")
                simulate = _resolve(reg, manifests, "exec.simulate")
                await simulate(
                    simulate.spec.input_model(
                        ticket_id=ticket_id,
                        mint=MINT,
                        side="buy",
                        size_lamports=200_000_000,
                        slippage_bps=100,
                    )
                )
                place = _resolve(reg, manifests, "exec.place")
                placed = await place(
                    place.spec.input_model(
                        ticket_id=ticket_id,
                        mint=MINT,
                        side="buy",
                        decision_id=IdFactory(WallClock(), make_rng()).ulid(),
                        size_lamports=200_000_000,
                        max_slippage_bps=100,
                        approval_id=approval_id,
                    )
                )
                assert placed.model_dump(mode="json")["status"] == "filled"
                cancel = _resolve(reg, manifests, "exec.cancel")
                cancelled = await cancel(
                    cancel.spec.input_model(
                        order_id=IdFactory(WallClock(), make_rng()).ulid(),
                        ticket_id=ticket_id,
                        approval_id=approval_id,
                    )
                )
                assert cancelled.model_dump(mode="json")["status_after"] == "not_found"
                positions = _resolve(reg, manifests, "exec.positions")
                view = await positions(positions.spec.input_model())
                body = view.model_dump(mode="json")
                assert body["equity_lamports"] > 0
                assert body["cash_lamports"] >= 0
            finally:
                store.close()
        finally:
            await client.aclose()


class TestServedVerbCoverage:
    """Every served CLI verb runs against its backend: exit 0 with JSON."""

    def _buy_flags(self, store: LedgerStore, *, side: str, size_sol: str) -> list[str]:
        ticket_id, approval_id = _ticket_and_approval(store, side=side, size_sol=size_sol)
        seat = SNIPER if side == "buy" else "bot-06-exit"
        return [
            "paper",
            side,
            "--ticket",
            ticket_id,
            "--mint",
            MINT,
            "--size-sol",
            size_sol,
            "--slippage-bps",
            "100",
            "--approval-id",
            approval_id,
            "--seat",
            seat,
        ]

    def test_paper_buy_fills_exit_0(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        _patch_curves(monkeypatch, ScriptedCurves([_snap(), _snap(), _snap()]))
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            flags = self._buy_flags(store, side="buy", size_sol="0.2")
        finally:
            store.close()
        code, out, err = _run(flags)
        assert code == 0
        assert json.loads(out)["status"] == "filled"
        assert "Traceback" not in err
        assert (tmp_path / "var" / "ledger.sqlite").is_file()

    def test_paper_sell_fills_after_buy_exit_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _patch_curves(monkeypatch, ScriptedCurves([_snap(), _snap(), _snap(), _snap(), _snap()]))
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            buy_flags = self._buy_flags(store, side="buy", size_sol="0.2")
        finally:
            store.close()
        assert _run(buy_flags)[0] == 0
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            _mark(store, MINT)
            sell_flags = self._buy_flags(store, side="sell", size_sol="0.1")
        finally:
            store.close()
        code, out, err = _run(sell_flags)
        assert code == 0
        assert json.loads(out)["status"] == "filled"
        assert "Traceback" not in err

    def test_state_halt_clear_cycle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        halt = [
            "state",
            "halt",
            "--clear",
            "--by",
            "human:op",
            "--reason",
            "r",
            "--seat",
            "desk",
        ]
        code, out, _ = _run(halt)
        assert code == 1
        assert json.loads(out)["code"] == "halt_clear_refused"
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            store.append(
                ts_utc=format_ts_utc(WallClock().now()),
                source="paper",
                correlation_id="t",
                idempotency_key="halt-test-1",
                type="HaltSet",
                payload={
                    "source": "paper",
                    "reason": "manual",
                    "detail": "test",
                    "equity_lamports": 10,
                    "day_start_equity_lamports": 10,
                    "set_by": "risk_engine",
                },
            )
        finally:
            store.close()
        code, out, err = _run(halt)
        assert code == 0
        assert json.loads(out)["halt"] == "cleared"
        assert "Traceback" not in err

    def test_state_autonomy_resume_ticket_killswitch_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        code, out, err = _run(
            ["state", "autonomy", "autonomous-paper", "--by", "human:op", "--seat", "desk"]
        )
        assert code == 0
        assert json.loads(out)["autonomy"] == "autonomous-paper"
        assert "Traceback" not in err

        code, out, err = _run(["state", "resume", "--seat", "sniper", "--by", "human:op"])
        assert code == 0
        assert json.loads(out)["seat"] == SNIPER
        assert "Traceback" not in err

        code, out, err = _run(["ticket", "next"])
        assert code == 0
        first = json.loads(out)["ticket_id"]
        code, out, err = _run(["ticket", "create", "--mint", MINT])
        assert code == 0
        second = json.loads(out)["ticket_id"]
        assert first != second
        code, out, err = _run(["ticket", "list"])
        assert code == 0
        tickets = json.loads(out)["tickets"]
        assert first in tickets and second in tickets
        assert "Traceback" not in err

        code, out, err = _run(["killswitch", "clear", "--by", "human:op", "--reason", "red"])
        assert code == 0
        assert json.loads(out)["killswitch"] == "cleared"
        assert "Traceback" not in err

        assert (tmp_path / "var" / "ledger.sqlite").is_file()

    def test_verify_replay_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        code, out, err = _run(["verify", "--fixture", "smoke"])
        assert code == 0
        assert "verify=CONSISTENT" in out
        assert "Traceback" not in err

    def test_remaining_exit_5_matches_handoff(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert len(EXIT_5_HANDOFF) == 11
        for argv in EXIT_5_HANDOFF:
            code, out, err = _run(argv)
            assert code == 5, argv
            assert json.loads(out)["status"] == "not-yet-implemented"
            assert "Traceback" not in err
