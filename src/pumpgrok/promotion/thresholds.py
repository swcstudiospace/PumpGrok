"""Fail-closed version-controlled promotion thresholds (PRM-02, T-17-08).

Every threshold lives in ``config/promotion_thresholds.toml`` with the
LiveGate floors as constants read from the execution live gate module,
never as retyped numbers. The loader refuses the whole file with a
ConfigError naming the key when any threshold is looser than its floor,
when a key is missing, or when the file does not parse. Ratios are
Decimal; counts are integers.

Promotion thresholds and the paper-record check (PRM-02, D17-3).

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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pumpgrok.config.settings import ConfigError
from pumpgrok.core.errors import PumpgrokError
from pumpgrok.execution.live.live_gate import (
    MAX_DRAWDOWN_FRACTION,
    MIN_CLOSED_TRADES,
    MIN_PAPER_DAYS,
    MIN_PROFIT_FACTOR,
)

__all__ = [
    "DEFAULT_THRESHOLDS_PATH",
    "PaperRecord",
    "PromotionThresholdError",
    "PromotionThresholds",
    "default_thresholds_path",
    "evaluate_paper_record",
    "load_thresholds",
]

#: Floors: the tightest values a promotion file may declare.
FLOOR_PAPER_DAYS = MIN_PAPER_DAYS
FLOOR_CLOSED_TRADES = MIN_CLOSED_TRADES
FLOOR_PROFIT_FACTOR = Decimal(str(MIN_PROFIT_FACTOR))
FLOOR_DRAWDOWN_FRACTION = Decimal(str(MAX_DRAWDOWN_FRACTION))

#: Version-controlled thresholds file consulted at promotion time.
DEFAULT_THRESHOLDS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "promotion_thresholds.toml"
)


class PromotionThresholdError(PumpgrokError):
    """The promotion thresholds file is missing, malformed, or looser than a LiveGate floor."""

    code = "promotion_thresholds_invalid"


@dataclass(frozen=True)
class PromotionThresholds:
    """Promotion thresholds, each at least as strict as its LiveGate floor."""

    min_paper_days: int = FLOOR_PAPER_DAYS
    min_closed_trades: int = FLOOR_CLOSED_TRADES
    min_profit_factor: Decimal = FLOOR_PROFIT_FACTOR
    max_drawdown_fraction: Decimal = FLOOR_DRAWDOWN_FRACTION

    def meets(
        self,
        *,
        paper_days: int,
        closed_trades: int,
        profit_factor: Decimal,
        drawdown_fraction: Decimal,
    ) -> bool:
        """True when recorded evidence meets every threshold."""
        return (
            paper_days >= self.min_paper_days
            and closed_trades >= self.min_closed_trades
            and profit_factor >= self.min_profit_factor
            and drawdown_fraction <= self.max_drawdown_fraction
        )


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


def _decimal(raw: object, key: str) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ConfigError([f"promotion threshold {key} is not a decimal: {raw!r}"]) from exc


def _read_section(target: Path) -> dict[str, object]:
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError([f"promotion thresholds unparsable: {target}: {exc}"]) from exc
    section = raw.get("promotion", {}).get("thresholds", {})
    if not isinstance(section, dict):
        raise ConfigError([f"promotion thresholds section missing in {target}"])
    return section


def _int_threshold(section: dict[str, object], key: str, floor: int, problems: list[str]) -> int:
    value = section.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        problems.append(f"promotion threshold {key} is missing or not an int")
        return floor
    if value < floor:
        problems.append(
            f"promotion threshold {key}={value} is looser than the LiveGate floor {floor}"
        )
    return value


def _decimal_threshold(
    section: dict[str, object], key: str, floor: Decimal, problems: list[str]
) -> Decimal:
    raw = section.get(key)
    if raw is None:
        problems.append(f"promotion threshold {key} is missing")
        return floor
    value = _decimal(raw, key)
    looser = value < floor if key == "min_profit_factor" else value > floor
    if looser:
        problems.append(
            f"promotion threshold {key}={value} is looser than the LiveGate floor {floor}"
        )
    return value


def load_thresholds(path: Path | str | None = None) -> PromotionThresholds:
    """Load thresholds from the version-controlled TOML file, fail-closed.

    Raises ConfigError naming the key when a threshold is looser than its
    floor, when a key is missing, or when the file does not parse.
    """
    target = Path(path) if path is not None else DEFAULT_THRESHOLDS_PATH
    section = _read_section(target)
    problems: list[str] = []
    paper_days = _int_threshold(section, "min_paper_days", FLOOR_PAPER_DAYS, problems)
    closed = _int_threshold(section, "min_closed_trades", FLOOR_CLOSED_TRADES, problems)
    profit = _decimal_threshold(section, "min_profit_factor", FLOOR_PROFIT_FACTOR, problems)
    drawdown = _decimal_threshold(
        section, "max_drawdown_fraction", FLOOR_DRAWDOWN_FRACTION, problems
    )
    if problems:
        raise ConfigError(problems)
    return PromotionThresholds(
        min_paper_days=paper_days,
        min_closed_trades=closed,
        min_profit_factor=profit,
        max_drawdown_fraction=drawdown,
    )


def default_thresholds_path() -> Path:
    """In-package promotion_thresholds.toml path."""
    return DEFAULT_THRESHOLDS_PATH


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
