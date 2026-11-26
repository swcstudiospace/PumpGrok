"""Offline contract for scripts/verify_doc_commands.sh and scripts/probe_pump_accounts.py.

Greptile R1 finding 17. The shell script is run from a throwaway repo
root holding a copy of itself, so the real CLAUDE.md and AGENTS.md are never
read. A fake ``uv`` on PATH stands in for the real binary; no network is used.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import stat
import struct
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from pumpgrok.replay.clock import FixtureClock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_doc_commands.sh"
PROBE = REPO_ROOT / "scripts" / "probe_pump_accounts.py"

ACCOUNT = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
ENDPOINT = "https://api.mainnet-beta.solana.com"
_CURVE_STRUCT = struct.Struct("<8sQQQQQB")

DOCUMENTED_OFFLINE = (
    "uv run pumpgrok doctor",
    "uv run pumpgrok --help",
    "uv run pumpgrok doctor --help",
    "uv run pumpgrok tools exec.quote --help",
    "uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke",
)

# Each line pairs a documented-looking command with a shell operator or network
# command. Every one must be rejected before bash sees it; {m} is a marker path
# that must never be created.
INJECTIONS = (
    "uv run pumpgrok doctor --help && touch {m}",
    "uv run pumpgrok doctor --help && wget https://example.invalid/x",
    "uv run pumpgrok doctor --help; touch {m}",
    "uv run pumpgrok doctor --help | touch {m}",
    "uv run pumpgrok --help $(touch {m})",
    "uv run pumpgrok --help `touch {m}`",
    "uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke && touch {m}",
    "uv run pumpgrok doctor && curl https://example.invalid/x",
)


def _make_root(tmp_path: Path, commands: list[str]) -> Path:
    root = tmp_path / "root"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "verify_doc_commands.sh")
    (root / "Makefile").write_text("lint:\n\ttrue\n", encoding="utf-8")
    body = "## Commands\n\n```bash\n" + "\n".join(commands) + "\n```\n"
    (root / "CLAUDE.md").write_text(body, encoding="utf-8")
    (root / "AGENTS.md").write_text("## Run the checks\n", encoding="utf-8")
    (root / "tests" / "fixtures" / "replay" / "smoke").mkdir(parents=True)
    return root


def _fake_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text('#!/usr/bin/env bash\necho "fake-uv $*"\n', encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _run_script(tmp_path: Path, commands: list[str]) -> subprocess.CompletedProcess[str]:
    root = _make_root(tmp_path, commands)
    env = dict(os.environ)
    env["PATH"] = f"{_fake_bin(tmp_path)}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["bash", str(root / "scripts" / "verify_doc_commands.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("line", INJECTIONS)
def test_shell_operator_line_is_rejected_and_never_executed(tmp_path: Path, line: str) -> None:
    """Finding 17: an operator after a --help or replay form must fail closed."""
    marker = tmp_path / "injected"
    command = line.format(m=marker)
    result = _run_script(tmp_path, [command])
    assert result.returncode == 1, result.stdout
    assert f"FAIL  {command}" in result.stdout, result.stdout
    assert not marker.exists()


@pytest.mark.parametrize("command", DOCUMENTED_OFFLINE)
def test_documented_offline_command_passes(tmp_path: Path, command: str) -> None:
    """The documented offline argument forms still run and pass."""
    result = _run_script(tmp_path, [command])
    assert result.returncode == 0, result.stdout
    assert f"PASS  {command} (exit 0)" in result.stdout, result.stdout


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("probe_pump_accounts", PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _account_value(owner: str, disc_hex: str) -> dict:
    """A getAccountInfo value whose bytes have the right length and plausible counters."""
    raw = _CURVE_STRUCT.pack(
        bytes.fromhex(disc_hex), 30_000_000_000, 1_000_000_000_000, 5_000_000_000, 7, 9, 0
    )
    data = base64.b64encode(raw).decode("ascii")
    return {"owner": owner, "lamports": 2_039_280, "executable": False, "data": [data, "base64"]}


@pytest.mark.parametrize(
    ("owner", "disc_hex", "expected_error"),
    [
        (
            "11111111111111111111111111111111",
            "17b7f83760d8ac60",
            "owner is not the expected program; layout stays ASSUMED",
        ),
        (
            "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
            "0000000000000000",
            "invalid bonding curve discriminator; layout stays ASSUMED",
        ),
    ],
)
def test_probe_keeps_assumed_for_unexpected_account(
    tmp_path: Path, owner: str, disc_hex: str, expected_error: str
) -> None:
    """Finding 18: a wrong owner or discriminator must never record VERIFIED."""
    probe = _load_probe()
    value = _account_value(owner, disc_hex)
    out = tmp_path / "probe.json"

    rc = probe.main(
        ["--account", ACCOUNT, "--endpoint", ENDPOINT, "--out", str(out)],
        fetch=lambda *_args: value,
        clock=FixtureClock(),
    )

    assert rc == 0
    text = out.read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["status"] == "ASSUMED"
    assert record["error"] == expected_error
    assert record["decoded"] is None
    assert "VERIFIED" not in text
