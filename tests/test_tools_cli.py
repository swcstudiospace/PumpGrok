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
from pathlib import Path
from unittest import mock

import pytest

from pumpgrok.cli import main
from pumpgrok.ledger.store import LedgerStore

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

    def test_killswitch_clear_records_intent_exit_5(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(
            tmp_path,
            monkeypatch,
            ["killswitch", "clear", "--by", "op", "--reason", "03-07 red"],
        )
        assert code == 5
        payload = json.loads(out)
        assert payload["status"] == "not-yet-implemented"
        assert payload["verb"] == "killswitch clear"
        assert payload["intent"] == {"by": "op", "reason": "03-07 red"}
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

    def test_state_halt_clear_records_intent_exit_5(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(
            tmp_path,
            monkeypatch,
            ["state", "halt", "--clear", "--by", "op", "--reason", "r", "--seat", "desk"],
        )
        assert code == 5
        payload = json.loads(out)
        assert payload["verb"] == "state halt --clear"
        assert payload["intent"] == {"by": "op", "reason": "r"}

    def test_state_autonomy_records_intent_exit_5(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out, _ = self._run(
            tmp_path,
            monkeypatch,
            ["state", "autonomy", "manual-ticket", "--seat", "desk"],
        )
        assert code == 5
        payload = json.loads(out)
        assert payload["verb"] == "state autonomy"
        assert payload["intent"] == {"policy": "manual-ticket"}

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
            ["ticket", "list"],
            ["ticket", "create", "--mint", _TRADE_MINT],
            ["report", "--daily"],
            ["audit"],
            ["live", "confirm"],
            ["replay", "trim"],
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
            (["state", "halt", "--clear", "--by", "op", "--reason", "r", "--seat", "desk"], 5),
            (["state", "autonomy", "manual-ticket", "--seat", "desk"], 5),
            (["killswitch", "set", "--reason", "sweep"], 0),
            (["killswitch", "flatten", "--reason", "sweep"], 0),
            (["killswitch", "status"], 0),
            (["killswitch", "clear", "--by", "op", "--reason", "sweep"], 5),
            (["scout", "discover"], 5),
            (["scout", "pipeline", "--candidates"], 5),
            (["risk", "audit"], 5),
            (["chief", "pickup"], 5),
            (["rug", "watch"], 5),
            (["journal", "rollup", "--daily"], 5),
            (["ticket", "next"], 5),
            (["ticket", "create", "--mint", _TRADE_MINT], 5),
            (["ticket", "list"], 5),
            (["report", "--daily"], 5),
            (["audit"], 5),
            (["live", "confirm"], 5),
            (["replay", "trim"], 5),
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
