"""Promotion thresholds and the paper-record check (PRM-02, D17-3).

Thresholds load fail-closed from config/promotion_thresholds.toml. A missing file, a
malformed value, or a value looser than its LiveGate floor raises PromotionThresholdError,
so the promotion path never runs on thresholds weaker than the live gate.

A paper record passes only when every threshold holds. A record with no losing closes has
no finite profit factor, so it fails the profit-factor check: an unbounded ratio is not
evidence of an edge (D17-3). LiveGate itself is unchanged; its profit-factor rule belongs to
Phase 18.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.execution.live.live_gate import (
    MAX_DRAWDOWN_FRACTION,
    MIN_CLOSED_TRADES,
    MIN_PAPER_DAYS,
    MIN_PROFIT_FACTOR,
)

__all__ = [
    "PaperRecord",
    "PromotionThresholdError",
    "PromotionThresholds",
    "default_thresholds_path",
    "evaluate_paper_record",
    "load_thresholds",
]


class PromotionThresholdError(PumpgrokError):
    """The promotion thresholds file is missing, malformed, or looser than a LiveGate floor."""

    code = "promotion_thresholds_invalid"


@dataclass(frozen=True)
class PromotionThresholds:
    """The four paper-record thresholds a strategy must meet to reach LIVE_ELIGIBLE."""

    min_paper_days: int
    min_closed_trades: int
    min_profit_factor: float
    max_drawdown_fraction: float


@dataclass(frozen=True)
class PaperRecord:
    """One strategy's paper record, from its first paper fill.

    gains_lamports is the sum of winning realized P&L; losses_lamports is the sum of losing
    realized P&L as a positive magnitude. max_drawdown_fraction is the largest peak-to-trough
    fall of cumulative realized P&L over the capital the strategy deployed.
    """

    window_start: str
    paper_days: int
    closed_trades: int
    gains_lamports: int
    losses_lamports: int
    max_drawdown_fraction: float


def default_thresholds_path() -> Path:
    """In-package promotion_thresholds.toml path."""
    return Path(__file__).resolve().parents[1] / "config" / "promotion_thresholds.toml"


def _int_value(table: dict[str, Any], key: str) -> int:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PromotionThresholdError(f"promotion thresholds: paper.{key} must be an integer")
    return value


def _number_value(table: dict[str, Any], key: str) -> float:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PromotionThresholdError(f"promotion thresholds: paper.{key} must be a number")
    if not math.isfinite(value):
        raise PromotionThresholdError(f"promotion thresholds: paper.{key} must be finite")
    return float(value)


def _refuse_looser(thresholds: PromotionThresholds) -> None:
    """Refuse any threshold looser than the LiveGate floor it mirrors."""
    if thresholds.min_paper_days < MIN_PAPER_DAYS:
        raise PromotionThresholdError(
            f"promotion thresholds: min_days {thresholds.min_paper_days} is looser than "
            f"the live floor {MIN_PAPER_DAYS}"
        )
    if thresholds.min_closed_trades < MIN_CLOSED_TRADES:
        raise PromotionThresholdError(
            f"promotion thresholds: min_closed_trades {thresholds.min_closed_trades} is "
            f"looser than the live floor {MIN_CLOSED_TRADES}"
        )
    if thresholds.min_profit_factor < MIN_PROFIT_FACTOR:
        raise PromotionThresholdError(
            f"promotion thresholds: min_profit_factor {thresholds.min_profit_factor} is "
            f"looser than the live floor {MIN_PROFIT_FACTOR}"
        )
    if thresholds.max_drawdown_fraction > MAX_DRAWDOWN_FRACTION:
        raise PromotionThresholdError(
            f"promotion thresholds: max_drawdown_fraction {thresholds.max_drawdown_fraction} "
            f"is looser than the live floor {MAX_DRAWDOWN_FRACTION}"
        )


def load_thresholds(path: Path | str | None = None) -> PromotionThresholds:
    """Read and validate the thresholds file; fail closed on any defect."""
    target = default_thresholds_path() if path is None else Path(path)
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PromotionThresholdError(f"promotion thresholds unreadable at {target}") from exc
    paper = raw.get("paper")
    if not isinstance(paper, dict):
        raise PromotionThresholdError("promotion thresholds: missing [paper] table")
    thresholds = PromotionThresholds(
        min_paper_days=_int_value(paper, "min_days"),
        min_closed_trades=_int_value(paper, "min_closed_trades"),
        min_profit_factor=_number_value(paper, "min_profit_factor"),
        max_drawdown_fraction=_number_value(paper, "max_drawdown_fraction"),
    )
    _refuse_looser(thresholds)
    return thresholds


def evaluate_paper_record(record: PaperRecord, thresholds: PromotionThresholds) -> tuple[bool, str]:
    """Pass only when every threshold holds; return the verdict and a one-line reason."""
    failures: list[str] = []
    if record.paper_days < thresholds.min_paper_days:
        failures.append(f"{record.paper_days} of {thresholds.min_paper_days} paper days")
    if record.closed_trades < thresholds.min_closed_trades:
        failures.append(f"{record.closed_trades} of {thresholds.min_closed_trades} closed trades")
    if record.losses_lamports <= 0:
        failures.append("profit factor undefined: no losing closes")
    else:
        profit_factor = record.gains_lamports / record.losses_lamports
        if profit_factor < thresholds.min_profit_factor:
            failures.append(
                f"profit factor {profit_factor:.2f} below {thresholds.min_profit_factor}"
            )
    if record.max_drawdown_fraction > thresholds.max_drawdown_fraction:
        failures.append(
            f"drawdown {record.max_drawdown_fraction:.3f} above {thresholds.max_drawdown_fraction}"
        )
    if failures:
        return (False, "; ".join(failures))
    return (True, "paper record meets every threshold")
