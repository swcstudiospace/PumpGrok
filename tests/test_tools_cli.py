#!/usr/bin/env python3
"""CLI contracts for the PumpGrok operator CLI. pytest; no network."""

from __future__ import annotations

import io
import json
import logging
import os
import re
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout, suppress
from datetime import UTC, datetime
from pathlib import Path

import pytest

import pumpgrok.cli as cli_mod
from pumpgrok.cli import _unflattened_lines, main
from pumpgrok.core.approvals import parse_human_phrase, record_human_approval
from pumpgrok.core.ids import IdFactory
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.tickets import allocate_ticket
from pumpgrok.replay.clock import WallClock, format_ts_utc
from pumpgrok.replay.rng import make_rng

ROOT = Path(__file__).resolve().parent.parent


_TRADE_TICKET = "SOL-20260101-001"
_TRADE_MINT = "So11111111111111111111111111111111111111112"
_TRADE_APPROVAL = "apr-01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _trade_flags(seat: str, side: str = "buy", approval: str | None = _TRADE_APPROVAL) -> list[str]:
    flags = [
        "paper",
        side,
        "--ticket",
        _TRADE_TICKET,
        "--mint",
        _TRADE_MINT,
        "--size-sol",
        "0.5",
        "--slippage-bps",
        "100",
    ]
    if approval is not None:
        flags += ["--approval-id", approval]
    return [*flags, "--seat", seat]


def _ledger_kinds(tmp_path: Path) -> list[str]:
    """Event types in the paper ledger under ``tmp_path``; empty when no ledger exists."""
    path = tmp_path / "var" / "ledger.sqlite"
    if not path.is_file():
        return []
    store = LedgerStore(str(path))
    try:
        return [str(event["type"]) for event in store.read(limit=10000)]
    finally:
        store.close()


@pytest.fixture(autouse=True)
def _03_07_clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip PUMPGROK_* and secret-shaped names so CLI tests set what they need."""
    for name in list(os.environ):
        if name.startswith("PUMPGROK_") or any(
            frag in name.lower()
            for frag in ("secret", "password", "token", "api_key", "auth", "credential")
        ):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _03_07_root_handlers() -> Iterator[None]:
    """main() installs a handler bound to the test's stderr; remove it afterwards."""
    root = logging.getLogger()
    level = root.level
    yield None
    for handler in list(root.handlers):
        root.removeHandler(handler)
        with suppress(Exception):  # best effort cleanup
            handler.close()
    root.setLevel(level)


class TestPaperRegistryPath:
    """Task 1 tracer: paper buy/sell resolve through the registry (TOOL-011, R63)."""

    @pytest.mark.parametrize("side", ["buy", "sell"])
    def test_paper_operator_seat_refused_by_registry_as_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        side: str,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        code = main(_trade_flags("desk", side=side))
        assert code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert payload["code"] == "permission_denied"
        assert "Traceback" not in captured.err

    @pytest.mark.parametrize("side", ["buy", "sell"])
    def test_paper_writer_seat_refused_unavailable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        side: str,
    ) -> None:
        # bot-04-sniper holds exec.simulate and exec.place, so the seat guard passes and
        # the trade is refused as unavailable (exit 1). The approval gate is no longer
        # reachable from the CLI; no ledger event is written.
        monkeypatch.chdir(tmp_path)
        code = main(_trade_flags("bot-04-sniper", side=side))
        assert code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert payload["code"] == "unavailable"
        assert "verified curve price source" in payload["message"]
        assert _ledger_kinds(tmp_path) == []

    def test_paper_rejections_write_no_order_placed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        for seat in ("desk", "bot-04-sniper", "sniper", "exit"):
            assert main(_trade_flags(seat)) == 1
        store_path = tmp_path / "var" / "ledger.sqlite"
        if store_path.is_file():
            store = LedgerStore(str(store_path))
            try:
                rows = [
                    event for event in store.read(limit=10000) if event["type"] == "OrderPlaced"
                ]
            finally:
                store.close()
            assert rows == []


class _ScriptedCurves:
    """Pop one scripted snapshot per read; hold the last."""

    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


