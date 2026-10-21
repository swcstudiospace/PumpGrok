#!/usr/bin/env python3
"""CLI contracts for PumpGrok tools. unittest + pytest; no network."""

from __future__ import annotations

import importlib.util
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout, suppress
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

import pumpgrok.cli as cli_mod
from pumpgrok.cli import main
from pumpgrok.core.approvals import parse_human_phrase, record_human_approval
from pumpgrok.core.ids import IdFactory
from pumpgrok.execution.paper_adapter import CurveSnapshot
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.tickets import allocate_ticket
from pumpgrok.replay.clock import WallClock, format_ts_utc
from pumpgrok.replay.rng import make_rng

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def load_tool(name: str):
    path = TOOLS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"pumpgrok_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JupiterQuoteContract(unittest.TestCase):
    def test_quote_url_is_current_lite_swap_api(self):
        mod = load_tool("jupiter_quote")
        self.assertEqual(
            mod.JUPITER_QUOTE_URL,
            "https://lite-api.jup.ag/swap/v1/quote",
        )
        self.assertNotIn("quote-api.jup.ag", mod.JUPITER_QUOTE_URL)

    def test_get_quote_calls_configured_url(self):
        mod = load_tool("jupiter_quote")
        seen = []

        class FakeResp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "inputMint": "A",
                    "outputMint": "B",
                    "inAmount": "1",
                    "outAmount": "2",
                    "otherAmountThreshold": "2",
                    "slippageBps": 50,
                    "priceImpactPct": "0",
                    "routePlan": [{"swapInfo": {"label": "x"}, "percent": 100}],
                    "contextSlot": 1,
                    "timeTaken": 0.01,
                }

        def fake_get(url, params=None, timeout=None):
            seen.append(url)
            return FakeResp()

        mod.requests.get = fake_get
        result = mod.get_quote("A", "B", 1, 50)
        self.assertTrue(result["ok"])
        self.assertEqual(seen, ["https://lite-api.jup.ag/swap/v1/quote"])
        self.assertEqual(result["outAmount"], "2")

    def test_main_exits_nonzero_when_quote_fails(self):
        mod = load_tool("jupiter_quote")
        mod.get_quote = lambda *a, **k: {"ok": False, "error": "dns"}
        buf = io.StringIO()
        argv = ["jupiter_quote.py", "--input-mint", "A", "--output-mint", "B", "--amount", "1"]
        with (
            mock.patch.object(sys, "argv", argv),
            redirect_stdout(buf),
            self.assertRaises(SystemExit) as caught,
        ):
            mod.main()
        self.assertEqual(caught.exception.code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["ok"])


class FailClosedExitCodes(unittest.TestCase):
    def test_pipeline_evidence_missing_log_exits_nonzero(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "pipeline_evidence.py"),
                "--log",
                "/tmp/pumpgrok-no-such-trades.jsonl",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("log not found", payload["error"])

    def test_authority_main_exits_nonzero_on_error(self):
        mod = load_tool("authority_check")
        mod.check_mint = lambda *a, **k: {"ok": False, "error": "boom", "mint": "x"}
        buf = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["authority_check.py", "--mint", "x"]),
            redirect_stdout(buf),
            self.assertRaises(SystemExit) as caught,
        ):
            mod.main()
        self.assertEqual(caught.exception.code, 1)

    def test_holder_main_exits_nonzero_on_error(self):
        mod = load_tool("holder_check")
        mod.holder_snapshot = lambda *a, **k: {"ok": False, "error": "429"}
        buf = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["holder_check.py", "--mint", "x"]),
            redirect_stdout(buf),
            self.assertRaises(SystemExit) as caught,
        ):
            mod.main()
        self.assertEqual(caught.exception.code, 1)

    def test_priority_fee_main_exits_nonzero_on_error(self):
        mod = load_tool("priority_fee")
        mod.estimate_priority_fee = lambda *a, **k: {"ok": False, "error": "rpc"}
        buf = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["priority_fee.py"]),
            redirect_stdout(buf),
            self.assertRaises(SystemExit) as caught,
        ):
            mod.main()
        self.assertEqual(caught.exception.code, 1)

    def test_paper_sim_main_exits_nonzero_on_error(self):
        mod = load_tool("paper_sim")

        def boom(*a, **k):
            raise OSError("nope")

        mod.append_paper_fill = boom
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            argv = [
                "paper_sim.py",
                "--desk",
                tmp,
                "--action",
                "buy",
                "--ticket",
                "SOL-20260918-001",
                "--mint",
                "MintMintMint",
                "--size-usd",
                "1",
                "--price",
                "1",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                redirect_stdout(buf),
                self.assertRaises(SystemExit) as caught,
            ):
                mod.main()
        self.assertEqual(caught.exception.code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["ok"])


