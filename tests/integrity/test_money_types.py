"""Integer-money static guard plus export exactness (INT-01).

Money crosses the export/engine boundary as integer lamports or base units
only; Decimal appears solely for ratios. This module fails if any annotation
under ``src/pumpgrok`` puts a money-suffixed field on ``float`` (AST-based,
so comments and docstrings never count), and pins the export to render
prices and SOL amounts as exact decimal strings that round-trip back to
their integer inputs.

Deterministic; no network.
"""

from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.ledger.export import export_ledger
from pumpgrok.ledger.store import LedgerStore

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"

MONEY_KEYWORDS = frozenset(
    {"lamport", "equity", "fee", "pnl", "cost", "price", "size", "balance"}
)


def _is_money_name(name: str) -> bool:
    lowered = name.lower()
    return any(keyword in lowered for keyword in MONEY_KEYWORDS)


def _mentions_float(node: ast.AST) -> bool:
    """Whether an annotation node admits ``float`` (``float``, ``X | float``, ...)."""
    if isinstance(node, ast.Name):
        return node.id == "float"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _mentions_float(node.left) or _mentions_float(node.right)
    if isinstance(node, ast.Subscript):
        target = node.value
        if isinstance(target, ast.Name) and target.id in {"Optional", "Union"}:
            elts = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            return any(_mentions_float(elt) for elt in elts)
        return False
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value.strip() == "float"
    return False


def _scan_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = str(path.relative_to(SRC))
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name):
                name = target.id
            elif isinstance(target, ast.Attribute):
                name = target.attr
            else:
                continue
            if _is_money_name(name) and _mentions_float(node.annotation):
                found.append(f"{rel}:{node.lineno}: {name} annotated as float")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            ):
                if arg.arg in {"self", "cls"} or arg.annotation is None:
                    continue
                if _is_money_name(arg.arg) and _mentions_float(arg.annotation):
                    found.append(
                        f"{rel}:{arg.lineno}: {node.name}({arg.arg}) annotated as float"
                    )
    return found


def test_no_float_money_annotations() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        violations.extend(_scan_file(path))
    assert not violations, "float money fields under src/pumpgrok:\n" + "\n".join(
        violations
    )


MINT = "Mint1111CATS1111111111111111111111111111111"


def _envelope(entry_type: str, payload: dict[str, Any], key: str, ts: str) -> dict[str, Any]:
    return {
        "ts_utc": ts,
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "idempotency_key": key,
        "type": entry_type,
        "payload": payload,
    }


def _export(tmp_path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.set_meta("source", "paper")
    store.set_meta("initial_equity_lamports", "10000000000")
    store.append_batch(rows)
    trades_path = tmp_path / "trades.jsonl"
    result = export_ledger(store, journal_dir=tmp_path / "journal", trades_path=trades_path)
    assert result["trade_lines"] == len(rows)
    return [json.loads(line) for line in trades_path.read_text(encoding="utf-8").splitlines()]


def test_export_money_renders_as_exact_decimal_strings(tmp_path: Path) -> None:
    buy = _envelope(
        "FillRecorded",
        {
            "source": "paper",
            "order_id": "01J0000000000000000000002",
            "decision_id": "01J0000000000000000000003",
            "side": "buy",
            "mint": MINT,
            "filled_lamports": 200_000_000,
            "filled_units": 3579186000000,
            "filled_fraction": "1",
            "price_avg": "5.532e-5",
            "venue_fee_lamports": 2000000,
            "network_cost_lamports": 9000,
            "cash_delta_lamports": -200009000,
            "latency_s": "1.4",
            "venue_tx_ref": "dry_run:01J0000000000000000000004",
        },
        "fill-key-0001",
        "2026-01-01T00:00:01.000001Z",
    )
    gain = _envelope(
        "PositionClosed",
        {
            "source": "paper",
            "mint": MINT,
            "price_exit": "6.2e-5",
            "proceeds_lamports": 225000000,
            "realized_pnl_lamports": 25000000,
            "reason": "take_profit",
            "pnl_pct": "12.5",
            "hold_seconds": 300,
            "venue_tx_ref": "dry_run:01J0000000000000000000005",
        },
        "close-key-0001",
        "2026-01-01T00:00:03.000001Z",
    )
    loss = _envelope(
        "PositionClosed",
        {
            "source": "paper",
            "mint": MINT,
            "price_exit": "4.1e-5",
            "proceeds_lamports": 80000000,
            "realized_pnl_lamports": -120_000_000,
            "reason": "stop_loss",
            "pnl_pct": "-30.0",
            "hold_seconds": 120,
            "venue_tx_ref": "dry_run:01J0000000000000000000006",
        },
        "close-key-0002",
        "2026-01-01T00:00:04.000001Z",
    )
    buy_line, gain_line, loss_line = _export(tmp_path, [buy, gain, loss])

    assert isinstance(buy_line["size_sol"], str)
    assert isinstance(buy_line["entry_price"], str)
    assert buy_line["size_sol"] == "0.2"
    assert int(Decimal(buy_line["size_sol"]) * 10**9) == 200_000_000
    assert Decimal(buy_line["entry_price"]) * 1000 == Decimal("5.532e-5")

    assert isinstance(gain_line["exit_price"], str)
    assert isinstance(gain_line["pnl_sol"], str)
    assert Decimal(gain_line["exit_price"]) * 1000 == Decimal("6.2e-5")
    assert int(Decimal(gain_line["pnl_sol"]) * 10**9) == 25_000_000

    assert int(Decimal(loss_line["pnl_sol"]) * 10**9) == -120_000_000
    assert Decimal(loss_line["exit_price"]) * 1000 == Decimal("4.1e-5")

    # Ratios stay numeric; timestamps stay epoch floats.
    assert isinstance(gain_line["pnl_pct"], float)
    assert isinstance(buy_line["ts"], float)