class TestPaperFillPath:
    """Task 3: sniper buy/sell refused as unavailable; the CLI cannot fill (exit 1)."""

    def _fill_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, side: str, size_sol: str
    ) -> list[str]:
        mint = _TRADE_MINT
        snap = CurveSnapshot(mint=mint, s_lamports=42_000_000_000, t_units=766_428_571_428_571)
        curves = _ScriptedCurves([snap, snap, snap, snap, snap])
        real_registry = cli_mod.build_operator_registry

        def _with_curves(**kwargs: object) -> object:
            params = dict(kwargs)
            params.setdefault("price_source", curves)
            params.setdefault("p_drop", 0.0)
            return real_registry(**params)  # type: ignore[arg-type]

        monkeypatch.setattr("pumpgrok.cli.wiring.build_operator_registry", _with_curves)
        seat = "bot-04-sniper" if side == "buy" else "bot-06-exit"
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            clock = WallClock()
            ts_utc = format_ts_utc(clock.now())
            ticket_id = allocate_ticket(
                store,
                ts_utc=ts_utc,
                source="paper",
                correlation_id="t",
                seat=seat,
                title="lead",
            )
            approval_id = f"apr-{IdFactory(clock, make_rng()).ulid()}"
            record = parse_human_phrase(
                f"approve {ticket_id} {mint} {size_sol} 100",
                kind="human_buy" if side == "buy" else "human_sell",  # type: ignore[arg-type]
                by="human:alice",
                approval_id=approval_id,
                at=datetime.fromtimestamp(clock.now(), UTC),
            )
            record_human_approval(store, record, ts_utc=ts_utc, source="paper", correlation_id="t")
        finally:
            store.close()
        return [
            "paper",
            side,
            "--ticket",
            ticket_id,
            "--mint",
            mint,
            "--size-sol",
            size_sol,
            "--slippage-bps",
            "100",
            "--approval-id",
            approval_id,
            "--seat",
            seat,
        ]

    def test_sniper_buy_then_sell_refused_unavailable_no_fill(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Same buy-then-sell flow as the former fill test: both legs are refused as
        # unavailable (exit 1) and no FillRecorded or OrderPlaced is written.
        monkeypatch.chdir(tmp_path)
        for side, size_sol in (("buy", "0.2"), ("sell", "0.1")):
            flags = self._fill_flags(tmp_path, monkeypatch, side=side, size_sol=size_sol)
            assert main(flags) == 1
            payload = json.loads(capsys.readouterr().out)
            assert payload["ok"] is False
            assert payload["code"] == "unavailable"
        kinds = _ledger_kinds(tmp_path)
        assert "FillRecorded" not in kinds
        assert "OrderPlaced" not in kinds


_SEED_TICKET = "SOL-20260101-001"
_SEED_MINT = "So11111111111111111111111111111111111111112"


def _seed_open_position(tmp_path: Path, *, with_mark: bool) -> None:
    """One open paper position in the canonical ledger, with or without a ledger mark.

    With no mark and no price source the flatten has nothing to value the sell with (G7).
    """
    path = tmp_path / "var" / "ledger.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    store = LedgerStore(str(path))
    try:
        store.set_meta("initial_equity_lamports", "10000000000")
        store.set_meta("source", "paper")
        now = format_ts_utc(WallClock().now())
        store.append(
            ts_utc=now,
            source="paper",
            correlation_id="seed",
            idempotency_key="seed-pos",
            type="PositionOpened",
            payload={
                "source": "paper",
                "mint": _SEED_MINT,
                "price_entry": "0.00001",
                "token_units": 3_000_000,
                "cost_basis_lamports": 200_000_000,
                "opened_ts_utc": now,
                "symbol": "TST",
                "creator": "Creator1111111111111111111111111111111111",
                "ticket_id": _SEED_TICKET,
                "score": "0.8",
            },
        )
        if with_mark:
            store.append(
                ts_utc=now,
                source="paper",
                correlation_id="seed",
                idempotency_key="seed-mark",
                type="MarkToMarket",
                payload={
                    "source": "paper",
                    "ts_source": now,
                    "cash_lamports": 9_800_000_000,
                    "equity_lamports": 10_000_000_000,
                    "unrealized_lamports": 0,
                    "prices_json": json.dumps(
                        {
                            _SEED_MINT: {
                                "mtm_lamports": 200_000_000,
                                "venue_fee_lamports": 0,
                                "spot": "0.00001",
                            }
                        }
                    ),
                },
            )
    finally:
        store.close()


class TestOperatorVerbs:
    """Task 2: killswitch/state verbs plus hidden tools help (TOOL-011, B5, B8, R22)."""

    def _run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
    ) -> tuple[int, str, str]:
        monkeypatch.chdir(tmp_path)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_killswitch_set_requires_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, _, err = self._run(tmp_path, monkeypatch, ["killswitch", "set"])
        assert code == 1
        assert "--reason" in err

    def test_killswitch_set_prints_json_and_persists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, err = self._run(
            tmp_path, monkeypatch, ["killswitch", "set", "--reason", "03-07 red"]
        )
        assert code == 0
        payload = json.loads(out)
        assert payload["active"] is True
        assert "Traceback" not in err
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            kinds = [event["type"] for event in store.read(limit=10000)]
        finally:
            store.close()
        assert "KillSwitchSet" in kinds

    def test_killswitch_flatten_requests_flatten(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(
            tmp_path, monkeypatch, ["killswitch", "flatten", "--reason", "03-07 red"]
        )
        assert code == 0
        payload = json.loads(out)
        assert payload["flatten_requested"] is True

    def test_killswitch_flatten_json_reports_incomplete_when_a_position_has_no_mark(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """G7 follow-up: the JSON must not say "completed" while a position is still open."""
        _seed_open_position(tmp_path, with_mark=False)
        _, out, _ = self._run(
            tmp_path, monkeypatch, ["killswitch", "flatten", "--reason", "g7 json"]
        )
        payload = json.loads(out)
        assert payload["flatten_status"] == "incomplete", payload
        assert [o["status"] for o in payload["flatten_outcomes"]] == ["not_flattened"]

    def test_killswitch_flatten_exits_6_when_a_position_has_no_mark(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """G7: a position the flatten cannot value stays open, so the exit code must say so."""
        _seed_open_position(tmp_path, with_mark=False)
        code, out, err = self._run(
            tmp_path, monkeypatch, ["killswitch", "flatten", "--reason", "g7 red"]
        )
        assert code == 6, (code, out, err)
        unflattened = [line for line in err.splitlines() if _SEED_MINT in line]
        assert len(unflattened) == 1, err
        assert "no_mark" in unflattened[0], unflattened[0]
        assert "UNFLATTENED" in unflattened[0], unflattened[0]
        # Fail closed: the latch is set even though the flatten did not finish.
        assert (tmp_path / "var" / "desk" / "KILLSWITCH").is_file()
        assert "KillSwitchSet" in _ledger_kinds(tmp_path)

    def test_killswitch_flatten_exits_0_and_closes_when_a_mark_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed_open_position(tmp_path, with_mark=True)
        code, out, err = self._run(
            tmp_path, monkeypatch, ["killswitch", "flatten", "--reason", "g7 green"]
        )
        assert code == 0, (code, out, err)
        payload = json.loads(out)
        assert [o["status"] for o in payload["flatten_outcomes"]] == ["closed"]
        assert "UNFLATTENED" not in err
        assert "PositionClosed" in _ledger_kinds(tmp_path)

    def test_killswitch_flatten_overlap_closed_elsewhere_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PR 11 finding 1: a position another caller closed first is not reported unflattened."""
        _seed_open_position(tmp_path, with_mark=True)
        path = tmp_path / "var" / "ledger.sqlite"

        async def overlapping_close(self, *, mint, ticket_id, reason):  # type: ignore[no-untyped-def]
            # The overlapping caller closed it first; this call finds nothing open.
            store = LedgerStore(str(path))
            try:
                store.append(
                    ts_utc=format_ts_utc(WallClock().now()),
                    source="paper",
                    correlation_id="other-caller",
                    idempotency_key="closed-by-overlap",
                    type="PositionClosed",
                    payload={
                        "source": "paper",
                        "mint": mint,
                        "price_exit": "0.00001",
                        "proceeds_lamports": 200_000_000,
                        "realized_pnl_lamports": 0,
                        "reason": reason,
                        "pnl_pct": "0",
                        "hold_seconds": 0,
                        "venue_tx_ref": "",
                    },
                )
            finally:
                store.close()
            return {"status": "no_position", "mint": mint}

        monkeypatch.setattr(PaperAdapter, "close_position", overlapping_close)
        code, out, err = self._run(
            tmp_path, monkeypatch, ["killswitch", "flatten", "--reason", "overlap"]
        )
        assert code == 0, (code, out, err)
        payload = json.loads(out)
        assert payload["flatten_status"] == "completed", payload
        assert [o["status"] for o in payload["flatten_outcomes"]] == ["closed"]
        assert "UNFLATTENED" not in err

    def test_killswitch_clear_appends_cleared_and_approval(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(
            tmp_path,
            monkeypatch,
            ["killswitch", "clear", "--by", "human:op", "--reason", "03-07 red"],
        )
        assert code == 0
        payload = json.loads(out)
        assert payload == {
            "ok": True,
            "killswitch": "cleared",
            "by": "human:op",
            "reason": "03-07 red",
        }
        assert (tmp_path / "var" / "ledger.sqlite").is_file()
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            events = store.read(limit=10000)
            kinds = [event["type"] for event in events]
            cleared = [event for event in events if event["type"] == "KillSwitchCleared"]
        finally:
            store.close()
        assert "KillSwitchCleared" in kinds
        assert cleared[0]["payload"]["cleared_by"] == "human:op"
        recorded = [event for event in events if event["type"] == "ApprovalRecorded"]
        assert {event["payload"]["kind"] for event in recorded} == {"killswitch_clear"}
        assert all(event["payload"]["consumed"] is True for event in recorded)

    def test_killswitch_clear_rejects_nonhuman_by(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(
            tmp_path,
            monkeypatch,
            ["killswitch", "clear", "--by", "op", "--reason", "03-07 red"],
        )
        assert code == 1
        assert out == ""
        assert not (tmp_path / "var" / "ledger.sqlite").is_file()

    def test_killswitch_clear_refused_while_file_source_live(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        desk = tmp_path / "var" / "desk"
        desk.mkdir(parents=True)
        (desk / "KILLSWITCH").write_text("03-07 red", encoding="utf-8")
        code, out, _ = self._run(
            tmp_path,
            monkeypatch,
            ["killswitch", "clear", "--by", "human:op", "--reason", "03-07 red"],
        )
        assert code == 1
        assert json.loads(out)["code"] == "killswitch_clear_refused"

    def test_killswitch_status_prints_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(tmp_path, monkeypatch, ["killswitch", "status"])
        assert code == 0
        assert "halted" in json.loads(out)

    def test_state_status_prints_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(tmp_path, monkeypatch, ["state", "status", "--seat", "desk"])
        assert code == 0
        assert "halted" in json.loads(out)

    def _latch_halt(self, tmp_path: Path) -> None:
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            store.append(
                ts_utc=format_ts_utc(WallClock().now()),
                source="paper",
                correlation_id="test",
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

    def test_state_halt_clear_refused_without_halt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(
            tmp_path,
            monkeypatch,
            ["state", "halt", "--clear", "--by", "human:op", "--reason", "r", "--seat", "desk"],
        )
        assert code == 1
        assert json.loads(out)["code"] == "halt_clear_refused"

    def test_state_halt_clear_appends_cleared_and_approval(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._latch_halt(tmp_path)
        code, out, _ = self._run(
            tmp_path,
            monkeypatch,
            ["state", "halt", "--clear", "--by", "human:op", "--reason", "r", "--seat", "desk"],
        )
        assert code == 0
        assert json.loads(out) == {"ok": True, "halt": "cleared", "by": "human:op", "reason": "r"}
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            events = store.read(limit=10000)
        finally:
            store.close()
        kinds = [event["type"] for event in events]
        assert "HaltCleared" in kinds
        recorded = [event for event in events if event["type"] == "ApprovalRecorded"]
        assert {event["payload"]["kind"] for event in recorded} == {"halt_clear"}

    def test_state_autonomy_appends_config_and_note(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(
            tmp_path,
            monkeypatch,
            ["state", "autonomy", "manual-ticket", "--by", "human:op", "--seat", "desk"],
        )
        assert code == 0
        payload = json.loads(out)
        assert payload == {
            "ok": True,
            "autonomy": "manual-ticket",
            "previous": "manual-ticket",
            "by": "human:op",
        }
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            kinds = [event["type"] for event in store.read(limit=10000)]
        finally:
            store.close()
        assert "ConfigChanged" in kinds

    def test_state_resume_records_resume_note(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(
            tmp_path, monkeypatch, ["state", "resume", "--seat", "sniper", "--by", "human:op"]
        )
        assert code == 0
        assert json.loads(out) == {"ok": True, "seat": "bot-04-sniper", "by": "human:op"}
        store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            notes = [
                event
                for event in store.read(limit=10000)
                if event["type"] == "JournalNote"
                and event["payload"].get("text", "").startswith("resume bot-04-sniper")
            ]
        finally:
            store.close()
        assert len(notes) == 1

    def test_ticket_next_allocates_sequenced_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(tmp_path, monkeypatch, ["ticket", "next"])
        assert code == 0
        first = json.loads(out)["ticket_id"]
        code, out, _ = self._run(tmp_path, monkeypatch, ["ticket", "next"])
        assert code == 0
        second = json.loads(out)["ticket_id"]
        assert first != second
        assert first[:-3] == second[:-3]
        assert int(second[-3:]) == int(first[-3:]) + 1
        assert (tmp_path / "var" / "ledger.sqlite").is_file()

    def test_ticket_create_and_list_round_trip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(tmp_path, monkeypatch, ["ticket", "create", "--mint", _TRADE_MINT])
        assert code == 0
        created = json.loads(out)["ticket_id"]
        code, out, _ = self._run(tmp_path, monkeypatch, ["ticket", "list"])
        assert code == 0
        assert created in json.loads(out)["tickets"]
        code, out, _ = self._run(tmp_path, monkeypatch, ["ticket", "create", "--ticket", created])
        assert code == 1
        assert json.loads(out)["code"] == "ticket_taken"

    def test_hidden_tools_schema_prints_json_schema(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(tmp_path, monkeypatch, ["tools", "exec.quote", "--help"])
        assert code == 0
        payload = json.loads(out)
        assert payload["name"] == "exec.quote"
        assert "properties" in payload["input_schema"]

    def test_hidden_tools_unknown_id_is_json_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(tmp_path, monkeypatch, ["tools", "nope.x", "--help"])
        assert code == 1
        assert json.loads(out)["code"] == "unknown_tool"

    def test_hidden_verb_absent_from_top_help(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as excinfo:
            main(["--help"])
        assert excinfo.value.code == 0

    @pytest.mark.parametrize(
        "argv",
        [
            ["scout", "discover"],
            ["scout", "pipeline", "--candidates"],
            ["risk", "audit"],
            ["chief", "pickup"],
            ["rug", "watch"],
            ["journal", "rollup", "--daily"],
            ["audit"],
            ["replay", "trim"],
            ["replay", "rebuild-ticks"],
        ],
    )
    def test_find_only_verbs_print_json_exit_5(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
    ) -> None:
        code, out, _ = self._run(tmp_path, monkeypatch, argv)
        assert code == 5
        assert json.loads(out)["status"] == "not-yet-implemented"


def _run_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> tuple[int, str, str]:
    """Run main() under an isolated cwd and capture both streams."""
    monkeypatch.chdir(tmp_path)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class TestCliRegressionSweep:
    """Task 3: TOOL-011 regression-proof; SC4 CLI half locked (STRUCT-005 pins)."""

    def test_top_help_exit_0_and_hides_tools_verb(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as excinfo:
            main(["--help"])
        assert excinfo.value.code == 0

    def test_hidden_verb_absent_from_top_help(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            main(["--help"])
        assert "  tools " not in capsys.readouterr().out

    def test_paper_help_lists_five_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as excinfo:
            main(["paper", "buy", "--help"])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        for flag in ("--ticket", "--mint", "--size-sol", "--slippage-bps", "--approval-id"):
            assert flag in out

    def test_no_direct_tool_imports_in_cli(self) -> None:
        text = "".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "src" / "pumpgrok" / "cli").glob("*.py"))
        )
        assert "build_operator_registry" in text
        assert not re.search(r"pumpgrok\.tools\.\w", text)

    @pytest.mark.parametrize(
        "argv,expected",
        [
            (_trade_flags("desk"), 1),
            (_trade_flags("bot-04-sniper", side="sell"), 1),
            (["state", "status", "--seat", "desk"], 0),
            (["state", "halt", "--seat", "desk"], 0),
            (
                ["state", "halt", "--clear", "--by", "human:op", "--reason", "r", "--seat", "desk"],
                1,
            ),
            (["state", "autonomy", "manual-ticket", "--by", "human:op", "--seat", "desk"], 0),
            (["state", "resume", "--seat", "sniper", "--by", "human:op"], 0),
            (["killswitch", "set", "--reason", "sweep"], 0),
            (["killswitch", "flatten", "--reason", "sweep"], 0),
            (["killswitch", "status"], 0),
            (["killswitch", "clear", "--by", "human:op", "--reason", "sweep"], 0),
            (["scout", "discover"], 5),
            (["scout", "pipeline", "--candidates"], 5),
            (["risk", "audit"], 5),
            (["chief", "pickup"], 5),
            (["rug", "watch"], 5),
            (["journal", "rollup", "--daily"], 5),
            (["ticket", "next"], 0),
            (["ticket", "create", "--mint", _TRADE_MINT], 0),
            (["ticket", "list"], 0),
            (["audit"], 5),
            (["replay", "trim"], 5),
            (["replay", "rebuild-ticks"], 5),
        ],
    )
    def test_every_wrapper_prints_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        argv: list[str],
        expected: int,
    ) -> None:
        code, out, err = _run_cli(tmp_path, monkeypatch, argv)
        assert code == expected
        payload = json.loads(out)
        if expected != 0:
            assert payload["ok"] is False
        assert "Traceback" not in err

    def test_verify_fixture_replays_and_prints_stable_hash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """verify is a real verb (04-02): replay, CONSISTENT, stable events.hash."""
        code, out, err = _run_cli(tmp_path, monkeypatch, ["verify", "--fixture", "smoke"])
        assert code == 0
        assert "events.hash=" in out
        assert "verify=CONSISTENT" in out
        assert "Traceback" not in err
        second, out2, _ = _run_cli(tmp_path, monkeypatch, ["verify", "--fixture", "smoke"])
        assert second == 0
        assert out2 == out

    def test_report_daily_prints_ascii_markdown_exit_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """report is a real verb (04-09 PAPER-006): ASCII markdown, never JSON."""
        code, out, err = _run_cli(tmp_path, monkeypatch, ["report", "--daily"])
        assert code == 0
        assert "# PumpGrok paper report - daily - " in out
        assert "## Summary" in out
        assert "## Trades" in out
        assert "## Live gate" in out
        out.encode("ascii")
        assert "Traceback" not in err
        assert not (tmp_path / "var").exists()

    def test_report_weekly_prints_ascii_markdown_exit_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """weekly adds the per-day table and the nine live-gate ids."""
        code, out, err = _run_cli(tmp_path, monkeypatch, ["report", "--weekly"])
        assert code == 0
        assert "# PumpGrok paper report - weekly - " in out
        assert "## Per day" in out
        assert "## Live gate" in out
        for gate_id in ("adapter_registered", "confirmation_record", "no_active_stop"):
            assert gate_id in out
        out.encode("ascii")
        assert "Traceback" not in err

    def test_live_confirm_bare_is_usage_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """confirm without --by/--notional-cap/--expires exits 1, never 5."""
        code, _, err = _run_cli(tmp_path, monkeypatch, ["live", "confirm"])
        assert code == 1
        assert "usage error" in err
        assert "Traceback" not in err


def test_minted_approval_ids_are_unique_in_a_burst() -> None:
    """WR-03: rapid CLI mints never collide, even within one millisecond."""
    minted = {cli_mod._mint_approval_id() for _ in range(500)}
    assert len(minted) == 500
    assert all(approval_id.startswith("apr-") for approval_id in minted)


def test_unflattened_lines_name_open_positions_and_unfinished_runs() -> None:
    """G7: every outcome that is not closed, and a run that did not finish, gets a line."""
    closed = {"mint": "M1", "ticket_id": "T1", "status": "closed", "detail": ""}
    open_ = {"mint": "M2", "ticket_id": "T2", "status": "not_flattened", "detail": "status=no_mark"}
    assert _unflattened_lines({"flatten_status": "completed", "flatten_outcomes": [closed]}) == []
    lines = _unflattened_lines({"flatten_status": "completed", "flatten_outcomes": [closed, open_]})
    assert len(lines) == 1 and "mint=M2" in lines[0] and "detail=status=no_mark" in lines[0]
    blocked = _unflattened_lines(
        {"flatten_status": "blocked", "flatten_detail": "barrier", "flatten_outcomes": []}
    )
    assert len(blocked) == 1 and "flatten_status=blocked" in blocked[0]
    unavailable = _unflattened_lines({"flatten_status": "unavailable", "flatten_outcomes": []})
    assert len(unavailable) == 1 and "flatten_status=unavailable" in unavailable[0]
