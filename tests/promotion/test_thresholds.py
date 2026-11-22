"""PRM-02: a looser threshold than the LiveGate floors refuses to load.

One parametrized looser-than-floor case per floor, plus missing-key and
unparsable cases. The floors are single-sourced from the live gate
module, never retyped.
"""

from __future__ import annotations

import sys
import tomllib
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.config.settings import ConfigError
from pumpgrok.execution.live.live_gate import (
    MAX_DRAWDOWN_FRACTION,
    MIN_CLOSED_TRADES,
    MIN_PAPER_DAYS,
    MIN_PROFIT_FACTOR,
)
from pumpgrok.promotion.thresholds import (
    FLOOR_CLOSED_TRADES,
    FLOOR_DRAWDOWN_FRACTION,
    FLOOR_PAPER_DAYS,
    FLOOR_PROFIT_FACTOR,
    load_thresholds,
)

DEFAULT = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "config" / "promotion_thresholds.toml"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "thresholds.toml"
    path.write_text(body, encoding="utf-8")
    return path


GOOD = (
    "[promotion.thresholds]\n"
    "min_paper_days = 14\n"
    "min_closed_trades = 50\n"
    'min_profit_factor = "1.20"\n'
    'max_drawdown_fraction = "0.15"\n'
)


def test_floors_are_single_sourced_from_the_live_gate() -> None:
    assert FLOOR_PAPER_DAYS == MIN_PAPER_DAYS
    assert FLOOR_CLOSED_TRADES == MIN_CLOSED_TRADES
    assert FLOOR_PROFIT_FACTOR == Decimal(str(MIN_PROFIT_FACTOR))
    assert FLOOR_DRAWDOWN_FRACTION == Decimal(str(MAX_DRAWDOWN_FRACTION))


def test_default_file_loads_at_the_floors() -> None:
    thresholds = load_thresholds(DEFAULT)
    assert thresholds.min_paper_days == MIN_PAPER_DAYS
    assert thresholds.min_closed_trades == MIN_CLOSED_TRADES
    assert thresholds.min_profit_factor == Decimal(str(MIN_PROFIT_FACTOR))
    assert thresholds.max_drawdown_fraction == Decimal(str(MAX_DRAWDOWN_FRACTION))


def test_default_file_parses_as_toml() -> None:
    raw = tomllib.loads(DEFAULT.read_text(encoding="utf-8"))
    assert isinstance(raw["promotion"]["thresholds"], dict)


@pytest.mark.parametrize(
    ("key", "looser_value"),
    [
        ("min_paper_days", 13),
        ("min_closed_trades", 49),
        ("min_profit_factor", "1.10"),
        ("max_drawdown_fraction", "0.20"),
    ],
)
def test_looser_than_floor_refuses_to_load(tmp_path: Path, key: str, looser_value: object) -> None:
    body = GOOD.replace(
        f'{key} = {"14" if key == "min_paper_days" else "50" if key == "min_closed_trades" else chr(34) + ("1.20" if key == "min_profit_factor" else "0.15") + chr(34)}',
        f"{key} = {looser_value!r}".replace("'", '"'),
    )
    with pytest.raises(ConfigError) as excinfo:
        load_thresholds(_write(tmp_path, body))
    assert key in str(excinfo.value)


def test_missing_key_refuses_to_load(tmp_path: Path) -> None:
    body = GOOD.replace("min_closed_trades = 50\n", "")
    with pytest.raises(ConfigError) as excinfo:
        load_thresholds(_write(tmp_path, body))
    assert "min_closed_trades" in str(excinfo.value)


def test_unparsable_file_refuses_to_load(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_thresholds(_write(tmp_path, "[promotion.thresholds"))


def test_thresholds_meet_check() -> None:
    thresholds = load_thresholds(DEFAULT)
    assert thresholds.meets(
        paper_days=14, closed_trades=50, profit_factor=Decimal("1.20"), drawdown_fraction=Decimal("0.15")
    )
    assert not thresholds.meets(
        paper_days=13, closed_trades=50, profit_factor=Decimal("1.20"), drawdown_fraction=Decimal("0.15")
    )
