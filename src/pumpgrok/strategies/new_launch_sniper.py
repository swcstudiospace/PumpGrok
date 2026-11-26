<<<<<<< HEAD
"""new_launch_sniper baseline strategy (STR-04).

Entries bounded to the early window: a mint fires one buy while its age
is at most ``max_age_seconds`` after creation. The window is a ParamSet
parameter, never a literal; construction validates it against the
declared BOUNDS (which equal the [strategy.new_launch_sniper.max_age_seconds]
TOML section exactly). Older mints never fire; state is incremental, so
the look-ahead canary holds.
=======
"""new_launch_sniper: buy a young launch with enough buyers and a thin curve; exit on a target.

PENDING OWNER APPROVAL. DEFAULTS are starting proposals with reasons in 15-PLANS-INDEX.md,
not final pins (owner decision 2). The sniper's max age is its own rule; it is not
filter.min_age_seconds (owner to confirm the interaction).

Rule, as proposed:
- BUY when the mint is at most max_age_seconds old, has at least min_unique_buyers unique
  buyers, has curve progress at most max_curve_progress, and the mint has never been entered
  by this strategy (one entry per mint).
- SELL when price >= entry_price * (1 + take_profit_pct / 100).

Prices are integer lamports. Percent and fraction parameters are read as exact rationals.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
from typing import Any

from pumpgrok.strategies.base import (
    Intent,
    StrategyContext,
    bounds_for,
    code_digest,
    strategy_version_id,
)
from pumpgrok.strategies.tape import Tick

__all__ = ["NewLaunchSniperStrategy"]


class NewLaunchSniperStrategy:
    """One-shot early-window buyer per mint."""

    def __init__(self, params: dict[str, Any]) -> None:
        bounds = bounds_for("new_launch_sniper")
        if "max_age_seconds" not in params:
            raise ValueError("new_launch_sniper requires max_age_seconds")
        value = params["max_age_seconds"]
        low, high = bounds["max_age_seconds"]
        if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
            raise ValueError(f"max_age_seconds {value!r} outside [{low}, {high}]")
        self._max_age = value
        self._fired: set[str] = set()

    @property
    def id(self) -> str:
        return "new_launch_sniper"

    @property
    def BOUNDS(self) -> dict[str, tuple[int, int]]:
        return bounds_for(self.id)

    def version_id(self, params: dict[str, Any]) -> str:
        return strategy_version_id(self.id, params, code=code_digest(self.id))

    def on_tick(self, tick: Tick) -> None:
        return None

    def decide(self, context: StrategyContext) -> Intent | None:
        if not context.tape:
            return None
        tick = context.tape[-1]
        if tick.mint in self._fired:
            return None
        if tick.created_ts is None or tick.age_seconds > self._max_age:
            return None
        self._fired.add(tick.mint)
        return Intent(
            strategy_id=self.id,
            side="buy",
            mint=tick.mint,
            size_lamports=1_000_000,
            reason=f"early window age {tick.age_seconds}s <= {self._max_age}s",
        )
=======
from collections.abc import Mapping
from typing import Any, ClassVar

from pumpgrok.strategies.base import Intent, Side, StrategyContext
from pumpgrok.strategies.recovery import Position, StrategyBook, exact
from pumpgrok.upgrade.bounds import KeyBound

__all__ = ["ENTRY_LAMPORTS", "NewLaunchSniper"]

#: Size of each entry, equal to the replay buy amount (supervisor REPLAY_BUY_LAMPORTS).
ENTRY_LAMPORTS = 10_000_000


class NewLaunchSniper:
    """The launch sniper: one early entry per mint, sold at a take-profit."""

    strategy_id: ClassVar[str] = "new_launch_sniper"
    BOUNDS: ClassVar[Mapping[str, KeyBound]] = {
        "max_age_seconds": KeyBound(minimum=10, maximum=900),
        "min_unique_buyers": KeyBound(minimum=1, maximum=1000),
        "max_curve_progress": KeyBound(minimum=0.0, maximum=1.0),
        "take_profit_pct": KeyBound(minimum=1.0, maximum=1000.0),
    }
    DEFAULTS: ClassVar[Mapping[str, Any]] = {
        "max_age_seconds": 300,
        "min_unique_buyers": 5,
        "max_curve_progress": 0.10,
        "take_profit_pct": 80.0,
    }

    def __init__(self) -> None:
        self.book = StrategyBook.fresh()

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        tick = context.tick
        book = self.book
        held = book.positions.get(tick.mint)
        intents: list[Intent] = []
        if held is None:
            if self._qualifies(context):
                book.open(
                    tick.mint,
                    Position(
                        entry_ts=tick.ts,
                        entry_price_lamports=tick.price_lamports,
                        size_lamports=ENTRY_LAMPORTS,
                    ),
                )
                intents.append(_intent(context, "buy", ENTRY_LAMPORTS, "launch qualifies"))
        else:
            target_pct = exact(self.DEFAULTS["take_profit_pct"])
            target = exact(held.entry_price_lamports) * (1 + target_pct / 100)
            if exact(tick.price_lamports) >= target:
                book.close(tick.mint)
                intents.append(_intent(context, "sell", held.size_lamports, "take_profit"))
        book.observe(tick.mint, tick.ts, tick.price_lamports)
        return tuple(intents)

    def _qualifies(self, context: StrategyContext) -> bool:
        tick = context.tick
        if self.book.probation.get(tick.mint, 0) > 0:
            return False
        if tick.ts - tick.launch_ts > self.DEFAULTS["max_age_seconds"]:
            return False
        if tick.unique_buyers < self.DEFAULTS["min_unique_buyers"]:
            return False
        return exact(tick.curve_progress) <= exact(self.DEFAULTS["max_curve_progress"])


def _intent(context: StrategyContext, side: Side, size_lamports: int, reason: str) -> Intent:
    mint = context.tick.mint
    return Intent(
        strategy_id=NewLaunchSniper.strategy_id,
        mint=mint,
        side=side,
        size_lamports=size_lamports,
        decision_id=f"{NewLaunchSniper.strategy_id}:{side}:{mint}:{context.tick.ts!r}",
        reason=reason,
        version_id=context.version_id,
    )
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
