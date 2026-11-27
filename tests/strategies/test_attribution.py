"""STR-03: per-strategy P&L folds exactly to the desk total."""

from __future__ import annotations

import pytest

from pumpgrok.strategies.attribution import fold_attribution


def test_fold_equals_desk_total() -> None:
    fold = fold_attribution(
        {"momentum_breakout": 1000, "legacy_screening": -400, "mean_reversion": 250},
        850,
    )
    assert fold.folded_lamports == 850
    assert fold.desk_total_lamports == 850
    assert fold.per_strategy["momentum_breakout"] == 1000


def test_mismatch_raises_instead_of_drifting() -> None:
    with pytest.raises(ValueError):
        fold_attribution({"momentum_breakout": 1000}, 999)


def test_non_int_pnl_refused() -> None:
    with pytest.raises(ValueError):
        fold_attribution({"momentum_breakout": True}, 1)  # type: ignore[dict-item]
