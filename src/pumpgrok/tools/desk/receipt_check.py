"""desk.receipt_check: run G-2, G-3, G-5, G-6 without writing to git (TOOL-007).

Each gate runs as a subprocess with a bounded timeout; the tool reports
``{gate, exit_code, output_tail}`` rows and never raises for a gate
failure — a failing gate is data, not a tool error. Only the caller's
materialized receipt copy is read; nothing under the repo is written.
Gates run as asyncio subprocesses and file I/O runs in a worker thread, so
the event loop is never blocked by a gate.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Self

from pydantic import Field, model_validator

from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.replay.clock import Clock
from pumpgrok.tools._common import meta_now

__all__ = [
    "RECEIPT_CHECK_SPEC",
    "ReceiptCheckIn",
    "ReceiptCheckOut",
    "build_receipt_check_tool",
    "run_receipt_check",
]

_GATE_TIMEOUT_S = 20
_OUTPUT_TAIL_CHARS = 2000
_TIMEOUT_EXIT_CODE = 124
_LAUNCH_FAILED_EXIT_CODE = 127


class ReceiptCheckIn(ToolInput):
    """Receipt to check; ``receipt_path`` or an inline ``receipt`` object."""

    bot: str = Field(pattern=r"^bot-0[0-9]-[a-z-]+$")
    receipt: dict[str, Any] | None = None
    receipt_path: str | None = None
    strict: bool = False

    @model_validator(mode="after")
    def _receipt_required(self) -> Self:
        if self.receipt is None and self.receipt_path is None:
            raise ValueError("receipt_check needs receipt or receipt_path")
        return self


class ReceiptCheckOut(ToolOutput):
    """One row per gate with its exit code and output tail."""

    gates: list[dict[str, str | int]] = Field(default_factory=list)


RECEIPT_CHECK_SPEC = ToolSpec(
    name="desk.receipt_check",
    description=(
        "Run G-2, G-3, G-5 and G-6 against a receipt without writing to git; "
        "reports exit codes and output tails."
    ),
    input_model=ReceiptCheckIn,
    output_model=ReceiptCheckOut,
    side_effect=SideEffect.READ,
    timeout_s=60.0,
    rate_limit_key="desk",
    backend="ci.gates",
)


def _materialize_receipt(inp: ReceiptCheckIn) -> tuple[str, bool]:
    """Return ``(receipt_file, cleanup)``: the caller's file, or a temp copy."""
    if inp.receipt_path is not None and Path(inp.receipt_path).is_file():
        return str(inp.receipt_path), False
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as materialized:
        json.dump(inp.receipt or {"receipt_path": inp.receipt_path}, materialized)
    return materialized.name, True


def _discard(receipt_file: str) -> None:
    Path(receipt_file).unlink(missing_ok=True)


def _gate_row(
    name: str, exit_code: int, stdout: bytes | None, stderr: bytes | None
) -> dict[str, str | int]:
    output = ((stdout or b"") + (stderr or b"")).decode("utf-8", errors="replace")
    return {
        "gate": name,
        "exit_code": exit_code,
        "output_tail": output[-_OUTPUT_TAIL_CHARS:],
    }


async def _run_gate(
    name: str, argv: list[str], repo_root: Path, clock: Clock
) -> dict[str, str | int]:
    """Run one gate under a bounded timeout; failures become rows, not raises."""
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return {
            "gate": name,
            "exit_code": _LAUNCH_FAILED_EXIT_CODE,
            "output_tail": f"gate launch failed: {exc}",
        }
    try:
        async with clock.timeout(_GATE_TIMEOUT_S):
            stdout, stderr = await process.communicate()
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        stdout, stderr = await process.communicate()
        return _gate_row(name, _TIMEOUT_EXIT_CODE, stdout, stderr)
    return _gate_row(name, await process.wait(), stdout, stderr)


async def run_receipt_check(
    inp: ReceiptCheckIn, gates_dir: Path, repo_root: Path, clock: Clock
) -> dict[str, Any]:
    """Materialize the receipt outside the repo, then run the four gates."""
    receipt_file, cleanup = await asyncio.to_thread(_materialize_receipt, inp)
    try:
        gate_argv = [
            (
                "G-2",
                [
                    sys.executable,
                    str(gates_dir / "check_receipt.py"),
                    "--receipt",
                    receipt_file,
                    "--bot",
                    inp.bot,
                ]
                + (["--strict"] if inp.strict else []),
            ),
            (
                "G-3",
                [
                    sys.executable,
                    str(gates_dir / "check_secrets.py"),
                    "--files",
                    receipt_file,
                    "--root",
                    str(repo_root),
                ],
            ),
            (
                "G-5/G-6",
                [sys.executable, str(gates_dir / "check_rollback.py"), "--receipt", receipt_file],
            ),
        ]
        gates = [await _run_gate(name, argv, repo_root, clock) for name, argv in gate_argv]
    finally:
        if cleanup:
            await asyncio.to_thread(_discard, receipt_file)
    ambient = ambient_correlation()
    return ReceiptCheckOut.model_validate(
        {
            "gates": gates,
            "meta": meta_now(
                "desk", inp.correlation_id or (str(ambient) if ambient else None), clock
            ),
        }
    ).model_dump()


def build_receipt_check_tool(gates_dir: Path, repo_root: Path, clock: Clock) -> Tool:
    """Bind ``desk.receipt_check`` to one gates directory, repo root and clock."""

    @tool(RECEIPT_CHECK_SPEC)
    async def _receipt_check(payload: ReceiptCheckIn) -> dict[str, Any]:
        return await run_receipt_check(payload, gates_dir, repo_root, clock)

    return _receipt_check
