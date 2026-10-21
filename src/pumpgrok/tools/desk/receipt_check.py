"""desk.receipt_check: run G-2, G-3, G-5, G-6 without writing to git (TOOL-007).

Each gate runs as a subprocess with a bounded timeout; the tool reports
``{gate, exit_code, output_tail}`` rows and never raises for a gate
failure — a failing gate is data, not a tool error. Only the caller's
materialized receipt copy is read; nothing under the repo is written.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import Field, model_validator
from typing import Self

from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import meta_now

__all__ = [
    "RECEIPT_CHECK_SPEC",
    "ReceiptCheckIn",
    "ReceiptCheckOut",
    "build_receipt_check_tool",
    "run_receipt_check",
]

_GATE_TIMEOUT_S = 20


class ReceiptCheckIn(ToolInput):
    """Receipt to check; ``receipt_path`` or an inline ``receipt`` object."""

    bot: str = Field(pattern=r"^bot-0[0-9]-[a-z-]+$")
    receipt: dict | None = None
    receipt_path: str | None = None
    strict: bool = False

    @model_validator(mode="after")
    def _receipt_required(self) -> Self:
        if self.receipt is None and self.receipt_path is None:
            raise ValueError("receipt_check needs receipt or receipt_path")
        return self


class ReceiptCheckOut(ToolOutput):
    """One row per gate with its exit code and output tail."""

    gates: list[dict] = Field(default_factory=list)


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


def _run_gate(name: str, argv: list[str], repo_root: Path) -> dict:
    try:
        completed = subprocess.run(
            argv,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=_GATE_TIMEOUT_S,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return {
            "gate": name,
            "exit_code": completed.returncode,
            "output_tail": output[-2000:],
        }
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or "") + (exc.stderr or "") if exc.stdout or exc.stderr else ""
        return {"gate": name, "exit_code": 124, "output_tail": partial[-2000:]}
    except OSError as exc:
        return {"gate": name, "exit_code": 127, "output_tail": f"gate launch failed: {exc}"}


async def run_receipt_check(
    inp: ReceiptCheckIn, gates_dir: Path, repo_root: Path
) -> dict:
    """Materialize the receipt outside the repo, then run the four gates."""
    if inp.receipt_path is not None and Path(inp.receipt_path).is_file():
        receipt_file = str(inp.receipt_path)
        cleanup = False
    else:
        materialized = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(inp.receipt or {"receipt_path": inp.receipt_path}, materialized)
        materialized.close()
        receipt_file = materialized.name
        cleanup = True
    try:
        gate_argv = [
            ("G-2", [sys.executable, str(gates_dir / "check_receipt.py"), "--receipt", receipt_file, "--bot", inp.bot] + (["--strict"] if inp.strict else [])),
            ("G-3", [sys.executable, str(gates_dir / "check_secrets.py"), "--files", receipt_file, "--root", str(repo_root)]),
            ("G-5/G-6", [sys.executable, str(gates_dir / "check_rollback.py"), "--receipt", receipt_file]),
        ]
        gates = [
            _run_gate(name, argv, repo_root) for name, argv in gate_argv
        ]
    finally:
        if cleanup:
            Path(receipt_file).unlink(missing_ok=True)
    ambient = ambient_correlation()
    return ReceiptCheckOut.model_validate(
        {
            "gates": gates,
            "meta": meta_now(
                "desk", inp.correlation_id or (str(ambient) if ambient else None)
            ),
        }
    ).model_dump()


def build_receipt_check_tool(gates_dir: Path, repo_root: Path) -> Tool:
    """Bind ``desk.receipt_check`` to one gates directory and repo root."""

    @tool(RECEIPT_CHECK_SPEC)
    async def _receipt_check(payload: ReceiptCheckIn) -> dict:
        return await run_receipt_check(payload, gates_dir, repo_root)

    return _receipt_check
