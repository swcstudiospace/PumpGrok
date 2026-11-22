"""Fail-closed version-controlled promotion thresholds (PRM-02, T-17-08).

Every threshold lives in ``config/promotion_thresholds.toml`` with the
LiveGate floors as constants read from the execution live gate module,
never as retyped numbers. The loader refuses the whole file with a
ConfigError naming the key when any threshold is looser than its floor,
when a key is missing, or when the file does not parse. Ratios are
Decimal; counts are integers.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

from pumpgrok.config.settings import ConfigError
from pumpgrok.execution.live.live_gate import (
    MAX_DRAWDOWN_FRACTION,
    MIN_CLOSED_TRADES,
    MIN_PAPER_DAYS,
    MIN_PROFIT_FACTOR,
)

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "DEFAULT_THRESHOLDS_PATH",
    "PromotionThresholds",
    "load_thresholds",
]

DEFAULT_THRESHOLDS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "promotion_thresholds.toml"
)

#: Floors: the tightest values a promotion file may declare.
FLOOR_PAPER_DAYS = MIN_PAPER_DAYS
FLOOR_CLOSED_TRADES = MIN_CLOSED_TRADES
FLOOR_PROFIT_FACTOR = Decimal(str(MIN_PROFIT_FACTOR))
FLOOR_DRAWDOWN_FRACTION = Decimal(str(MAX_DRAWDOWN_FRACTION))


@dataclass(frozen=True)
class PromotionThresholds:
    """Promotion thresholds, each at least as strict as its LiveGate floor."""

    min_paper_days: int = FLOOR_PAPER_DAYS
    min_closed_trades: int = FLOOR_CLOSED_TRADES
    min_profit_factor: Decimal = FLOOR_PROFIT_FACTOR
    max_drawdown_fraction: Decimal = FLOOR_DRAWDOWN_FRACTION

    def meets(self, *, paper_days: int, closed_trades: int, profit_factor: Decimal, drawdown_fraction: Decimal) -> bool:
        """True when recorded evidence meets every threshold."""
        return (
            paper_days >= self.min_paper_days
            and closed_trades >= self.min_closed_trades
            and profit_factor >= self.min_profit_factor
            and drawdown_fraction <= self.max_drawdown_fraction
        )


def _decimal(raw: object, key: str) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ConfigError([f"promotion threshold {key} is not a decimal: {raw!r}"]) from exc


def load_thresholds(path: Path | str | None = None) -> PromotionThresholds:
    """Load thresholds from the version-controlled TOML file, fail-closed.

    Raises ConfigError naming the key when a threshold is looser than its
    floor, when a key is missing, or when the file does not parse.
    """
    target = Path(path) if path is not None else DEFAULT_THRESHOLDS_PATH
    problems: list[str] = []
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError([f"promotion thresholds unparsable: {target}: {exc}"]) from exc
    section = raw.get("promotion", {}).get("thresholds", {})
    if not isinstance(section, dict):
        raise ConfigError([f"promotion thresholds section missing in {target}"])

    def _int(key: str, floor: int) -> int:
        value = section.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            problems.append(f"promotion threshold {key} is missing or not an int")
            return floor
        if value < floor:
            problems.append(
                f"promotion threshold {key}={value} is looser than the LiveGate floor {floor}"
            )
        return value

    paper_days = _int("min_paper_days", FLOOR_PAPER_DAYS)
    closed = _int("min_closed_trades", FLOOR_CLOSED_TRADES)

    profit_raw = section.get("min_profit_factor")
    drawdown_raw = section.get("max_drawdown_fraction")
    if profit_raw is None:
        problems.append("promotion threshold min_profit_factor is missing")
        profit = FLOOR_PROFIT_FACTOR
    else:
        profit = _decimal(profit_raw, "min_profit_factor")
        if profit < FLOOR_PROFIT_FACTOR:
            problems.append(
                f"promotion threshold min_profit_factor={profit} is looser than the LiveGate floor {FLOOR_PROFIT_FACTOR}"
            )
    if drawdown_raw is None:
        problems.append("promotion threshold max_drawdown_fraction is missing")
        drawdown = FLOOR_DRAWDOWN_FRACTION
    else:
        drawdown = _decimal(drawdown_raw, "max_drawdown_fraction")
        if drawdown > FLOOR_DRAWDOWN_FRACTION:
            problems.append(
                f"promotion threshold max_drawdown_fraction={drawdown} is looser than the LiveGate floor {FLOOR_DRAWDOWN_FRACTION}"
            )
    if problems:
        raise ConfigError(problems)
    return PromotionThresholds(
        min_paper_days=paper_days,
        min_closed_trades=closed,
        min_profit_factor=profit,
        max_drawdown_fraction=drawdown,
    )
