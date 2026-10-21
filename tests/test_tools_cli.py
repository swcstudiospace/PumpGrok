#!/usr/bin/env python3
"""CLI contracts for PumpGrok tools. Stdlib unittest; no network."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


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
        text = (ROOT / "skills" / "desk-trade-lifecycle" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("ticket_helper.py --write", text)
        self.assertIn("ticket_helper.py next", text)
        self.assertIn("ticket_helper.py create", text)

    def test_tools_readme_uses_real_subcommands(self):
        text = (TOOLS / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("ticket_helper.py --write", text)
        self.assertIn("ticket_helper.py next", text)


if __name__ == "__main__":
    unittest.main()
