"""Backtest paper gate: same-window paper comparison and the D7 promotion gate.

Split out of cli/backtest.py (11-04). The window readers come from backtest_holdout.py, so the
paper summary and the holdout summary read the ledger rows the same way.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.backtest.divergence import DivergenceVerdict, breach_line, check, enforce
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.backtest.results import SharedResult
from pumpgrok.cli.backtest_holdout import (
    _fills_from_rows,
    _read_window_ledger,
    _row_stamp,
    _window_metrics,
)
from pumpgrok.cli.codes import EXIT_OK
from pumpgrok.cli.errors import UsageError, _say
from pumpgrok.config.settings import ConfigError
from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce


@dataclass(frozen=True)
class _PaperOutcome:
    """Paper-gate result: summaries, promotion flag, reason text, exit code."""

    paper_metrics: MetricsReport | None
    divergence_reasons: tuple[str, ...]
    promotion_eligible: bool
    reasons: tuple[str, ...]
    exit_code: int


def _paper_window(
    rows: Sequence[Mapping[str, Any]],
    *,
    cutoff: float,
    window_end: float,
    initial: int,
) -> tuple[LedgerState, list[Mapping[str, Any]]]:
    """Fold paper rows before the window into its opening state; keep the window rows.

    Rows stamped before the cutoff set the opening equity, so the paper curve
    starts where the window starts rather than at genesis. Rows at or past the
    window end are left out, so the paper summary counts the same span the
    holdout summary does, whatever the paper ledger holds after it.
    """
    opening = initial_state(source="backtest", initial_equity_lamports=initial, day_utc="")
    window_rows: list[Mapping[str, Any]] = []
    for row in rows:
        stamp = _row_stamp(row)
        if stamp < cutoff:
            opening = reduce(opening, row)
        elif stamp < window_end:
            window_rows.append(row)
    return (opening, window_rows)


def _paper_evidence(
    paper_file: Path,
    *,
    dataset_name: str,
    run_id: str,
    cutoff: float,
    window_end: float,
    elapsed_days: Decimal,
    initial_fallback: int,
) -> tuple[MetricsReport, SharedResult]:
    """Verify the paper ledger hash chain, then summarize its rows over the holdout window."""
    paper_rows, paper_meta = _read_window_ledger(paper_file, verify=True)
    paper_initial = int(paper_meta) if paper_meta is not None else initial_fallback
    opening, window_rows = _paper_window(
        paper_rows, cutoff=cutoff, window_end=window_end, initial=paper_initial
    )
    paper_fills, _ = _fills_from_rows(window_rows)
    paper_metrics = _window_metrics(
        paper_fills, genesis=opening, rows=window_rows, elapsed_days=elapsed_days
    )
    paper_result = SharedResult.from_ledger_rows(
        run_id=run_id,
        dataset=dataset_name,
        window_start_ts=cutoff,
        window_end_ts=window_end,
        rows=paper_rows,
    )
    return (paper_metrics, paper_result)


def _verdict_outcome(
    verdict: DivergenceVerdict, paper_metrics: MetricsReport, eligible: bool
) -> _PaperOutcome:
    """Map the divergence verdict to the promotion outcome; a breach prints its line and fails."""
    if verdict.blocks_promotion:
        line = breach_line(verdict)
        if line is None:
            raise ConfigError(["divergence verdict blocks without a breach line"])
        _say(sys.stderr, line)
        return _PaperOutcome(
            paper_metrics,
            verdict.reasons,
            False,
            ("divergence breach: " + "|".join(verdict.reasons),),
            enforce(verdict),
        )
    if eligible:
        return _PaperOutcome(
            paper_metrics,
            verdict.reasons,
            True,
            ("trial count within limit and paper divergence within D7 defaults",),
            EXIT_OK,
        )
    return _PaperOutcome(paper_metrics, verdict.reasons, False, (), EXIT_OK)


def _paper_gate(
    *,
    paper_ledger: str | None,
    dataset_name: str,
    run_id: str,
    cutoff: float,
    window_end: float,
    elapsed_days: Decimal,
    initial_fallback: int,
    backtest_result: SharedResult,
    window_metrics: MetricsReport,
    eligible: bool,
) -> _PaperOutcome:
    """Same-window paper comparison and the D7 promotion gate (PAP-02, G-08).

    Without a paper ledger path promotion stays ineligible with reason
    divergence not compared. With one, the paper ledger's hash chain is verified
    first (LedgerInconsistent on failure), then the paper rows over the holdout window
    (from the cutoff to the window end) build the paper summary,
    opened at the equity the paper ledger held at the cutoff. SharedResult.compare
    enforces window equality before divergence.check, and a breach prints the
    DIVERGENCE BREACH line on stderr and exits 1 via enforce. Promotion is
    eligible only when trials are within limit and the verdict passes.
    """
    if paper_ledger is None:
        return _PaperOutcome(None, (), False, ("divergence not compared",), EXIT_OK)
    paper_file = Path(paper_ledger)
    if not paper_file.is_file():
        raise UsageError(f"bad --paper-ledger {paper_ledger!r}: want a ledger sqlite file")
    paper_metrics, paper_result = _paper_evidence(
        paper_file,
        dataset_name=dataset_name,
        run_id=run_id,
        cutoff=cutoff,
        window_end=window_end,
        elapsed_days=elapsed_days,
        initial_fallback=initial_fallback,
    )
    backtest_result.compare(paper_result)
    verdict = check(window_metrics, paper_metrics)
    return _verdict_outcome(verdict, paper_metrics, eligible)