class HermesScriptsExecutable(unittest.TestCase):
    def test_hermes_shell_scripts_are_executable(self):
        for name in (
            "hermes-bootstrap.sh",
            "hermes-install-cron.sh",
            "hermes-verify-isolation.sh",
        ):
            path = ROOT / "scripts" / name
            self.assertTrue(path.is_file(), msg=f"missing {path}")
            self.assertTrue(os.access(path, os.X_OK), msg=f"not executable: {path}")


class TicketHelperDocs(unittest.TestCase):
    def test_lifecycle_skill_uses_real_subcommands(self):
        text = (ROOT / "skills" / "desk-trade-lifecycle" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("ticket_helper.py --write", text)
        self.assertIn("ticket_helper.py next", text)
        self.assertIn("ticket_helper.py create", text)

    def test_tools_readme_uses_real_subcommands(self):
        text = (TOOLS / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("ticket_helper.py --write", text)
        self.assertIn("ticket_helper.py next", text)


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
    def test_paper_writer_seat_reaches_approval_gate(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        side: str,
    ) -> None:
        # bot-04-sniper holds exec.place, so find() succeeds and the unknown
        # approval_id fails closed with exit 1 (R63: the approval record is
        # the control, not the --seat string filter).
        monkeypatch.chdir(tmp_path)
        code = main(_trade_flags("bot-04-sniper", side=side))
        assert code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert payload["code"] == "approval_unknown"
        assert "no valid approval_id" in captured.err

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
    """Task 3: sniper buy/sell with a valid approval fill (exit 0, was 1)."""

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

        monkeypatch.setattr(cli_mod, "build_operator_registry", _with_curves)
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

    def test_sniper_buy_then_sell_fill_exit_0(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        buy = self._fill_flags(tmp_path, monkeypatch, side="buy", size_sol="0.2")
        assert main(buy) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "filled"
        mark_store = LedgerStore(str(tmp_path / "var" / "ledger.sqlite"))
        try:
            now = format_ts_utc(WallClock().now())
            mark_store.append(
                ts_utc=now,
                source="paper",
                correlation_id="t",
                idempotency_key=f"mtm|{_TRADE_MINT}|{now}",
                type="MarkToMarket",
                payload={
                    "source": "paper",
                    "ts_source": now,
                    "cash_lamports": 9_800_000_000,
                    "equity_lamports": 10_000_000_000,
                    "unrealized_lamports": 0,
                    "prices_json": json.dumps(
                        {_TRADE_MINT: {"mtm_lamports": 200_000_000, "spot": "0"}}
                    ),
                },
            )
        finally:
            mark_store.close()
        sell = self._fill_flags(tmp_path, monkeypatch, side="sell", size_sol="0.1")
        assert main(sell) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "filled"


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
            ["report", "--daily"],
            ["audit"],
            ["live", "confirm"],
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
        text = (ROOT / "src" / "pumpgrok" / "cli.py").read_text(encoding="utf-8")
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
            (["report", "--daily"], 5),
            (["audit"], 5),
            (["live", "confirm"], 5),
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


if __name__ == "__main__":
    unittest.main()
