"""Characterization: tune grid search (STRUCT-003).

Pins ``engine/tune.py`` against ``vendor/grokbot-pumpfun/scripts/tune.py``.
The math (weighted total, threshold split, rank tie-breaks, simplex grid,
weight normalization) is vendor-identical; the surroundings differ on
purpose: records arrive as plain mappings instead of the unported
``TradeLog`` rotation, weights arrive as ``ScoringWeights``, and output
goes through ``sys.stdout.write``. ``main`` is exercised end to end on a
temporary JSONL log.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.config.settings import ScoringWeights
from pumpgrok.engine.tune import (
    COMPONENTS,
    Candidate,
    Outcome,
    current_weights,
    evaluate,
    fmt_weights,
    load_candidates,
    main,
    rank,
    run_report,
    simplex,
    total,
)


def _scored(kind: str, mint: str, value: float) -> dict[str, Any]:
    """One scored record with a flat component value."""
    return {"type": kind, "mint": mint, "scores": dict.fromkeys(COMPONENTS, value)}


def _candidates() -> list[Candidate]:
    return [
        Candidate(mint="A", parts=(0.9, 0.9, 0.9, 0.9), bought=True, pnl_lamports=1_000_000_000),
        Candidate(mint="B", parts=(0.1, 0.1, 0.1, 0.1), bought=True, pnl_lamports=-500_000_000),
        Candidate(mint="C", parts=(0.8, 0.8, 0.8, 0.8), bought=False, pnl_lamports=None),
    ]


def test_total_is_positional_weighted_sum() -> None:
    assert total((1.0, 0.5, 0.0, 0.25), (0.3, 0.25, 0.15, 0.3)) == 0.3 + 0.125 + 0.075


def test_evaluate_splits_kept_and_missed() -> None:
    outcome = evaluate(_candidates(), (0.25, 0.25, 0.25, 0.25), 0.5)
    assert (outcome.passed, outcome.kept_trades, outcome.lost_trades) == (2, 1, 1)
    assert outcome.kept_pnl == 1_000_000_000
    assert outcome.lost_pnl == -500_000_000


def test_evaluate_rounds_pnl_to_micro() -> None:
    candidates = [Candidate(mint="A", parts=(1.0, 1.0, 1.0, 1.0), bought=True, pnl_lamports=123_456_789)]
    assert evaluate(candidates, (0.25, 0.25, 0.25, 0.25), 0.5).kept_pnl == 123_456_789


def test_rank_prefers_more_kept_trades_then_diffuse_weights() -> None:
    low_kept = (Outcome(1, 1, 2_000_000_000, 0, 0), (0.25, 0.25, 0.25, 0.25), 0.5)
    high_kept = (Outcome(2, 2, 2_000_000_000, 0, 0), (0.25, 0.25, 0.25, 0.25), 0.5)
    assert rank(high_kept) > rank(low_kept)
    diffuse = (Outcome(2, 2, 2_000_000_000, 0, 0), (0.25, 0.25, 0.25, 0.25), 0.5)
    concentrated = (Outcome(2, 2, 2_000_000_000, 0, 0), (1.0, 0.0, 0.0, 0.0), 0.5)
    assert rank(diffuse) > rank(concentrated)


def test_simplex_covers_unit_sum_grid() -> None:
    grid = simplex(0.5)
    assert len(grid) == 10
    for mix in grid:
        assert len(mix) == 4
        assert abs(sum(mix) - 1.0) < 1e-9
    assert (1.0, 0.0, 0.0, 0.0) in grid
    assert (0.25, 0.25, 0.25, 0.25) not in grid


def test_current_weights_normalize_in_component_order() -> None:
    assert current_weights(ScoringWeights(audit=0.3, narrative=0.25, timing=0.15, metrics=0.3)) == (
        0.3,
        0.25,
        0.15,
        0.3,
    )
    assert current_weights(ScoringWeights(audit=1.0, narrative=1.0, timing=1.0, metrics=1.0)) == (
        0.25,
        0.25,
        0.25,
        0.25,
    )


def test_fmt_weights_renders_compact_mix() -> None:
    assert fmt_weights((0.3, 0.25, 0.15, 0.3)) == "audi=0.30 narr=0.25 timi=0.15 metr=0.30"


def test_load_candidates_dedupes_and_attaches_close_pnl() -> None:
    records: list[dict[str, Any]] = [
        _scored("buy", "A", 0.9),
        _scored("buy", "A", 0.1),
        {"type": "close", "mint": "A", "pnl_sol": "2.5"},
        _scored("buy", "B", 0.2),
        _scored("skip", "C", 0.7),
        {"type": "close", "mint": "C", "pnl_sol": "-1.0"},
        {"type": "buy", "mint": "D"},
    ]
    candidates = load_candidates(records)
    by_mint = {candidate.mint: candidate for candidate in candidates}
    assert set(by_mint) == {"A", "B", "C"}
    assert by_mint["A"].parts == (0.9, 0.9, 0.9, 0.9)
    assert by_mint["A"].pnl_lamports == 2_500_000_000
    assert by_mint["B"].pnl_lamports is None
    assert by_mint["C"].bought is False
    assert by_mint["C"].pnl_lamports is None


def test_run_report_needs_scored_records(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    lines, code = run_report(str(empty), 0.10, 10, ScoringWeights())
    assert code == 1
    assert "nothing to tune" in lines[0]


def test_main_reports_thresholds_and_grid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "trades.jsonl"
    rows: list[dict[str, Any]] = [
        _scored("buy", "A", 0.9),
        {"type": "close", "mint": "A", "pnl_sol": "1.5"},
        _scored("buy", "B", 0.1),
        {"type": "close", "mint": "B", "pnl_sol": "-0.5"},
    ]
    log.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    assert main([str(log), "--top", "3"]) == 0
    out = capsys.readouterr().out
    assert "WEIGHT TUNING" in out
    assert "Threshold sweep" in out
    assert "Weight search" in out
